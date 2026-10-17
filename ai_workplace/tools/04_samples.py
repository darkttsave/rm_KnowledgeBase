#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase A pre-check -- part 3/3: sampling of ordinary text, printed TOC,
tables, special-font pages; PUA context; notes-version text contamination.
Read-only.
"""
import os
import re
import json
import difflib
from collections import Counter

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "原始材料")
OUT = os.path.join(ROOT, "ai_workplace", "audit", "samples")
os.makedirs(OUT, exist_ok=True)

F26 = os.path.join(SRC, "2026 机甲大师超级对抗赛比赛规则手册V2.2.0.pdf")
F27O = os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-官方版.pdf")
F27N = os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-笔记版.pdf")
W = lambda n, s: open(os.path.join(OUT, n), "w", encoding="utf-8").write(s)

out = []

# ---------------------------------------------------- locate printed TOC pages
d26, d27o, d27n = pymupdf.open(F26), pymupdf.open(F27O), pymupdf.open(F27N)
for tag, doc in (("2026", d26), ("2027", d27o)):
    hits = [p + 1 for p in range(min(20, doc.page_count))
            if "目录" in doc.load_page(p).get_text("text")[:80]]
    print(tag, "printed TOC candidate pages:", hits, flush=True)
    out.append("%s printed TOC candidate pages: %s" % (tag, hits))

# ------------------------------------------------------- footer page numbering
for tag, doc in (("2026", d26), ("2027", d27o)):
    print("--- %s footer samples" % tag, flush=True)
    for p in (15, 16, 17, 40, 100, doc.page_count - 1):
        page = doc.load_page(p)
        foot = [b[4].strip() for b in page.get_text("blocks")
                if b[3] > page.rect.height * 0.90]
        print("   phys p%-4d label=%-4s footer=%r" % (p + 1, page.get_label(), foot), flush=True)

# ------------------------------------------------------------- table sampling
def table_probe(doc, pages, tag):
    res = []
    for p in pages:
        page = doc.load_page(p - 1)
        tabs = page.find_tables()
        entry = dict(page=p, n_tables=len(tabs.tables), tables=[])
        for t in tabs.tables:
            try:
                data = t.extract()
            except Exception as e:
                data = [["<extract error %r>" % e]]
            blank = sum(1 for row in data for c in row if not (c or "").strip())
            cells = sum(len(r) for r in data)
            entry["tables"].append(dict(
                bbox=[round(v, 1) for v in t.bbox], rows=t.row_count, cols=t.col_count,
                cells=cells, blank_cells=blank,
                header=data[0] if data else [],
                sample=[r for r in data[:4]]))
        res.append(entry)
    return res

table_pages = {}
for tag, doc, pages in (("2026", d26, [3, 4, 5, 60, 61, 62, 63, 100, 120, 130]),
                        ("2027-official", d27o, [3, 4, 5, 58, 59, 60, 61, 95, 115, 125]),
                        ("2027-notes", d27n, [3, 4, 5, 58, 59, 60, 61, 95, 115, 125])):
    table_pages[tag] = table_probe(doc, pages, tag)
    print("== table probe", tag, flush=True)
    for e in table_pages[tag]:
        print("   p%-4d tables=%d %s" % (e["page"], e["n_tables"],
              "" if not e["tables"] else str([(t["rows"], t["cols"], "blank=%d" % t["blank_cells"]) for t in e["tables"]])))

# --------------------------------------------- PUA context (Wingdings bullets)
print("== PUA context", flush=True)
ctx = []
for tag, doc, pages in (("2026", d26, [2, 17, 77]), ("2027-official", d27o, [2, 15, 76])):
    for p in pages:
        t = doc.load_page(p - 1).get_text("text")
        for m in re.finditer("[\ue000-\uf8ff]", t):
            s = t[max(0, m.start() - 45):m.end() + 45].replace("\n", " ")
            ctx.append(dict(doc=tag, page=p, cp="U+%04X" % ord(m.group()),
                            context=s))
print(json.dumps(ctx[:20], ensure_ascii=False, indent=1))

# --------------------------- notes vs official: the 3 differing pages in detail
print("== differing pages detail", flush=True)
diffdetail = []
for p in (29, 76, 95):
    a = d27o.load_page(p - 1).get_text("text")
    b = d27n.load_page(p - 1).get_text("text")
    sm = difflib.SequenceMatcher(None, re.sub(r"\s+", "", a), re.sub(r"\s+", "", b))
    adds = [re.sub(r"\s+", "", b)[i1:i2] for tag_, i1, i2, j1, j2 in sm.get_opcodes() if tag_ == "insert"]
    dels = [re.sub(r"\s+", "", a)[i1:i2] for tag_, i1, i2, j1, j2 in sm.get_opcodes() if tag_ == "delete"]
    diffdetail.append(dict(page=p, only_in_notes=adds[:12], only_in_official=dels[:12]))
    print("   p%d only-in-notes=%s only-in-official=%s" % (p, adds[:6], dels[:6]))

# ------------------------------------ annotation rectangles vs page text on p29
ann29 = []
for a in d27n.load_page(28).annots():
    ann29.append(dict(type=a.type[1], rect=[round(v, 1) for v in a.rect],
                      content=(a.info or {}).get("content", "")[:80]))
print("   p29 annots:", json.dumps(ann29, ensure_ascii=False)[:600])

# ---------------------------------------------------- raw body text samples
for tag, doc, pages in (("2026", d26, [1, 2, 5, 16, 17, 60, 100, 159]),
                        ("2027-official", d27o, [1, 2, 5, 13, 14, 60, 100, 144]),
                        ("2027-notes", d27n, [29, 76, 95])):
    buf = []
    for p in pages:
        page = doc.load_page(p - 1)
        buf.append("\n" + "=" * 70 + "\n### %s physical page %d (label %s)\n" % (tag, p, page.get_label())
                   + "=" * 70 + "\n" + page.get_text("text"))
    W("text_%s.txt" % tag, "\n".join(buf))
    print("   wrote text_%s.txt" % tag, flush=True)

json.dump(dict(tables=table_pages, pua_context=ctx, diff_pages=diffdetail, p29_annots=ann29),
          open(os.path.join(ROOT, "ai_workplace", "audit", "precheck_samples.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
for d in (d26, d27o, d27n):
    d.close()
print("done")
