#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase A pre-check -- part 6: table extraction quality, PyMuPDF vs pdfplumber.
Read-only; writes readable table dumps under ai_workplace/audit/tables/.
"""
import os
import json

import pymupdf
import pdfplumber

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "原始材料")
AUD = os.path.join(ROOT, "ai_workplace", "audit")
TAB = os.path.join(AUD, "tables")
os.makedirs(TAB, exist_ok=True)

F26 = os.path.join(SRC, "2026 机甲大师超级对抗赛比赛规则手册V2.2.0.pdf")
F27O = os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-官方版.pdf")

CASES = [
    ("2026", F26, [94, 95, 96, 97, 103, 120, 130]),
    ("2027-official", F27O, [93, 94, 83, 21, 117, 95]),
]

rows_out = []
buf = []
for tag, path, pages in CASES:
    doc = pymupdf.open(path)
    with pdfplumber.open(path) as pl:
        for p in pages:
            page = doc.load_page(p - 1)
            fits = page.find_tables()
            pt = pl.pages[p - 1]
            plts = pt.find_tables()
            rec = dict(doc=tag, page=p, pymupdf_tables=[], pdfplumber_tables=[])
            buf.append("\n" + "#" * 78)
            buf.append("# %s  physical page %d   (PyMuPDF tables=%d, pdfplumber tables=%d)"
                       % (tag, p, len(fits.tables), len(plts)))
            buf.append("#" * 78)
            for i, t in enumerate(fits.tables):
                data = t.extract()
                blank = sum(1 for r in data for c in r if not (c or "").strip())
                cells = sum(len(r) for r in data)
                rec["pymupdf_tables"].append(dict(rows=t.row_count, cols=t.col_count,
                                                 cells=cells, blank=blank,
                                                 blank_ratio=round(blank / max(1, cells), 2)))
                buf.append("\n-- PyMuPDF table %d  rows=%d cols=%d blank=%d/%d (%.0f%%)"
                           % (i, t.row_count, t.col_count, blank, cells, 100 * blank / max(1, cells)))
                for r in data[:8]:
                    buf.append("   | " + " | ".join((c or "").replace("\n", " ")[:28] for c in r))
                if len(data) > 8:
                    buf.append("   ... (%d more rows)" % (len(data) - 8))
            for i, t in enumerate(plts):
                data = t.extract()
                blank = sum(1 for r in data for c in r if not (c or "").strip())
                cells = sum(len(r) for r in data)
                rec["pdfplumber_tables"].append(dict(rows=len(data), cols=len(data[0]) if data else 0,
                                                     cells=cells, blank=blank,
                                                     blank_ratio=round(blank / max(1, cells), 2)))
                buf.append("\n-- pdfplumber table %d  rows=%d cols=%d blank=%d/%d (%.0f%%)"
                           % (i, len(data), len(data[0]) if data else 0, blank, cells,
                              100 * blank / max(1, cells)))
                for r in data[:8]:
                    buf.append("   | " + " | ".join((c or "").replace("\n", " ")[:28] for c in r))
                if len(data) > 8:
                    buf.append("   ... (%d more rows)" % (len(data) - 8))
            rows_out.append(rec)
    doc.close()

open(os.path.join(TAB, "table_compare.txt"), "w", encoding="utf-8").write("\n".join(buf))
json.dump(rows_out, open(os.path.join(AUD, "table_compare.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

print("page  | PyMuPDF (rows x cols blank%)            | pdfplumber (rows x cols blank%)")
for r in rows_out:
    a = "; ".join("%dx%d %d%%" % (t["rows"], t["cols"], 100 * t["blank_ratio"]) for t in r["pymupdf_tables"]) or "-"
    b = "; ".join("%dx%d %d%%" % (t["rows"], t["cols"], 100 * t["blank_ratio"]) for t in r["pdfplumber_tables"]) or "-"
    print("%-5s | %-40s | %-40s" % (r["page"], a, b))
print("written table_compare.txt")
