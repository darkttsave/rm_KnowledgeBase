#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase A pre-check -- part 9: reading-order quality (default vs geometric),
special-font pages, formula subscript handling, changelog body, note inventory.
Read-only.
"""
import os
import re
import json
import difflib

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "原始材料")
AUD = os.path.join(ROOT, "ai_workplace", "audit")

FILES = {
    "2026": os.path.join(SRC, "2026 机甲大师超级对抗赛比赛规则手册V2.2.0.pdf"),
    "2027-official": os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-官方版.pdf"),
    "2027-notes": os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-笔记版.pdf"),
}
out = {}
lines = lambda t: [l.strip() for l in t.splitlines() if l.strip()]

# ------------------------------------------- 1. reading-order quality
print("== reading order: default vs geometrically sorted")
order = {}
for tag, path in FILES.items():
    doc = pymupdf.open(path)
    worst, ratios = [], []
    for pno in range(doc.page_count):
        page = doc.load_page(pno)
        a, b = lines(page.get_text("text")), lines(page.get_text("text", sort=True))
        if len(a) < 3:
            continue
        r = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
        ratios.append(r)
        worst.append((round(r, 3), pno + 1))
    worst.sort()
    order[tag] = dict(mean=round(sum(ratios) / max(1, len(ratios)), 4),
                      lowest=worst[:12],
                      pages_below_0_9=sum(1 for r in ratios if r < 0.9))
    print("  ", tag, "mean line-sequence similarity %.4f" % order[tag]["mean"],
          " pages<0.90:", order[tag]["pages_below_0_9"], " lowest:", worst[:6])
    doc.close()
out["reading_order"] = order

# -------------------------------------------- 2. special font pages
print("== special pages")
spec = {}
checks = [("2026", FILES["2026"], [70, 85]), ("2027-official", FILES["2027-official"], [68, 83])]
for tag, path, pages in checks:
    doc = pymupdf.open(path)
    for p in pages:
        page = doc.load_page(p - 1)
        fonts = sorted({f[3] for f in doc.get_page_fonts(p - 1)})
        spec["%s p%d" % (tag, p)] = dict(fonts=fonts, text=page.get_text("text")[:700])
        print("  ", tag, "p%d fonts=%s" % (p, fonts))
    doc.close()
out["special_pages"] = spec

# ------------------------------- 3. formula sub/superscript span geometry
print("== formula span geometry (2026 p101)")
doc = pymupdf.open(FILES["2026"])
page = doc.load_page(100)
found = []
for blk in page.get_text("dict")["blocks"]:
    if blk["type"]:
        continue
    for line in blk["lines"]:
        txt = "".join(s["text"] for s in line["spans"])
        if "sin" in txt or "spd" in txt:
            base = line["spans"][0]["size"]
            for s in line["spans"]:
                found.append(dict(text=s["text"][:26], font=s["font"].split("+")[-1],
                                  size=round(s["size"], 2), origin=[round(v, 1) for v in s["origin"]],
                                  line_base_size=round(base, 2)))
doc.close()
out["formula_spans"] = found[:25]
for f in found[:14]:
    print("   ", f)

# ---------------------------------------------- 4. changelog body text
print("== changelog body")
chg = {}
for tag, path in FILES.items():
    doc = pymupdf.open(path)
    txt = "\n".join(doc.load_page(p).get_text("text") for p in range(2, 5))
    chg[tag] = txt
    doc.close()
open(os.path.join(AUD, "changelog_raw.txt"), "w", encoding="utf-8").write(
    "\n\n".join("######## %s ########\n%s" % (k, v) for k, v in chg.items()))
print("   written changelog_raw.txt")

# ---------------------------------------- 5. notes inventory (types, content)
doc = pymupdf.open(FILES["2027-notes"])
inv, freetext = [], []
for pno in range(doc.page_count):
    for a in doc.load_page(pno).annots():
        info = a.info or {}
        rec = dict(page=pno + 1, type=a.type[1], rect=[round(v, 1) for v in a.rect],
                   content=info.get("content", ""), title=info.get("title", ""),
                   subject=info.get("subject", ""), creationDate=info.get("creationDate", ""),
                   modDate=info.get("modDate", ""), colors=a.colors, opacity=a.opacity)
        inv.append(rec)
        if a.type[1] == "FreeText":
            freetext.append(rec)
doc.close()
out["notes_inventory"] = inv
out["notes_freetext"] = freetext
from collections import Counter
print("== notes:", len(inv), dict(Counter(a['type'] for a in inv)))
print("   FreeText notes:", json.dumps(freetext, ensure_ascii=False, indent=1))

json.dump(out, open(os.path.join(AUD, "precheck_extra.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("done")
