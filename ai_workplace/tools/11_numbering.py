#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase A pre-check -- part 10: numbering integrity (tables/figures) and
internal cross-reference resolvability.  Read-only, diagnostic only.
"""
import os
import re
import json
from collections import Counter, defaultdict

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "原始材料")
AUD = os.path.join(ROOT, "ai_workplace", "audit")

FILES = {
    "2026": os.path.join(SRC, "2026 机甲大师超级对抗赛比赛规则手册V2.2.0.pdf"),
    "2027-official": os.path.join(SRC, "RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-官方版.pdf"),
}
RANGES = {"2026": dict(toc=(7, 10), tabs=(11, 12), figs=(13, 15)),
          "2027-official": dict(toc=(4, 7), tabs=(8, 9), figs=(10, 12))}
LINE = re.compile(r"^(?P<title>\S.*?)\s*\.{3,}\s*(?P<page>\d{1,3})\s*$")

out = {}
for tag, path in FILES.items():
    doc = pymupdf.open(path)
    r = RANGES[tag]
    listed = {}
    for kind, (a, b) in (("tabs", r["tabs"]), ("figs", r["figs"])):
        n = {}
        for pno in range(a - 1, b):
            for raw in doc.load_page(pno).get_text("text").splitlines():
                m = LINE.match(raw.strip())
                if not m:
                    continue
                t = re.sub(r"\s+", "", m.group("title"))
                n[t] = int(m.group("page"))
        listed[kind] = n

    # captions actually present in the body
    txt_pages = [doc.load_page(i).get_text("text") for i in range(doc.page_count)]
    body_tables = Counter()
    body_figs = Counter()
    for t in txt_pages:
        for m in re.finditer(r"表\s?(\d{1,2})-(\d{1,2})", t):
            body_tables[(int(m.group(1)), int(m.group(2)))] += 1
        for m in re.finditer(r"图\s?(\d{1,2})-(\d{1,2})", t):
            body_figs[(int(m.group(1)), int(m.group(2)))] += 1

    def numbering(d):
        nums = []
        for t in d:
            m = re.match(r"^[表图](\d+)-(\d+)", t)
            if m:
                nums.append((int(m.group(1)), int(m.group(2))))
        by_ch = defaultdict(list)
        for c, i in nums:
            by_ch[c].append(i)
        gaps, dupes = [], []
        for c, v in sorted(by_ch.items()):
            vs = sorted(v)
            if len(set(vs)) != len(vs):
                dupes.append((c, [x for x, n in Counter(vs).items() if n > 1]))
            missing = [i for i in range(1, max(vs) + 1) if i not in set(vs)]
            if missing:
                gaps.append((c, missing))
        return dict(count=len(nums), chapters=len(by_ch), gaps=gaps, duplicates=dupes)

    # cross references inside the body: 详见"5.5.3.9 堡垒增益点机制"
    outline_nums = set()
    for lvl, title, page in doc.get_toc():
        m = re.match(r"^([\d.]+)\s", title)
        if m:
            outline_nums.add(m.group(1).rstrip("."))
    refs = Counter()
    for t in txt_pages:
        for m in re.finditer(r"详见\s*[“\"]?\s*([0-9]+(?:\.[0-9]+){1,4})", t):
            refs[m.group(1)] += 1
    unresolved = {k: v for k, v in refs.items() if k not in outline_nums}

    out[tag] = dict(table_numbering=numbering(listed["tabs"]),
                    figure_numbering=numbering(listed["figs"]),
                    listed_tables=len(listed["tabs"]), listed_figures=len(listed["figs"]),
                    refs_total=sum(refs.values()), refs_distinct=len(refs),
                    unresolved_refs=dict(sorted(unresolved.items())[:40]),
                    unresolved_count=len(unresolved))
    print("==", tag)
    print("   表目录条目", len(listed["tabs"]), " 图目录条目", len(listed["figs"]))
    print("   表编号 gaps:", out[tag]["table_numbering"]["gaps"][:5],
          " duplicates:", out[tag]["table_numbering"]["duplicates"][:5])
    print("   图编号 gaps:", out[tag]["figure_numbering"]["gaps"][:5],
          " duplicates:", out[tag]["figure_numbering"]["duplicates"][:5])
    print("   正文 详见 引用", out[tag]["refs_total"], "次 /", out[tag]["refs_distinct"],
          "个不同编号, 未能对应到书签章节:", out[tag]["unresolved_count"],
          dict(list(out[tag]["unresolved_refs"].items())[:10]))
    doc.close()

json.dump(out, open(os.path.join(AUD, "numbering_refs.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("done")
