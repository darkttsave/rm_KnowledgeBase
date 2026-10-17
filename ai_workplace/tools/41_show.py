#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 4 helper: dump the reading text of specific sections so the alignment
decision can be based on actual content (evidence), not on numbering.

Usage: python 41_show.py 2026 3.1 3.2 2027 3.1.1 3.1.2
       python 41_show.py --mode full 2026 5.6.7 2027 5.6.3
"""
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STRUCT = os.path.join(ROOT, "ai_workplace", "structured")


def load(doc):
    sk = json.load(open(os.path.join(STRUCT, "%s_章节骨架.json" % doc), encoding="utf-8"))
    recs = {}
    for line in open(os.path.join(STRUCT, "%s_结构化.jsonl" % doc), encoding="utf-8"):
        r = json.loads(line)
        recs.setdefault(r["section_index"], []).append(r)
    return sk, recs


def show(doc, nos, width=300, maxlines=12):
    sk, recs = load(doc)
    by_no = {s["section_no"]: s for s in sk["sections"] if s["section_no"]}
    by_title = {s["title"]: s for s in sk["sections"]}
    for no in nos:
        s = by_no.get(no) or by_title.get(no)
        if not s:
            print("  [%s] section %s not found" % (doc, no))
            continue
        rs = recs.get(s["section_id"], [])
        print("\n" + "=" * 100)
        print("%s  %s  | L%d | pages %s | 记录 %d 条"
              % (doc, s["title"], s["level"],
                 (s["pages_with_content"][:1] + s["pages_with_content"][-1:]), len(rs)))
        print("path:", " › ".join(s["path"]))
        n = 0
        for r in rs:
            k = r.get("block_kind", r["record_type"])
            if k in ("heading", "index_entry", "inline_icon", "cover_text"):
                continue
            if k == "table":
                cells = [c for row in r.get("grid_raw") or [] for c in row if c and c.strip()]
                txt = " / ".join(cells[:40])
                print("  [table %s] %s" % (r.get("table_no"), txt[:width]))
            elif k == "figure":
                print("  [figure] p%s %s" % (r["physical_page"], r.get("image_info", {}).get("box_pt")))
            else:
                t = (r.get("norm_text") or r.get("numerator_text") or "").strip()
                if t:
                    print("  [%s] %s" % (k, t[:width]))
            n += 1
            if n >= maxlines:
                print("  ... (%d more records)" % (len(rs) - n))
                break


def main():
    args = sys.argv[1:]
    mode = "brief"
    if args and args[0] == "--mode":
        mode = args[1]
        args = args[2:]
    i = 0
    while i < len(args):
        doc = args[i]
        i += 1
        nos = []
        while i < len(args) and args[i] not in ("2026", "2027"):
            nos.append(args[i])
            i += 1
        show(doc, nos, width=300 if mode == "brief" else 2000,
             maxlines=12 if mode == "brief" else 60)


if __name__ == "__main__":
    main()
