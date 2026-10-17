#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 2 -- step 4: collect every number quoted in 结构化验证报告.md."""
import os
import re
import json
import glob
from collections import Counter, defaultdict

import struct_lib as L

OUT = L.STRUCT


def load(path):
    return json.load(open(path, encoding="utf-8"))


stats = {}
sk = {d: load(os.path.join(OUT, "%s_章节骨架.json" % d.replace("RMUC", ""))) for d in L.DOCS}
index = load(os.path.join(OUT, "samples_index.json"))

print("=== skeleton ===")
for d in L.DOCS:
    s = sk[d]
    v = s["validation"]
    secs = s["sections"]
    outline = [x for x in secs if x["region_type"] == "section"]
    para_levels = Counter(x["level"] for x in outline)
    pm = s["page_map"]
    multi = Counter()
    for p in pm:
        if len(p["sections"]) > 1:
            multi[p["physical_page"]] = len(p["sections"])
    # how much of a page can belong to two sections: top example
    top = sorted(multi.items(), key=lambda kv: -kv[1])[:5]
    stats[d] = dict(
        regions=v["sections_total"], outline=v["outline_sections"],
        synthetic=v["synthetic_regions"], levels={str(k): para_levels[k] for k in (1, 2, 3, 4)},
        heading_matched=v["heading_matched"], heading_exact=v["heading_matched_exact"],
        heading_rate=v["heading_match_rate"], level_size_ok=v["level_size_confirmed"],
        blocks=v["blocks_assigned"], blocks_lost=v["blocks_lost"],
        running=v["running_header_footer_blocks"],
        multi_pages=v["pages_with_multiple_section_starts"],
        max_per_page=v["max_sections_starting_on_one_page"],
        spanning=v["sections_spanning_pages"],
        zero_content=len(v["sections_with_zero_content"]),
        unmatched_headings=[u["text"] for u in v["unmatched_block_headings"]],
        pages_with_2plus_sections=multi,
        top_multi_pages=top,
        chars=sum(x["char_count"] for x in secs),
        pages=len(pm),
        sections_with_caption=None,
    )
    print(" %-9s regions=%d outline=%d synth=%d levels=%s blocks=%d lost=%d"
          % (d, stats[d]["regions"], stats[d]["outline"], stats[d]["synthetic"],
             stats[d]["levels"], stats[d]["blocks"], stats[d]["blocks_lost"]))
    print("            multi-section pages=%d max=%d spanning=%d top=%s"
          % (stats[d]["multi_pages"], stats[d]["max_per_page"], stats[d]["spanning"],
             stats[d]["top_multi_pages"]))

print()
print("=== samples ===")
recs = []
for f in sorted(glob.glob(os.path.join(L.SAMPLES, "*.jsonl"))):
    recs += [json.loads(l) for l in open(f, encoding="utf-8")]
kinds = Counter(r.get("block_kind", r["record_type"]) for r in recs)
per_doc = Counter(r["doc_id"] for r in recs)
paras = [r for r in recs if r.get("block_kind") == "paragraph"]
line_counts = Counter(r["line_count"] for r in paras)
cross = [r for r in recs if r.get("cross_page")]
review = [r for r in recs if r.get("needs_review")]
stats["samples"] = dict(
    files=len(glob.glob(os.path.join(L.SAMPLES, "*.jsonl"))),
    records=len(recs), per_doc=dict(per_doc), kinds=dict(kinds),
    paragraphs=len(paras), paragraph_lines=dict(sorted(line_counts.items())),
    multi_line_paragraphs=sum(n for k, n in line_counts.items() if k > 1),
    max_lines=max(line_counts) if line_counts else 0,
    cross_page_paragraphs=len(cross), needs_review=len(review),
    needs_review_kinds=dict(Counter(r.get("block_kind", r["record_type"]) for r in review)),
    chars=sum(len(r.get("raw_text") or "") for r in recs),
    preserved=sum(1 for r in recs if r.get("normalization", {}).get("chars_preserved")),
    normalized_records=sum(1 for r in recs if r.get("normalization")),
)
print(" files", stats["samples"]["files"], "records", len(recs), dict(per_doc))
print(" kinds", dict(kinds))
print(" paragraphs", len(paras), "multi-line", stats["samples"]["multi_line_paragraphs"],
      "max lines", stats["samples"]["max_lines"], "cross-page", len(cross))
print(" needs_review", len(review), dict(Counter(r.get("block_kind", r["record_type"]) for r in review)))

print()
print("=== tables ===")
tabs = [r for r in recs if r["record_type"] == "table"]
stats["tables"] = dict(
    count=len(tabs),
    per_doc=dict(Counter(r["doc_id"] for r in tabs)),
    with_caption=sum(1 for r in tabs if r["caption"]),
    continuation_no_caption=sum(1 for r in tabs if not r["caption"]),
    rows=sum(r["extraction"]["rows"] for r in tabs),
    cells=sum(r["extraction"]["cells"] for r in tabs),
    blank=sum(r["extraction"]["blank_cells"] for r in tabs),
    blank_ratio=round(sum(r["extraction"]["blank_cells"] for r in tabs)
                      / max(1, sum(r["extraction"]["cells"] for r in tabs)), 3),
    min_blank_ratio=min(r["extraction"]["blank_ratio"] for r in tabs),
    max_blank_ratio=max(r["extraction"]["blank_ratio"] for r in tabs),
    merge_suspects=sum(len(r["merge_suspects"]) for r in tabs),
    all_unapplied=all(not r["merge_suspects_applied"] for r in tabs),
    all_needs_review=all(r["needs_review"] for r in tabs),
    words_box=sum(r["coverage_check"]["words_in_box"] for r in tabs),
    words_missing=sum(len(r["coverage_check"]["missing_words"]) for r in tabs),
    tables_with_loss=sum(1 for r in tabs if r["coverage_check"]["data_loss_suspected"]),
    raw_grid_intact=all(
        r["extraction"]["blank_cells"] == sum(1 for row in r["grid_raw"] for c in row if not c.strip())
        for r in tabs),
    source_lines=sum(r["extraction"]["source_text_lines_inside_box"] for r in tabs),
    table_nos=sorted({r["table_no"] for r in tabs if r["table_no"]}),
)
for k, v in stats["tables"].items():
    print("  %-22s %s" % (k, v))

print()
print("=== formulas / diagram labels ===")
frac = [r for r in recs if r["record_type"] == "formula_fraction"]
parts = [r for r in recs if r.get("block_kind") == "formula_fraction_part"]
diag = [r for r in recs if r.get("block_kind") == "diagram_label"]
fpara = [r for r in recs if r.get("block_kind") == "formula_paragraph"]
scripts = Counter()
for r in recs:
    for lay in (r.get("formula_span_layout") or []):
        if isinstance(lay, list):
            for sp in lay:
                scripts[sp["script"]] += 1
        elif lay:
            scripts[lay["script"]] += 1
stats["formulas"] = dict(
    fractions=len(frac), fraction_parts=len(parts),
    fraction_details=[dict(doc=r["doc_id"], page=r["physical_page"],
                           numerator=r["numerator_text"], denominator=r["denominator_text"],
                           part_records=len(r["part_record_ids"])) for r in frac],
    diagram_labels=len(diag), formula_paragraphs=len(fpara),
    span_scripts=dict(scripts),
    cambria_records=sum(1 for r in recs if r.get("flags", {}).get("uses_cambria_math")),
    formula_with_layout=sum(1 for r in recs if r.get("formula_span_layout")),
    records_with_scripts=sum(1 for r in recs if r.get("script_spans")),
    subscript_spans=sum(len(r.get("script_spans") or []) for r in recs),
    table_loss_records=[dict(record_id=r["record_id"],
                             missing_from_grid=r["coverage_check"]["missing_from_grid"],
                             missing_words=r["coverage_check"]["missing_words"],
                             missing_also_from_source=r["coverage_check"]["missing_also_from_source_lines"],
                             source_lines_kept=len(r["source_text_lines"]))
                        for r in tabs if r["coverage_check"]["data_loss_suspected"]],
)
for k, v in stats["formulas"].items():
    print("  %-22s %s" % (k, v))

print()
print("=== deliverable inventory ===")
files = {}
for p in sorted(glob.glob(os.path.join(OUT, "**", "*"), recursive=True)):
    if os.path.isfile(p):
        files[os.path.relpath(p, L.ROOT).replace("\\", "/")] = os.path.getsize(p)
stats["files"] = files
for k, v in files.items():
    print("  %-58s %8d" % (k, v))

json.dump(stats, open(os.path.join(OUT, "verification_stats.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\nwritten verification_stats.json")
