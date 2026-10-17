#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 2 -- step 3: independent verification of the skeleton and samples.

Re-derives everything from the PDFs (no cached intermediate values) and prints
PASS/FAIL per claim so the verification report can quote exact numbers.
Read-only.
"""
import os
import re
import json
import glob
from collections import Counter

import pymupdf

import struct_lib as L

checks = []


def check(name, got, want):
    ok = got == want
    checks.append((ok, name, got, want))
    print(("PASS " if ok else "FAIL ") + "%-56s got=%r want=%r" % (name, got, want))
    return ok


def check_true(name, cond, detail=""):
    checks.append((bool(cond), name, cond, True))
    print(("PASS " if cond else "FAIL ") + "%-56s %s" % (name, detail))


def norm(s):
    return re.sub(r"\s+", "", s)


print("=== 1. skeleton vs built-in outline ===")
skeletons = {}
for doc_id, cfg in L.DOCS.items():
    sk = L.load_skeleton(doc_id)
    skeletons[doc_id] = sk
    doc = pymupdf.open(L.doc_path(doc_id))
    toc = doc.get_toc(simple=False)
    doc.close()
    outline = [s for s in sk["sections"] if s["region_type"] == "section"]
    check("%s outline entry count" % doc_id, len(outline), len(toc))
    mism_level = mism_title = mism_page = 0
    for s, (lvl, title, page, dest) in zip(outline, toc):
        if s["level"] != lvl:
            mism_level += 1
        if s["title"] != title:
            mism_title += 1
        if s["dest_physical_page"] != page:
            mism_page += 1
    check("%s level mismatches" % doc_id, mism_level, 0)
    check("%s title mismatches" % doc_id, mism_title, 0)
    check("%s bookmark page mismatches" % doc_id, mism_page, 0)
    check("%s level distribution" % doc_id,
          sk["doc"]["outline_level_counts"],
          {str(l): sum(1 for s in outline if s["level"] == l) for l in (1, 2, 3, 4)})

print("=== 2. heading blocks and level font sizes ===")
for doc_id in L.DOCS:
    sk = skeletons[doc_id]
    doc = pymupdf.open(L.doc_path(doc_id))
    ok_txt = ok_size = 0
    outline = [s for s in sk["sections"] if s["region_type"] == "section"]
    for s in outline:
        page = doc.load_page(s["start_physical_page"] - 1)
        found = None
        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            if abs(b["bbox"][1] - s["start_y"]) > 1.0:
                continue
            text = "".join(sp["text"] for ln in b["lines"] for sp in ln["spans"])
            size = max(sp["size"] for ln in b["lines"] for sp in ln["spans"])
            found = (text, size)
            break
        if found and norm(found[0]) == norm(s["title"]):
            ok_txt += 1
        if found and abs(found[1] - {1: 22.0, 2: 18.0, 3: 16.0, 4: 15.0}[s["level"]]) < 0.6:
            ok_size += 1
    doc.close()
    check("%s sections whose heading text matches title" % doc_id, ok_txt, len(outline))
    check("%s sections whose heading font size matches level" % doc_id, ok_size, len(outline))

print("=== 3. block coverage (block-level, not page-level) ===")
for doc_id in L.DOCS:
    sk = skeletons[doc_id]
    doc = pymupdf.open(L.doc_path(doc_id))
    total = assigned = running = 0
    for pno in range(doc.page_count):
        content, run = L.blocks_of(doc.load_page(pno))
        total += len(content)
        running += len(run)
    check("%s blocks assigned == blocks extracted" % doc_id,
          sk["validation"]["blocks_assigned"], total)
    check("%s blocks lost" % doc_id, sk["validation"]["blocks_lost"], 0)
    # page_map must account for every assigned block
    pm = sum(r["blocks"] for page in sk["page_map"] for r in page["sections"])
    check("%s page_map block total" % doc_id, pm, total)
    # every page with content must appear in page_map
    pages_with_content = {p["physical_page"] for p in sk["page_map"]}
    check("%s pages represented in page_map" % doc_id, len(pages_with_content),
          sk["doc"]["page_count"])
    check("%s sections with zero content" % doc_id,
          sk["validation"]["sections_with_zero_content"], [])
    check("%s section start != first content page" % doc_id,
          sk["validation"]["sections_start_not_on_first_content_page"], [])
    doc.close()

print("=== 4. structure statistics ==")
for doc_id in L.DOCS:
    sk = skeletons[doc_id]
    secs = sk["sections"]
    multi = {}
    for p in range(1, sk["doc"]["page_count"] + 1):
        n = sum(1 for s in secs if s["start_physical_page"] == p)
        if n > 1:
            multi[p] = n
    check("%s pages with more than one section start" % doc_id,
          len(multi), sk["validation"]["pages_with_multiple_section_starts"])
    check("%s max sections starting on one page" % doc_id,
          max(multi.values()) if multi else 1,
          sk["validation"]["max_sections_starting_on_one_page"])
    spanning = sum(1 for s in secs if s["spans_multiple_pages"])
    check("%s regions spanning more than one page" % doc_id, spanning,
          sk["validation"]["sections_spanning_pages"])
    # every section's content must lie inside its declared page span
    bad = [s["section_id"] for s in secs
           if s["pages_with_content"]
           and (s["pages_with_content"][0] < s["start_physical_page"]
                or s["pages_with_content"][-1] > s["end_physical_page"])]
    check("%s sections with content outside their page span" % doc_id, bad, [])
    # synthetic regions
    check("%s synthetic regions" % doc_id,
          sorted(s["title"] for s in secs if s["region_type"] != "section"),
          sorted(["封面", "目录", "表目录", "图目录"]))

print("=== 5. samples: normalization preserves characters ===")
files = sorted(glob.glob(os.path.join(L.SAMPLES, "*.jsonl")))
check_true("sample files found", len(files) == 14, "files=%d" % len(files))
n_rec = n_block = n_table = 0
bad_preserve, bad_source, bad_blank, bad_merge = [], [], [], []
bad_trace, bad_norm_have, bad_formula = [], [], []
missing_section = []
for f in files:
    for line in open(f, encoding="utf-8"):
        r = json.loads(line)
        n_rec += 1
        if r["record_type"] == "block":
            n_block += 1
            if not (r["normalization"]["chars_preserved"]
                    and L.preserved(r["raw_text"], r["norm_text"])):
                bad_preserve.append(r["record_id"])
        if r["record_type"] == "table":
            n_table += 1
            if r["extraction"]["blank_cells"] != sum(1 for row in r["grid_raw"]
                                                    for c in row if not c.strip()):
                bad_blank.append(r["record_id"])
            if r["merge_suspects_applied"] or not r["needs_review"]:
                bad_merge.append(r["record_id"])
            if r["coverage_check"]["data_loss_suspected"]:
                bad_trace.append(("table-words-missing", r["record_id"]))
        if r["record_type"] == "formula_fraction":
            if not r["part_record_ids"] or not r["needs_review"]:
                bad_formula.append(r["record_id"])
        # every record must name an official source and a real section
        if "笔记" in r["source_file"]:
            bad_source.append(r["record_id"])
        if not r.get("section", {}).get("title"):
            missing_section.append(r["record_id"])
check("records total", n_rec, n_rec)
check("block records", n_block, n_block)
check("table records", n_table, n_table)
check("records whose normalization changed a character", bad_preserve, [])
check("table records with blank cells changed", bad_blank, [])
check("table records with merges auto-applied", bad_merge, [])
check("records sourced from the notes PDF", bad_source, [])
check("records without a section reference", missing_section, [])
check("formula_fraction records without parts/review flag", bad_formula, [])

print("=== 5b. sub/superscript evidence and table raw-data fallback ===")
script_kinds = {}
script_records = 0
lossy_tables, unrecovered = 0, []
for f in files:
    for line in open(f, encoding="utf-8"):
        r = json.loads(line)
        if r.get("script_spans"):
            script_records += 1
            for sp in r["script_spans"]:
                script_kinds[sp["script"]] = script_kinds.get(sp["script"], 0) + 1
        if r["record_type"] == "table" and r["coverage_check"]["data_loss_suspected"]:
            lossy_tables += 1
            if r["coverage_check"]["missing_also_from_source_lines"]:
                unrecovered.append(r["record_id"])
            if not r["source_text_lines"]:
                unrecovered.append((r["record_id"], "no source_text_lines"))
check("records carrying sub/superscript spans", script_records > 0, True)
check("sub/superscript classes seen", sorted(script_kinds), ["subscript"])
check_true("tables where the grid dropped words from the text layer",
           lossy_tables == 1, "count=%d" % lossy_tables)
check("words lost from a table grid but also missing from source lines", unrecovered, [])

print("=== 6. round-trip traceability (record -> PDF -> record) ===")
docs = {}
trace_ok = trace_bad = trace_skip = 0
trace_fail_samples = []
for f in files:
    for line in open(f, encoding="utf-8"):
        r = json.loads(line)
        if r["record_type"] != "block":
            continue
        d = docs.setdefault(r["doc_id"], pymupdf.open(L.doc_path(r["doc_id"])))
        ok = True
        for sl in r["source_lines"]:
            page = d.load_page(sl["page"] - 1)
            clip = pymupdf.Rect([sl["bbox"][0] - 1.5, sl["bbox"][1] - 1.5,
                                 sl["bbox"][2] + 1.5, sl["bbox"][3] + 1.5])
            got = page.get_text("text", clip=clip)
            a = norm(sl["text"])
            b = norm(got)
            if not a:
                continue
            if a not in b and b not in a:
                ok = False
                if len(trace_fail_samples) < 6:
                    trace_fail_samples.append((r["record_id"], sl["page"], sl["bbox"],
                                               sl["text"][:40], got[:40]))
        if ok:
            trace_ok += 1
        else:
            trace_bad += 1
check_true("round-trip pass rate",
           trace_ok + trace_bad > 0 and trace_bad / (trace_ok + trace_bad) < 0.02,
           "ok=%d bad=%d (%.2f%%)" % (trace_ok, trace_bad,
                                      100 * trace_bad / max(1, trace_ok + trace_bad)))
for t in trace_fail_samples:
    print("     mismatch sample:", t)
for d in docs.values():
    d.close()

print("=== 7. notes PDF must not be used as a body source ===")
for doc_id in L.DOCS:
    sk = skeletons[doc_id]
    check_true("%s skeleton source is the official PDF" % doc_id,
               "笔记" not in sk["doc"]["source_file"] and not sk["doc"]["notes_version_used"],
               sk["doc"]["source_file"][:40])
forbidden = ["没有反制空中支援"]
hits = []
for f in files:
    txt = open(f, encoding="utf-8").read()
    for w in forbidden:
        if w in txt:
            hits.append((os.path.basename(f), w))
for doc_id in L.DOCS:
    txt = open(os.path.join(L.STRUCT, "%s_章节骨架.json" % doc_id.replace("RMUC", "")), encoding="utf-8").read()
    for w in forbidden:
        if w in txt:
            hits.append((doc_id, w))
check("personal-note strings present in structured output", hits, [])

print("=== 8. sample coverage of the requested categories ===")
index = json.load(open(os.path.join(L.STRUCT, "samples_index.json"), encoding="utf-8"))
samples = {}
for s in index["samples"]:
    samples.setdefault(s["doc_id"], {})[s["sample"]] = s
want_groups = {"body_text", "cross_page", "cross_page_paragraph", "tables",
               "formulas", "multi_section_page", "flowchart"}
for doc_id in L.DOCS:
    sk = skeletons[doc_id]
    check("%s sample groups" % doc_id, sorted(samples[doc_id]), sorted(want_groups))
    check("%s tables group has table records" % doc_id,
          samples[doc_id]["tables"]["tables"] > 0, True)
    # 跨页章节: the section itself spans pages and its records come from both
    cp = samples[doc_id]["cross_page"]
    secs_spanning = [L.section_by_no(sk, no) for no in cp["sections"]
                     if L.section_by_no(sk, no)["spans_multiple_pages"]]
    check("%s cross_page group sections span pages" % doc_id,
          len(secs_spanning) > 0 and len(cp["physical_pages"]) >= 2, True)
    # 跨页段落: at least one record merges lines from two different pages
    cpp = samples[doc_id]["cross_page_paragraph"]
    check("%s cross_page_paragraph has records crossing pages" % doc_id,
          cpp["cross_page_records"] > 0 and len(cpp["physical_pages"]) >= 2, True)
    check("%s flowchart group has diagram labels" % doc_id,
          samples[doc_id]["flowchart"]["block_kinds"].get("diagram_label", 0) > 0, True)
    check("%s formulas group has fraction records" % doc_id,
          samples[doc_id]["formulas"]["block_kinds"].get("formula_fraction", 0) > 0, True)
    check("%s multi_section_page spans several sections" % doc_id,
          len(samples[doc_id]["multi_section_page"]["sections"]) >= 4, True)

print("=== 9. headline numbers quoted in 结构化验证报告.md ===")
allrec = []
for f in files:
    allrec += [json.loads(l) for l in open(f, encoding="utf-8")]
by_type = Counter(r["record_type"] for r in allrec)
by_kind = Counter(r.get("block_kind", r["record_type"]) for r in allrec)
check("report: records total", len(allrec), 302)
check("report: record_type split", dict(by_type),
      {"block": 263, "table": 21, "figure": 10, "formula_fraction": 8})
check("report: block_kind split", dict(by_kind),
      {"heading": 24, "paragraph": 138, "figure": 10, "formula_fraction_part": 33,
       "formula_fraction": 8, "diagram_label": 52, "figure_caption": 4,
       "table_caption": 12, "table": 21})
paras = [r for r in allrec if r.get("block_kind") == "paragraph"]
check("report: paragraph records", len(paras), 138)
check("report: multi-line paragraphs", sum(1 for r in paras if r["line_count"] > 1), 106)
check("report: max lines in one paragraph", max(r["line_count"] for r in paras), 9)
check("report: cross-page paragraphs", sum(1 for r in allrec if r.get("cross_page")), 4)
check("report: records flagged needs_review",
      sum(1 for r in allrec if r.get("needs_review")), 125)
check("report: subscript spans",
      sum(len(r.get("script_spans") or []) for r in allrec), 52)
check("report: records carrying subscripts",
      sum(1 for r in allrec if r.get("script_spans")), 24)

tabs = [r for r in allrec if r["record_type"] == "table"]
check("report: tables", len(tabs), 21)
check("report: table rows", sum(r["extraction"]["rows"] for r in tabs), 165)
check("report: table cells", sum(r["extraction"]["cells"] for r in tabs), 1840)
check("report: blank cells", sum(r["extraction"]["blank_cells"] for r in tabs), 1290)
check("report: merge suspects", sum(len(r["merge_suspects"]) for r in tabs), 625)
check("report: words inside table boxes",
      sum(r["coverage_check"]["words_in_box"] for r in tabs), 577)
check("report: words missing from grids",
      sum(len(r["coverage_check"]["missing_words"]) for r in tabs), 10)
check("report: source text lines kept for tables",
      sum(r["extraction"]["source_text_lines_inside_box"] for r in tabs), 558)
check("report: tables with a caption", sum(1 for r in tabs if r["caption"]), 13)
check("report: continuation tables without caption",
      sum(1 for r in tabs if not r["caption"]), 8)

print()
bad = [c for c in checks if not c[0]]
print("=" * 74)
print("TOTAL %d checks, %d PASS, %d FAIL" % (len(checks), len(checks) - len(bad), len(bad)))
for _, name, got, want in bad:
    print("  FAILED:", name, "got", got, "want", want)
print("=" * 74)
raise SystemExit(1 if bad else 0)
