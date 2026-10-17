#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase A pre-check -- part 4: fix-ups.
* real text delta on the 3 differing pages (official vs notes)
* locate genuinely table-heavy pages (line density) and re-probe find_tables
* render sample pages to PNG for visual inspection
* locate pages that emit the MuPDF ExtGState 'GS' warning
Read-only.
"""
import os
import re
import json
import difflib
import sys

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "原始材料")
AUD = os.path.join(ROOT, "ai_workplace", "audit")
IMG = os.path.join(AUD, "img")
os.makedirs(IMG, exist_ok=True)

F26 = os.path.join(SRC, "2026 机甲大师超级对抗赛比赛规则手册V2.2.0.pdf")
F27O = os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-官方版.pdf")
F27N = os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-笔记版.pdf")

strip = lambda s: re.sub(r"\s+", "", s)
res = {}

# --------------------------------------------------- 1. real text delta
d27o, d27n = pymupdf.open(F27O), pymupdf.open(F27N)
delta = []
for p in (29, 76, 95):
    a, b = strip(d27o.load_page(p - 1).get_text("text")), strip(d27n.load_page(p - 1).get_text("text"))
    ops = difflib.SequenceMatcher(None, a, b).get_opcodes()
    ins = [b[j1:j2] for tag, i1, i2, j1, j2 in ops if tag in ("insert", "replace")]
    dele = [a[i1:i2] for tag, i1, i2, j1, j2 in ops if tag in ("delete", "replace")]
    delta.append(dict(page=p, official_len=len(a), notes_len=len(b), inserted=ins, deleted=dele))
    print("p%-3d official=%d notes=%d  inserted=%r deleted=%r" % (p, len(a), len(b), ins, dele))
res["notes_text_delta"] = delta

# --------------------------------------- 2. table-heavy pages by line density
def line_counts(doc):
    out = []
    for pno in range(doc.page_count):
        page = doc.load_page(pno)
        h = v = 0
        for d in page.get_drawings():
            for item in d["items"]:
                if item[0] == "l":
                    p1, p2 = item[1], item[2]
                    if abs(p1.y - p2.y) < 1.5 and abs(p1.x - p2.x) > 20:
                        h += 1
                    elif abs(p1.x - p2.x) < 1.5 and abs(p1.y - p2.y) > 10:
                        v += 1
                elif item[0] == "re":
                    r = item[1]
                    if r.width > 20 and r.height < 3:
                        h += 1
                    if r.height > 10 and r.width < 3:
                        v += 1
        out.append((h, v, pno + 1))
    return out

heaviest = {}
for tag, path in (("2026", F26), ("2027-official", F27O)):
    doc = pymupdf.open(path)
    lc = line_counts(doc)
    top = sorted(lc, reverse=True)[:14]
    heaviest[tag] = top
    print(tag, "heaviest table-line pages (h,v,page):", top)
    doc.close()
res["table_line_heaviest"] = heaviest

# --------------------------------------------------- 3. ExtGState GS warning
import contextlib, io
gs_pages = {}
for tag, path in (("2026", F26), ("2027-official", F27O), ("2027-notes", F27N)):
    doc = pymupdf.open(path)
    hits = []
    for pno in range(doc.page_count):
        buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(buf):
                doc.load_page(pno).get_text("text")
        except Exception:
            pass
        if "ExtGState" in buf.getvalue():
            hits.append(pno + 1)
    gs_pages[tag] = hits
    print(tag, "ExtGState warning pages:", hits)
    doc.close()
res["extgstate_pages"] = gs_pages

json.dump(res, open(os.path.join(AUD, "precheck_fixups.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
d27o.close(); d27n.close()
print("done")
