#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Independent re-verification of every headline number quoted in
《PDF预检查报告.md》.  Recomputes from the original PDFs only (no cached JSON)
and prints PASS / FAIL per claim.  Read-only.
"""
import os
import re
import io
import json
import hashlib
import difflib
from collections import Counter

import pymupdf
from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "原始材料")

F26 = os.path.join(SRC, "2026 机甲大师超级对抗赛比赛规则手册V2.2.0.pdf")
F27O = os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-官方版.pdf")
F27N = os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-笔记版.pdf")

checks = []


def check(name, got, want):
    ok = got == want
    checks.append((ok, name, got, want))
    print(("PASS " if ok else "FAIL ") + "%-58s got=%r want=%r" % (name, got, want))
    return ok


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest().upper()


def norm(s):
    return re.sub(r"\s+", "", s)


def lines(t):
    return [l.strip() for l in t.splitlines() if l.strip()]


print("=== 1. identity ===")
check("sha256 2026", sha(F26), "88AE3C7D0BBD7312C8095EFF2603910437E292A0B53F46C9378F26144C09A6F5")
check("sha256 2027 official", sha(F27O), "9E2EED9295536C6FD547B62D634DF1D5E70A2E1E2250E5DFF3521D557E5D54BE")
check("sha256 2027 notes", sha(F27N), "C085D56458B3D012BE10955B8246CC2BE99CE2A35D9C7674DE6C47B7E6404A14")
check("bytes 2026", os.path.getsize(F26), 21018604)
check("bytes 2027 official", os.path.getsize(F27O), 22455861)

d26, d27o, d27n = pymupdf.open(F26), pymupdf.open(F27O), pymupdf.open(F27N)
check("pages 2026", d26.page_count, 159)
check("pages 2027 official", d27o.page_count, 144)
check("pages 2027 notes", d27n.page_count, 144)
check("outline 2026", len(d26.get_toc()), 130)
check("outline 2027 official", len(d27o.get_toc()), 129)
check("outline 2027 notes", len(d27n.get_toc()), 0)
check("notes has_annots", d27n.has_annots(), True)
check("official has_annots", d27o.has_annots(), False)
check("notes has_links", d27n.has_links(), False)

print("=== 2. text quality ===")
tot, pua_tot, pua_distinct, efffd, empty, tablepages = {}, {}, {}, {}, {}, {}
for tag, doc in (("2026", d26), ("2027o", d27o), ("2027n", d27n)):
    n = pua = rep = 0
    pc = Counter()
    empties = 0
    tp = 0
    for pno in range(doc.page_count):
        page = doc.load_page(pno)
        t = page.get_text("text")
        n += len(t)
        rep += t.count("\ufffd")
        for ch in t:
            if 0xE000 <= ord(ch) <= 0xF8FF:
                pua += 1
                pc[ch] += 1
        if len(t.strip()) < 5:
            empties += 1
        if len(page.find_tables().tables) > 0:
            tp += 1
    tot[tag], pua_tot[tag], pua_distinct[tag] = n, pua, len(pc)
    efffd[tag], empty[tag], tablepages[tag] = rep, empties, tp

check("chars 2026", tot["2026"], 100632)
check("chars 2027 official", tot["2027o"], 92985)
check("chars 2027 notes", tot["2027n"], 93001)
check("PUA total 2026", pua_tot["2026"], 469)
check("PUA distinct 2026", pua_distinct["2026"], 3)
check("PUA total 2027 official", pua_tot["2027o"], 391)
check("PUA distinct 2027 official", pua_distinct["2027o"], 5)
check("U+FFFD all docs", efffd["2026"] + efffd["2027o"] + efffd["2027n"], 0)
check("empty pages all docs", empty["2026"] + empty["2027o"] + empty["2027n"], 0)
check("table pages 2026", tablepages["2026"], 65)
check("table pages 2027 official", tablepages["2027o"], 59)

print("=== 3. fonts ===")
fonts, no_tu = {}, {}
for tag, doc in (("2026", d26), ("2027o", d27o), ("2027n", d27n)):
    seen, bad = set(), 0
    for pno in range(doc.page_count):
        for f in doc.get_page_fonts(pno):
            seen.add(f[0])
    for xref in seen:
        k = doc.xref_get_key(xref, "ToUnicode")
        if not k or k[0] == "null":
            bad += 1
    fonts[tag], no_tu[tag] = len(seen), bad
check("font count 2026", fonts["2026"], 21)
check("font count 2027 official", fonts["2027o"], 15)
check("fonts w/o ToUnicode 2026", no_tu["2026"], 5)
check("fonts w/o ToUnicode 2027 official", no_tu["2027o"], 0)

print("=== 4. TOC / page numbering ===")
LINE = re.compile(r"^(?P<title>\S.*?)\s*\.{3,}\s*(?P<page>\d{1,3})\s*$")


def printed(doc, a, b):
    out = {}
    for pno in range(a - 1, b):
        for raw in doc.load_page(pno).get_text("text").splitlines():
            m = LINE.match(raw.strip())
            if m:
                t = norm(m.group("title"))
                out.setdefault(t, int(m.group("page")))
    return out


for tag, doc, rng in (("2026", d26, (7, 10)), ("2027o", d27o, (4, 7))):
    p = printed(doc, *rng)
    ol = [norm(t[1]) for t in doc.get_toc()]
    olset = set(ol)
    missing = [t for t in p if t not in olset]
    extra = [t for t in ol if t not in set(p)]
    mism = 0
    for t, pg in p.items():
        i = ol.index(t)
        bm = doc.get_toc()[i][2]
        if bm and bm - 1 != pg:
            mism += 1
    check("printed TOC entries %s" % tag, len(p), 103)
    check("printed not in outline %s" % tag, len(missing), 0)
    check("outline-only entries %s" % tag, len(extra), 27 if tag == "2026" else 26)
    check("page mismatches %s" % tag, mism, 0)
    bad = 0
    for pno in range(doc.page_count):
        txt = doc.load_page(pno).get_text("text")
        m = re.findall(r"(\d{1,3})\s+©\s*2026\s*大疆\s*版权所有|©\s*2026\s*大疆\s*版权所有\s+(\d{1,3})", txt)
        m = [a or b for a, b in m]
        if m and pno > 0 and int(m[-1]) != pno:
            bad += 1
    check("footer page-number violations %s" % tag, bad, 0)

print("=== 5. annotations / notes isolation ===")
inv_pages, inv_types = [], []
for pno in range(d27n.page_count):
    page = d27n.load_page(pno)
    kept = list(page.annots())          # keep bound to this live page object
    for a in kept:
        inv_pages.append(pno + 1)
        inv_types.append(a.type[1])
check("notes annot total", len(inv_types), 101)
check("notes annot types", dict(Counter(inv_types)),
      {"Highlight": 73, "Ink": 25, "FreeText": 3})
check("pages with annots", len(set(inv_pages)), 24)
check("official annots", sum(1 for p in range(d27o.page_count) for _ in d27o.load_page(p).annots()), 0)

same, diff, inserts = 0, [], {}
for pno in range(d27o.page_count):
    a = norm(d27o.load_page(pno).get_text("text"))
    b = norm(d27n.load_page(pno).get_text("text"))
    if a == b:
        same += 1
    else:
        diff.append(pno + 1)
        sm = difflib.SequenceMatcher(None, a, b)
        inserts[pno + 1] = [b[j1:j2] for tag_, i1, i2, j1, j2 in sm.get_opcodes()
                            if tag_ in ("insert", "replace")]
check("pages textually identical", same, 141)
check("pages textually differing", diff, [29, 76, 95])
check("note text leaked into body", inserts,
      {29: ["没有反制空中支援"], 76: ["变多"], 95: ["0.5"]})

print("=== 6. render comparison official vs notes ===")
clean = 0
for pno in range(d27o.page_count):
    pa = d27o.load_page(pno).get_pixmap(dpi=50)
    pb = d27n.load_page(pno).get_pixmap(dpi=50)
    ia = Image.open(io.BytesIO(pa.tobytes("png"))).convert("L")
    ib = Image.open(io.BytesIO(pb.tobytes("png"))).convert("L")
    hist = ImageChops.difference(ia, ib).histogram()
    if sum(hist[16:]) / sum(hist) < 0.00005:
        clean += 1
check("pages pixel-identical (official vs notes)", clean, 121)

print("=== 7. covers ===")
for tag, doc in (("2026", d26), ("2027o", d27o)):
    pg = doc.load_page(0)
    nsp = sum(1 for b in pg.get_text("dict")["blocks"] if b["type"] == 0
              for l in b["lines"] for s in l["spans"])
    check("cover %s text chars" % tag, len(pg.get_text("text").strip()), 78 if tag == "2026" else 23)
    check("cover %s spans" % tag, nsp, 20 if tag == "2026" else 6)
check("2026 cover garbled sample",
      "3PCP.BTUFS" in d26.load_page(0).get_text("text"), True)
check("version V2.2.0 in body p3", "V2.2.0" in d26.load_page(2).get_text("text"), True)
check("version V1.0.0 in body p2/p3",
      "V1.0.0" in d27o.load_page(1).get_text("text") and "V1.0.0" in d27o.load_page(2).get_text("text"), True)

print("=== 8. reading order body vs table ===")
for tag, doc in (("2026", d26), ("2027o", d27o)):
    body, tbl = [], []
    for pno in range(doc.page_count):
        pg = doc.load_page(pno)
        a, b = lines(pg.get_text("text")), lines(pg.get_text("text", sort=True))
        if len(a) < 3:
            continue
        r = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
        (tbl if pg.find_tables().tables else body).append(r)
    mb = round(sum(body) / len(body), 3)
    mt = round(sum(tbl) / len(tbl), 3)
    check("mean body similarity %s" % tag, mb, 0.648 if tag == "2026" else 0.646)
    check("mean table similarity %s" % tag, mt, 0.293 if tag == "2026" else 0.349)

print("=== 9. numbering / cross references ===")
for tag, doc in (("2026", d26), ("2027o", d27o)):
    nums = set()
    for lvl, title, page in doc.get_toc():
        m = re.match(r"^([\d.]+)\s", title)
        if m:
            nums.add(m.group(1).rstrip("."))
    refs = set()
    for pno in range(doc.page_count):
        for m in re.finditer(r"详见\s*[“\"]?\s*([0-9]+(?:\.[0-9]+){1,4})",
                             doc.load_page(pno).get_text("text")):
            refs.add(m.group(1))
    check("unresolved cross-refs %s" % tag, len(refs - nums), 0)

print("=== 10. notes-version MuPDF warnings ===")


def warn_pages_fresh(path):
    """Must run in a pristine interpreter: MuPDF keeps per-context caches, and a
    document already rendered earlier in the same process reports an extra page."""
    import subprocess
    import sys
    code = (
        "import pymupdf,sys\n"
        "d=pymupdf.open(sys.argv[1])\n"
        "pymupdf.TOOLS.reset_mupdf_warnings()\n"
        "out=[]\n"
        "for i in range(d.page_count):\n"
        "    pg=d.load_page(i); pg.get_text('text'); pg.get_pixmap(dpi=20)\n"
        "    if pymupdf.TOOLS.mupdf_warnings().strip():\n"
        "        out.append(i+1); pymupdf.TOOLS.reset_mupdf_warnings()\n"
        "d.close()\n"
        "print('WARN_PAGES='+','.join(map(str,out)))\n"
    )
    r = subprocess.run([sys.executable, "-c", code, path],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    for ln in r.stdout.splitlines():
        if ln.startswith("WARN_PAGES="):
            body = ln.split("=", 1)[1].strip()
            return [int(x) for x in body.split(",") if x]
    raise RuntimeError("warn check subprocess failed: %r %r" % (r.stdout[-300:], r.stderr[-300:]))


check("warned pages in notes version", warn_pages_fresh(F27N), [29, 76, 95, 98, 131])

print("=== 11. table extraction spot checks ===")
t94 = d26.load_page(93).find_tables().tables
blank94 = sum(1 for r in t94[1].extract() for c in r if not (c or "").strip())
check("2026 p94 table1 blank ratio", round(blank94 / 208, 2), 0.67)

print("=== 12. formula font pages / annotation dates ===")
for tag, doc, want in (("2026", d26, 11), ("2027o", d27o, 16)):
    pgs = {p + 1 for p in range(doc.page_count)
           for f in doc.get_page_fonts(p) if "CambriaMath" in f[3]}
    check("CambriaMath pages %s" % tag, len(pgs), want)

dates = []
for pno in range(d27n.page_count):
    page = d27n.load_page(pno)
    for a in list(page.annots()):
        i = a.info or {}
        if i.get("creationDate"):
            dates.append(i["creationDate"])
check("annotation date range",
      (min(dates).replace("D:", "").split("+")[0], max(dates).replace("D:", "").split("+")[0]),
      ("20261015111151", "20261015133740"))

print("=== 13. word-order agreement, body vs table pages ===")
d26, d27o = pymupdf.open(F26), pymupdf.open(F27O)
for tag, doc, want_body, want_tbl in (("2026", d26, (56, 64), (7, 63)),
                                      ("2027o", d27o, (46, 56), (7, 57))):
    body_same = body_tot = tbl_same = tbl_tot = 0
    for pno in range(doc.page_count):
        pg = doc.load_page(pno)
        H = pg.rect.height
        keep = lambda W: [w[4] for w in W if w[1] > H * 0.06 and w[3] < H * 0.94]
        a = keep(pg.get_text("words", sort=False))
        b = keep(pg.get_text("words", sort=True))
        if len(a) < 15:
            continue
        if pg.find_tables().tables:
            tbl_tot += 1
            tbl_same += (a == b)
        else:
            body_tot += 1
            body_same += (a == b)
    check("body pages word-order identical %s" % tag, (body_same, body_tot), want_body)
    check("table pages word-order identical %s" % tag, (tbl_same, tbl_tot), want_tbl)

print("=== 14. cross-reference counts ===")
for tag, doc, want_n, want_d in (("2026", d26, 43, 19), ("2027o", d27o, 23, 13)):
    refs, dist = 0, set()
    for pno in range(doc.page_count):
        for m in re.finditer(r"详见\s*[“\"]?\s*([0-9]+(?:\.[0-9]+){1,4})",
                             doc.load_page(pno).get_text("text")):
            refs += 1
            dist.add(m.group(1))
    check("详见 refs %s" % tag, (refs, len(dist)), (want_n, want_d))

for d in (d26, d27o):
    d.close()
print()
bad = [c for c in checks if not c[0]]
print("=" * 72)
print("TOTAL %d checks, %d PASS, %d FAIL" % (len(checks), len(checks) - len(bad), len(bad)))
for _, name, got, want in bad:
    print("  FAILED:", name, "got", got, "want", want)
print("=" * 72)
raise SystemExit(1 if bad else 0)
