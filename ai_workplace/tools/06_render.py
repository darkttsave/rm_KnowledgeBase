#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase A pre-check -- part 5: render sample pages for visual inspection and
pinpoint the ExtGState warning via fd-level stderr capture.  Read-only.
"""
import os
import io
import json
import contextlib

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "原始材料")
AUD = os.path.join(ROOT, "ai_workplace", "audit")
IMG = os.path.join(AUD, "img")
os.makedirs(IMG, exist_ok=True)

F26 = os.path.join(SRC, "2026 机甲大师超级对抗赛比赛规则手册V2.2.0.pdf")
F27O = os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-官方版.pdf")
F27N = os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-笔记版.pdf")

SAMPLES = {
    "26": (F26, [1, 7, 9, 16, 95, 120, 159]),
    "27o": (F27O, [1, 4, 6, 13, 93, 95, 117, 144]),
    "27n": (F27N, [29, 76, 95]),
}

for tag, (path, pages) in SAMPLES.items():
    doc = pymupdf.open(path)
    for p in pages:
        page = doc.load_page(p - 1)
        pix = page.get_pixmap(dpi=110)
        out = os.path.join(IMG, "%s_p%03d.png" % (tag, p))
        pix.save(out)
        print("rendered", os.path.basename(out), pix.width, "x", pix.height, flush=True)
    doc.close()

# ---- fd-level stderr capture to attribute the MuPDF syntax warning to a page
def probe_pages(tag, path):
    hits = []
    doc = pymupdf.open(path)
    for pno in range(doc.page_count):
        tmp = os.path.join(AUD, "_err.txt")
        saved = os.dup(2)
        f = open(tmp, "wb")
        try:
            os.dup2(f.fileno(), 2)
            page = doc.load_page(pno)
            page.get_text("text")
            page.get_drawings()
            page.get_images(full=True)
        finally:
            os.dup2(saved, 2)
            os.close(saved)
            f.close()
        txt = open(tmp, "rb").read().decode("utf-8", "replace")
        if txt.strip():
            hits.append((pno + 1, txt.strip().splitlines()[0][:90]))
    doc.close()
    return hits

gs = {}
for tag, path in (("2026", F26), ("2027-official", F27O), ("2027-notes", F27N)):
    gs[tag] = probe_pages(tag, path)
    print(tag, "pages emitting MuPDF syntax warnings:", gs[tag][:20], flush=True)

json.dump(gs, open(os.path.join(AUD, "mupdf_warnings.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("done")
