#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase A pre-check -- part 7: printed TOC vs embedded outline; printed page
number <-> physical page mapping.  Read-only.
"""
import os
import re
import json
import difflib
from collections import Counter

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "原始材料")
AUD = os.path.join(ROOT, "ai_workplace", "audit")

FILES = {
    "2026": os.path.join(SRC, "2026 机甲大师超级对抗赛比赛规则手册V2.2.0.pdf"),
    "2027-official": os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-官方版.pdf"),
    "2027-notes": os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-笔记版.pdf"),
}

TOC_LINE = re.compile(r"^(?P<title>\S.*?)\s*\.{3,}\s*(?P<page>\d{1,3})\s*$")


def printed_toc_entries(doc, first, last):
    """Parse the printed 目录 pages; keep the first occurrence of each title."""
    seen, order = {}, []
    for pno in range(first - 1, last):
        for raw in doc.load_page(pno).get_text("text").splitlines():
            line = raw.strip()
            m = TOC_LINE.match(line)
            if not m:
                continue
            title = re.sub(r"\s+", "", m.group("title"))
            if title in ("目录",):
                continue
            if title not in seen:
                seen[title] = int(m.group("page"))
                order.append(title)
    return seen, order


result = {}
for tag, path in FILES.items():
    doc = pymupdf.open(path)
    if tag == "2026":
        first, last = 7, 10           # 目录 only (表目录/图目录 start later)
        tfirst, tlast = 11, 12
        ffirst, flast = 13, 15
    elif tag == "2027-official":
        first, last = 4, 7
        tfirst, tlast = 8, 9
        ffirst, flast = 10, 12
    else:
        first = last = tfirst = tlast = ffirst = flast = -1

    entry = {}
    if first > 0:
        toc, order = printed_toc_entries(doc, first, last)
        tabs, _ = printed_toc_entries(doc, tfirst, tlast)
        figs, _ = printed_toc_entries(doc, ffirst, flast)
        outline = doc.get_toc()
        onames = [re.sub(r"\s+", "", t[1]) for t in outline]
        onames_set = set(onames)

        missing = [t for t in order if t not in onames_set]
        extra = [t for t in onames if t not in set(order)]
        mism = []
        for t in order:
            if t in onames_set:
                idx = onames.index(t)
                bm_page = outline[idx][2]           # 1-based physical
                printed = toc[t]
                if bm_page and bm_page - 1 != printed:
                    mism.append(dict(title=t, printed=printed, bookmark_physical=bm_page))
        entry = dict(
            printed_toc_entries=len(toc), table_entries=len(tabs), figure_entries=len(figs),
            outline_entries=len(outline), outline_depth=max([t[0] for t in outline], default=0),
            in_print_but_not_outline=missing[:40], in_print_but_not_outline_count=len(missing),
            in_outline_but_not_print=extra[:40], in_outline_but_not_print_count=len(extra),
            page_mismatches=mism[:40], page_mismatch_count=len(mism),
        )
        print("==", tag)
        print("   printed 目录 entries:", len(toc), " 表目录:", len(tabs), " 图目录:", len(figs))
        print("   outline entries:", len(outline), " depth:", entry["outline_depth"])
        print("   in print, not in outline (%d):" % len(missing), missing[:12])
        print("   in outline, not in print (%d):" % len(extra), extra[:12])
        print("   printed-vs-bookmark page mismatches (%d):" % len(mism), mism[:8])
    result[tag] = entry
    doc.close()

# ------------------------------- footer page number <-> physical mapping check
print("== footer page-number mapping")
fmap = {}
for tag, path in FILES.items():
    doc = pymupdf.open(path)
    bad, checked, samples = [], 0, []
    for pno in range(doc.page_count):
        page = doc.load_page(pno)
        txt = page.get_text("text")
        nums = re.findall(r"(\d{1,3})\s+©\s*2026\s*大疆\s*版权所有|©\s*2026\s*大疆\s*版权所有\s+(\d{1,3})", txt)
        nums = [a or b for a, b in nums]
        if not nums or pno == 0:
            continue
        checked += 1
        n = int(nums[-1])
        if n != pno:
            bad.append(dict(physical=pno + 1, footer=n))
        if len(samples) < 5:
            samples.append((pno + 1, n))
    fmap[tag] = dict(checked=checked, mismatches=bad[:20], mismatch_count=len(bad), samples=samples)
    print("  ", tag, "checked", checked, "mismatch(printed != physical-1):", len(bad), bad[:6])
    doc.close()

result["footer_map"] = fmap
json.dump(result, open(os.path.join(AUD, "toc_vs_outline.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("done")
