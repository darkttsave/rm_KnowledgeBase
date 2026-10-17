#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase A pre-check -- part 11: render-based comparison of 官方版 vs 笔记版.
Detects whether the PDFium re-save changed anything visually beyond annotations.
Read-only.
"""
import os
import json

import pymupdf
from PIL import Image, ImageChops
import io

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "原始材料")
AUD = os.path.join(ROOT, "ai_workplace", "audit")

OFF = os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-官方版.pdf")
NOT = os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-笔记版.pdf")

a, b = pymupdf.open(OFF), pymupdf.open(NOT)
rows = []
for pno in range(a.page_count):
    pa = a.load_page(pno).get_pixmap(dpi=50)
    pb = b.load_page(pno).get_pixmap(dpi=50)
    ia = Image.open(io.BytesIO(pa.tobytes("png"))).convert("L")
    ib = Image.open(io.BytesIO(pb.tobytes("png"))).convert("L")
    if ia.size != ib.size:
        rows.append((pno + 1, -1, "size-mismatch"))
        continue
    diff = ImageChops.difference(ia, ib)
    hist = diff.histogram()
    npx = sum(hist)
    changed = sum(hist[16:])          # pixels differing by >=16 grey levels
    rows.append((pno + 1, round(changed / npx, 5), ""))

a.close(); b.close()
rows_sorted = sorted(rows, key=lambda r: r[1], reverse=True)
print("pages differing >=16/255 grey levels between 官方版 and 笔记版:")
for p, r, note in rows_sorted[:14]:
    print("   phys p%-4d changed=%.4f%% %s" % (p, 100 * r if r >= 0 else -1, note))
n_clean = sum(1 for _, r, _ in rows if 0 <= r < 0.00005)
print("pages with essentially no change (<0.005% pixels):", n_clean, "/", len(rows))
json.dump(dict(rows=rows, top=[r for r in rows_sorted[:20]], clean_pages=n_clean),
          open(os.path.join(AUD, "render_diff.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("done")
