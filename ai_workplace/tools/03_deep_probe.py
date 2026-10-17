#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase A pre-check -- part 2/3: cross-version text diff, PUA inventory,
annotation inventory, ordering analysis.

Read-only.
"""
import os
import json
import re
import unicodedata
from collections import Counter, defaultdict

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "原始材料")
OUT = os.path.join(ROOT, "ai_workplace", "audit")
os.makedirs(OUT, exist_ok=True)

F26 = os.path.join(SRC, "2026 机甲大师超级对抗赛比赛规则手册V2.2.0.pdf")
F27O = os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-官方版.pdf")
F27N = os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-笔记版.pdf")

norm = lambda s: re.sub(r"\s+", "", s)

report = {}

# ---------------------------------------------------------------- 1. PUA
print("== PUA inventory", flush=True)
pua = {}
for tag, path in (("2026", F26), ("2027-official", F27O), ("2027-notes", F27N)):
    doc = pymupdf.open(path)
    c = Counter()
    pages = defaultdict(list)
    for pno in range(doc.page_count):
        t = doc.load_page(pno).get_text("text")
        for ch in t:
            o = ord(ch)
            if 0xE000 <= o <= 0xF8FF:
                c[ch] += 1
                if len(pages[ch]) < 6:
                    pages[ch].append(pno + 1)
    pua[tag] = dict(total=sum(c.values()),
                    distinct=len(c),
                    chars=[dict(ch=ch, cp="U+%04X" % ord(ch),
                                name=unicodedata.name(ch, "?"),
                                count=n, pages=pages[ch])
                           for ch, n in c.most_common()])
    doc.close()
report["pua"] = pua
for tag, v in pua.items():
    print(" ", tag, v["total"], "occurrences,", v["distinct"], "distinct")
    for e in v["chars"][:30]:
        print("     ", e["cp"], e["name"], "x%d" % e["count"], "pages", e["pages"])

# ------------------------------------------------- 2. official vs notes text
print("== official vs notes body text", flush=True)
da, db = pymupdf.open(F27O), pymupdf.open(F27N)
same = []
diff = []
for pno in range(da.page_count):
    ta, tb = da.load_page(pno).get_text("text"), db.load_page(pno).get_text("text")
    (same if norm(ta) == norm(tb) else diff).append(pno + 1)
report["f27_official_vs_notes"] = dict(
    identical_pages=len(same), differing_pages=diff, page_count=da.page_count)
print("  identical:", len(same), " differing:", diff)
for pno in diff[:6]:
    ta = norm(da.load_page(pno - 1).get_text("text"))
    tb = norm(db.load_page(pno - 1).get_text("text"))
    print("   page", pno, "len", len(ta), len(tb))
da.close(); db.close()

# ------------------------------------------------------------ 3. annotations
print("== annotations in notes version", flush=True)
doc = pymupdf.open(F27N)
annots = []
for pno in range(doc.page_count):
    for a in doc.load_page(pno).annots():
        info = a.info or {}
        annots.append(dict(page=pno + 1, type=a.type[1], rect=[round(v, 1) for v in a.rect],
                           content=info.get("content", ""), name=info.get("name", ""),
                           subject=info.get("subject", ""), title=info.get("title", ""),
                           creationDate=info.get("creationDate", ""),
                           modDate=info.get("modDate", ""),
                           opacity=a.opacity, colors=a.colors,
                           vertices=len(a.vertices) if a.vertices else 0,
                           has_popup=a.has_popup))
doc.close()
by_type = Counter(a["type"] for a in annots)
by_page = Counter(a["page"] for a in annots)
report["annotations_notes"] = dict(
    total=len(annots), by_type=dict(by_type), pages_with=len(by_page),
    per_page=dict(sorted(by_page.items())), items=annots)
print("  total", len(annots), "by type", dict(by_type), "pages", len(by_page))
for a in annots[:12]:
    print("   p%-4d %-12s %s" % (a["page"], a["type"], (a["content"] or "")[:70].replace("\n", " ")))

# official version annotations (sanity: must be none)
doc = pymupdf.open(F27O)
n = sum(1 for pno in range(doc.page_count) for _ in doc.load_page(pno).annots())
doc.close()
report["annotations_official"] = n
print("  official annots:", n)

# --------------------------------------------------- 4. text ordering analysis
print("== ordering analysis", flush=True)
def order_metrics(page):
    nat = page.get_text("text", sort=False).splitlines()
    srt = page.get_text("text", sort=True).splitlines()
    nat = [l for l in nat if l.strip()]
    srt = [l for l in srt if l.strip()]
    if not nat:
        return None
    breaks = sum(1 for a, b in zip(nat, srt) if a != b)
    return dict(natural_lines=len(nat), sorted_lines=len(srt),
                differing_lines=breaks,
                ratio=round(breaks / max(1, min(len(nat), len(srt))), 3))

ord_info = {}
for tag, path, pages in (("2026", F26, range(0, 0)),):
    pass
d = pymupdf.open(F26)
m = [order_metrics(d.load_page(p)) for p in range(d.page_count)]
worst = sorted([(x["ratio"], i + 1) for i, x in enumerate(m) if x], reverse=True)[:10]
report["ordering_2026"] = dict(worst_pages=worst,
                               mean_ratio=round(sum(x["ratio"] for x in m if x) / d.page_count, 3))
print("  2026 worst:", worst)
d.close()
d = pymupdf.open(F27O)
m = [order_metrics(d.load_page(p)) for p in range(d.page_count)]
worst = sorted([(x["ratio"], i + 1) for i, x in enumerate(m) if x], reverse=True)[:10]
report["ordering_2027"] = dict(worst_pages=worst,
                               mean_ratio=round(sum(x["ratio"] for x in m if x) / d.page_count, 3))
print("  2027 worst:", worst)
d.close()

with open(os.path.join(OUT, "precheck_deep.json"), "w", encoding="utf-8") as fh:
    json.dump(report, fh, ensure_ascii=False, indent=1)
print("written precheck_deep.json")
