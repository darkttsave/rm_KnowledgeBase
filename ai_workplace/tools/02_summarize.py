#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Summarise ai_workplace/audit/precheck_structure.json for human review."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(ROOT, "ai_workplace", "audit", "precheck_structure.json")
data = json.load(open(P, encoding="utf-8"))


def short(name):
    if "2026" in name:
        return "2026-V2.2.0"
    return "2027-V1.0.0-" + ("notes" if "笔记" in name else "official")


for d in data["files"]:
    print("=" * 78)
    print(short(d["file"]), "|", d["file"])
    print("  bytes      ", d["bytes"])
    print("  sha256     ", d["sha256"])
    print("  pdf hdr    ", d["pdf_header_version"], " catalog /Version:", d["catalog_version"])
    print("  pages      ", d["page_count"], " encrypted:", d["is_encrypted"],
          " repaired:", d["is_repaired"])
    print("  metadata   ", json.dumps(d["metadata"], ensure_ascii=False))
    print("  page labels", json.dumps(d["page_labels"], ensure_ascii=False)[:400])
    print("  embfiles   ", d["embfile_count"], d["embfile_names"])
    print("  has_links  ", d["has_links"], " has_annots:", d["has_annots"])
    print("  toc        ", d["toc_count"], "entries, max depth", d["toc_maxdepth"])
    print("  chars      ", d["total_chars"])
    print("  empty pages", len(d["empty_pages"]), d["empty_pages"][:40])
    print("  image-only ", len(d["image_only_pages"]), d["image_only_pages"][:40])
    print("  PUA pages  ", len(d["pua_pages"]), d["pua_pages"][:20])
    print("  U+FFFD pgs ", len(d["fffd_pages"]), d["fffd_pages"][:20])
    print("  sort-diff  ", len(d["sort_diff_pages"]), d["sort_diff_pages"][:40])
    print("  fonts      ", len(d["fonts"]))
    for f in d["fonts"]:
        print("     xref%-6s %-9s %-8s emb=%-5s tu=%-14s %s" % (
            f["xref"], f["type"], f["ext"], f["embedded"],
            str(f.get("ToUnicode"))[:14], f["basefont"][:60]))
    print("  pages w/ drawings>0:", sum(1 for p in d["pages"] if p["drawings"] > 0),
          " w/ images>0:", sum(1 for p in d["pages"] if p["images"] > 0),
          " w/ links>0:", sum(1 for p in d["pages"] if p["links"] > 0))
    sizes = {}
    for p in d["pages"]:
        for s in p["sizes"]:
            sizes[s] = sizes.get(s, 0) + 1
    print("  font sizes seen:", sorted(sizes.items(), key=lambda kv: -kv[1])[:14])
    print("  first 6 toc  :")
    for t in d["toc"][:6]:
        print("     ", t)
    print("  last 4 toc   :")
    for t in d["toc"][-4:]:
        print("     ", t)
