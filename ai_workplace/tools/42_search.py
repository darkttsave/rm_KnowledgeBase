#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 4 helper: term-level evidence search across both structured documents.

For each term, report which sections (of which document) contain it and how many
times.  This is the objective evidence used to decide "moved / merged / deleted /
new" without relying on section numbers.

Usage: python 42_search.py 部署模式 底盘能量 控制度 ...
"""
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STRUCT = os.path.join(ROOT, "ai_workplace", "structured")

_cache = {}


def load(doc):
    if doc in _cache:
        return _cache[doc]
    sk = json.load(open(os.path.join(STRUCT, "%s_章节骨架.json" % doc), encoding="utf-8"))
    recs = {}
    for line in open(os.path.join(STRUCT, "%s_结构化.jsonl" % doc), encoding="utf-8"):
        r = json.loads(line)
        recs.setdefault(r["section_index"], []).append(r)
    _cache[doc] = (sk, recs)
    return _cache[doc]


def section_text(recs):
    parts = []
    for r in recs:
        parts.append(r.get("norm_text") or "")
        for row in r.get("grid_raw") or []:
            for c in row:
                parts.append(c or "")
    return "\n".join(parts)


def search(term):
    print("\n### term: %s" % term)
    for doc in ("2026", "2027"):
        sk, recs = load(doc)
        hits = []
        for s in sk["sections"]:
            if s["region_type"] != "section":
                continue
            t = section_text(recs.get(s["section_id"], []))
            n = t.count(term)
            if n:
                hits.append((n, s["section_no"] or s["title"], s["title"]))
        hits.sort(reverse=True)
        total = sum(h[0] for h in hits)
        print("  %s: total=%-4d sections=%d  %s"
              % (doc, total, len(hits),
                 ", ".join("%s(%d)" % (h[1], h[0]) for h in hits[:8])))


def main():
    for term in sys.argv[1:]:
        search(term)


if __name__ == "__main__":
    main()
