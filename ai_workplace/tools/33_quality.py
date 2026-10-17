#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 3 -- automatic quality checks over the full-document output.

Produces:
  * ai_workplace/structured/quality_checks.json   (all numbers)
  * ai_workplace/structured/待人工核验清单.jsonl    (one line per item to review)

Checks: section attribution, record completeness, duplicates, missing lines,
cross-page records, character fidelity, number/unit/formula preservation,
table raw-text coverage, Markdown view completeness, and a regression against
the task-2 validated samples.

Read-only on the PDFs.
"""
import os
import re
import json
import glob
from collections import Counter, defaultdict

import pymupdf

import struct_lib as L

AUD = L.AUD
checks = []
headline = {}


def check(name, got, want):
    ok = got == want
    checks.append((ok, name, got, want))
    g = ("<%d items>" % len(got)) if isinstance(got, list) and len(got) > 6 else repr(got)
    w = ("<%d items>" % len(want)) if isinstance(want, list) and len(want) > 6 else repr(want)
    print(("PASS " if ok else "FAIL ") + "%-58s got=%s want=%s" % (name, g, w))
    return ok


def check_true(name, cond, detail=""):
    checks.append((bool(cond), name, detail, True))
    print(("PASS " if cond else "FAIL ") + "%-58s %s" % (name, detail))
    return bool(cond)


NUM = re.compile(r"\d+(?:\.\d+)?")
UNITS = re.compile(r"(?:mm/s|mm|m/s|rad/s|°/s|°|℃|%|Hz|kHz|kW|W|J|V|A|ms|min|s)(?![A-Za-z])")
FORMULA = re.compile(r"[=<>≤≥≠±×÷*/^√∑∏∫∞≈~]")
GREEK = re.compile(r"[α-ωΑ-ΩπΔΣ∑√]")
MATH_ALNUM = re.compile(r"[\U0001D400-\U0001D7FF]")


def nonspace(s):
    return re.sub(r"\s+", "", L.normalize([s]) if "\n" in s else s)


def load_all(doc_id):
    year = doc_id.replace("RMUC", "")
    return [json.loads(l) for l in
            open(os.path.join(L.STRUCT, "%s_结构化.jsonl" % year), encoding="utf-8")]


def main():
    summary = json.load(open(os.path.join(L.STRUCT, "fulltext_summary.json"), encoding="utf-8"))
    hier = {}
    for doc_id in L.DOCS:
        sk = L.load_skeleton(doc_id)
        doc = pymupdf.open(L.doc_path(doc_id))
        toc = doc.get_toc(simple=False)
        doc.close()
        hier[doc_id] = dict(skeleton=sk, toc=toc)
        h = L.validate_hierarchy(sk["sections"], toc)
        hier[doc_id]["h"] = h
        check("%s hierarchy check ok" % doc_id, h["ok"], True)
        check("%s hierarchy problems" % doc_id, len(h["problems"]), 0)
        check("%s sections checked" % doc_id, h["sections_checked"],
              sk["validation"]["outline_sections"])
        check("%s max path depth" % doc_id, h["max_depth"], 4)

    allrecs = {d: load_all(d) for d in L.DOCS}
    review_items = []

    for doc_id, recs in allrecs.items():
        print("\n=== %s ===" % doc_id)
        sk = hier[doc_id]["skeleton"]
        secs = {s["section_id"]: s for s in sk["sections"]}
        scan = summary["summary"][doc_id]["scan"]
        pfx = doc_id + ":"

        # ---------------- 1. completeness / duplicates ----------------
        check("%s record_index contiguous" % doc_id,
              [r["record_index"] for r in recs], list(range(len(recs))))
        ids = [r["record_id"] for r in recs]
        check("%s duplicate record_id" % doc_id,
              [k for k, v in Counter(ids).items() if v > 1], [])
        check("%s distinct sections with records" % doc_id,
              len({r["section_index"] for r in recs}), len(secs))
        missing_secs = [sid for sid in secs if sid not in {r["section_index"] for r in recs}]
        check("%s sections without any record" % doc_id, missing_secs, [])

        # ---------------- 2. attribution ----------------
        bad_attr = []
        bad_sec_ref = []
        for r in recs:
            s = secs[r["section_index"]]
            if r.get("source_lines") and r.get("cross_page"):
                sl0 = r["source_lines"][0]
                pos = (sl0["page"], sl0["bbox"][1])
            else:
                pos = (r["physical_page"], r["bbox"][1])
            lo = (s["start_physical_page"], s["start_y"])
            hi = (s["end_physical_page"], s["end_y"])
            if not (lo <= pos <= hi):
                bad_attr.append(r["record_id"])
            if (r["section"]["section_no"] != s["section_no"]
                    or r["section"]["title"] != s["title"]
                    or r["section"]["path"] != s["path"]):
                bad_sec_ref.append(r["record_id"])
            if r["printed_page"] != r["physical_page"] + L.PRINTED_OFFSET:
                bad_attr.append(("printed_page", r["record_id"]))
        check("%s records outside their section span" % doc_id, bad_attr[:20], [])
        check("%s section reference mismatch" % doc_id, bad_sec_ref, [])

        # ---------------- 3. line accounting (no lost / duplicated line) ----
        line_recs = [r for r in recs if r.get("source_lines")]
        n_lines = sum(len(r["source_lines"]) for r in line_recs)
        check("%s source lines == kept lines" % doc_id, n_lines, scan["lines_kept"])
        seen = Counter()
        for r in line_recs:
            for sl in r["source_lines"]:
                seen[(sl["page"], tuple(sl["bbox"]))] += 1
        dup = [k for k, v in seen.items() if v > 1]
        check("%s lines used by more than one record" % doc_id, dup[:10], [])
        check("%s total text lines accounted" % doc_id,
              scan["lines_kept"] + scan["lines_in_tables"], scan["text_lines"])

        # ---------------- 4. cross-page ----------------
        cross = [r for r in recs if r.get("cross_page")]
        bad_cross = []
        for r in cross:
            pages = sorted({sl["page"] for sl in r["source_lines"]})
            if len(pages) < 2 or pages[-1] - pages[0] + 1 != len(pages):
                bad_cross.append(r["record_id"])       # non-consecutive page coverage
        check("%s cross-page records" % doc_id, len(cross) > 0, True)
        check("%s malformed cross-page records" % doc_id, bad_cross, [])
        check("%s cross-page records carrying per-page bbox" % doc_id,
              all(r.get("bbox_by_page") for r in cross), True)

        # ---------------- 5. character fidelity + numbers/units/formula ----
        bad_pres, bad_num, bad_unit, bad_formula, bad_greek = [], [], [], [], []
        for r in recs:
            if not r.get("normalization"):
                continue
            raw, nrm = r["raw_text"], r["norm_text"]
            if not (r["normalization"]["chars_preserved"] and L.preserved(raw, nrm)):
                bad_pres.append(r["record_id"])
                continue
            if Counter(NUM.findall(raw)) != Counter(NUM.findall(nrm)):
                bad_num.append(r["record_id"])
            if Counter(UNITS.findall(raw)) != Counter(UNITS.findall(nrm)):
                bad_unit.append(r["record_id"])
            if Counter(FORMULA.findall(raw)) != Counter(FORMULA.findall(nrm)):
                bad_formula.append(r["record_id"])
            if Counter(GREEK.findall(raw)) != Counter(GREEK.findall(nrm)):
                bad_greek.append(r["record_id"])
        check("%s records failing character fidelity" % doc_id, bad_pres, [])
        check("%s records with changed numbers" % doc_id, bad_num, [])
        check("%s records with changed units" % doc_id, bad_unit, [])
        check("%s records with changed formula/operators" % doc_id, bad_formula, [])
        check("%s records with changed greek/formula chars" % doc_id, bad_greek, [])

        # ---- independent re-extraction: each line must exist in page text ----
        doc = pymupdf.open(L.doc_path(doc_id))
        page_cache = {}
        bad_indep = []
        for r in line_recs:
            for sl in r["source_lines"]:
                page = sl["page"]
                if page not in page_cache:
                    page_cache[page] = re.sub(r"\s+", "", doc.load_page(page - 1).get_text("text"))
                if re.sub(r"\s+", "", sl["text"]) not in page_cache[page]:
                    bad_indep.append((r["record_id"], sl["page"], sl["text"][:30]))
        doc.close()
        check("%s lines not found in the page's own text extraction" % doc_id,
              bad_indep[:10], [])

        # ---------------- 6. tables ----------------
        tabs = [r for r in recs if r["record_type"] == "table"]
        t_stat = dict(tables=len(tabs),
                      cells=sum(r["extraction"]["cells"] for r in tabs),
                      blank=sum(r["extraction"]["blank_cells"] for r in tabs),
                      suspects=sum(len(r["merge_suspects"]) for r in tabs),
                      words=sum(r["coverage_check"]["words_in_box"] for r in tabs),
                      missing_grid=sum(r["coverage_check"]["missing_from_grid"] for r in tabs),
                      source_lines=sum(r["extraction"]["source_text_lines_inside_box"] for r in tabs),
                      captioned=sum(1 for r in tabs if r.get("caption_status") == "captioned"),
                      no_caption=sum(1 for r in tabs if r.get("caption_status") == "no_caption"))
        loss = [r for r in tabs if r["coverage_check"]["data_loss_suspected"]]
        t_stat["tables_with_grid_loss"] = len(loss)
        t_stat["missing_recovered_by_source_lines"] = all(
            not r["coverage_check"]["missing_also_from_source_lines"] for r in tabs)
        t_stat["grid_blank_consistent"] = all(
            r["extraction"]["blank_cells"] == sum(1 for row in r["grid_raw"] for c in row if not c.strip())
            for r in tabs)
        t_stat["merges_never_applied"] = all(not r["merge_suspects_applied"] for r in tabs)
        headline["%s_tables" % doc_id] = t_stat
        check("%s table grid blank count consistent" % doc_id,
              t_stat["grid_blank_consistent"], True)
        check("%s merge cells never auto-applied" % doc_id,
              t_stat["merges_never_applied"], True)
        check("%s table words recovered by source lines" % doc_id,
              t_stat["missing_recovered_by_source_lines"], True)

        # ---------------- 7. formulas / images / diagram labels --------
        subs = [r for r in recs if r.get("script_spans")]
        frac = [r for r in recs if r["record_type"] == "formula_fraction"]
        diag = [r for r in recs if r.get("block_kind") == "diagram_label"]
        figs = [r for r in recs if r.get("block_kind") == "figure"]
        icons = [r for r in recs if r.get("block_kind") == "inline_icon"]
        f_stat = dict(subscript_spans=sum(len(r["script_spans"]) for r in subs),
                      records_with_subscript=len(subs),
                      subscript_kinds=dict(Counter(sp["script"] for r in subs for sp in r["script_spans"])),
                      fractions=len(frac),
                      fraction_parts=sum(len(r["part_record_ids"]) for r in frac),
                      diagram_labels=len(diag),
                      figures=len(figs), inline_icons=len(icons),
                      figures_with_semantics=sum(1 for r in figs if r["flags"]["semantic_content_extracted"]),
                      fraction_all_review=all(r["needs_review"] for r in frac),
                      diagram_all_review=all(r["needs_review"] for r in diag))
        headline["%s_formulas_images" % doc_id] = f_stat
        headline["%s_layout_kinds" % doc_id] = dict(
            figure_label_row=sum(1 for r in recs if r.get("block_kind") == "figure_label_row"),
            index_entry=sum(1 for r in recs if r.get("block_kind") == "index_entry"),
            cover_text=sum(1 for r in recs if r.get("block_kind") == "cover_text"),
            math_alphanumeric=sum(1 for r in recs
                                 if MATH_ALNUM.search((r.get("norm_text") or "") + "".join("".join(x) for x in (r.get("grid_raw") or [])))),
            cross_page=len(cross))
        check("%s sub/superscript spans found" % doc_id,
              f_stat["subscript_kinds"].get("subscript", 0) > 0, True)
        # every script label must be consistent with its own geometry
        bad_script = []
        for r in recs:
            for sp in (r.get("script_spans") or []):
                ratio = sp["size"] / sp["base_size"]
                dy = sp["baseline_dy"]
                lab = sp["script"]
                ok_lab = ((lab == "subscript" and dy > 0.8 and ratio < 0.85)
                          or (lab == "superscript" and dy < -0.8 and ratio < 0.85)
                          or (lab == "small" and abs(dy) <= 0.8 and ratio < 0.85))
                if not ok_lab:
                    bad_script.append((r["record_id"], sp))
        check("%s script labels inconsistent with geometry" % doc_id, bad_script[:5], [])
        check("%s fractions flagged for review" % doc_id, f_stat["fraction_all_review"], True)
        check("%s diagram labels flagged for review" % doc_id, f_stat["diagram_all_review"], True)
        check("%s figures without semantic extraction" % doc_id,
              f_stat["figures_with_semantics"], 0)

        # ---------------- 8. review list ----------------
        for r in recs:
            if not r.get("needs_review"):
                continue
            kind = r.get("block_kind", r["record_type"])
            cat, prio, action = {
                "table": ("table_merge", "medium",
                          "按 merge_suspects 还原合并单元格；核对等级/数值的列归属"),
                "formula_fraction": ("formula_fraction", "medium",
                                     "按 part_record_ids 把分子/分母/片段拼回一行公式"),
                "formula_fraction_part": ("formula_fraction_part", "medium",
                                          "分式片段，配合所属 formula_fraction 记录还原"),
                "diagram_label": ("diagram_label", "medium",
                                  "流程图/图例文字，语义需人工读渲染图确认"),
                "figure": ("figure_content", "low", "按 bbox 裁剪渲染图后人工阅读"),
                "inline_icon": ("inline_icon", "low", "小图标，仅确认是否需引用"),
                "cover_text": ("cover_text_garbled", "low",
                               "封面文本层乱码，不作为正文；封面信息以渲染图为准"),
                "paragraph": ("paragraph_boundary", "medium",
                              "检查该段落在图例行处是否应断开"),
            }.get(kind, ("other", "medium", "人工确认"))
            if r["record_type"] == "table" and r["coverage_check"]["data_loss_suspected"]:
                cat, prio, action = ("table_grid_loss", "high",
                                     "用 source_text_lines 把缺失的单元格补回网格")
            review_items.append(dict(
                doc_id=doc_id, category=cat, priority=prio,
                record_id=r["record_id"],
                physical_page=r["physical_page"], printed_page=r["printed_page"],
                section_no=r["section"]["section_no"], section_title=r["section"]["title"],
                section_path=r["section"]["path"],
                block_kind=kind, bbox=r["bbox"],
                snippet=(r.get("norm_text") or r.get("caption") or "")[:120],
                reason=r.get("review_note", ""),
                suggested_action=action,
                detail=dict(
                    table_no=r.get("table_no"),
                    blank_ratio=(r.get("extraction") or {}).get("blank_ratio"),
                    merge_suspects=len(r.get("merge_suspects") or []),
                    missing_words=(r.get("coverage_check") or {}).get("missing_words"),
                    numerator=r.get("numerator_text"),
                    denominator=r.get("denominator_text"),
                    parts=len(r.get("part_record_ids") or []),
                    image_pt=(r.get("image_info") or {}).get("box_pt"),
                ),
            ))

        # ---- extra: notation risks the extractor deliberately does not "fix" ----
        for r in recs:
            txt = (r.get("norm_text") or "") \
                + "".join("".join(row) for row in (r.get("grid_raw") or []))
            if MATH_ALNUM.search(txt):
                review_items.append(dict(
                    doc_id=doc_id, category="font_math_alphanumeric", priority="medium",
                    record_id=r["record_id"], physical_page=r["physical_page"],
                    printed_page=r["printed_page"], section_no=r["section"]["section_no"],
                    section_title=r["section"]["title"], section_path=r["section"]["path"],
                    block_kind=r.get("block_kind", r["record_type"]), bbox=r["bbox"],
                    snippet=txt[:120],
                    reason="文本使用了 Mathematical Alphanumeric Symbols（U+1D400–U+1D7FF）字体映射，"
                           "例如 𝑠𝑠𝑠𝑠𝑠𝑠 / 𝟏𝟏𝟏𝟏；字符已原样保留，未做任何转换",
                    suggested_action="比对阶段如需按 ASCII 匹配，应在展示层做一次可回滚的兼容映射"
                                      "（不得修改结构化主数据）",
                    detail=dict(math_symbols=sorted({c for c in txt if MATH_ALNUM.match(c)})[:8])))

    # ---------------- 10. Markdown view completeness ----------------
    print()
    for doc_id, recs in allrecs.items():
        year = doc_id.replace("RMUC", "")
        md = open(os.path.join(L.STRUCT, "%s_结构化.md" % year), encoding="utf-8").read()
        md_unesc = re.sub(r"\\(.)", r"\1", md)
        md_norm = re.sub(r"\s+", "", md_unesc)
        missing, missing_id = [], []
        for r in recs:
            if r.get("block_kind") == "heading":
                continue
            if r.get("norm_text"):
                # the text itself must survive the rendering (escaping aside)
                if re.sub(r"\s+", "", r["norm_text"]) not in md_norm:
                    missing.append(r["record_id"])
            elif r["record_id"] not in md:
                missing_id.append(r["record_id"])
        check("%s record text missing from the Markdown view" % doc_id, missing[:10], [])
        check("%s record id missing from the Markdown view" % doc_id, missing_id[:10], [])
        headline["%s_markdown" % doc_id] = dict(
            bytes=os.path.getsize(os.path.join(L.STRUCT, "%s_结构化.md" % year)),
            records_rendered=len(recs) - sum(1 for r in recs if r.get("block_kind") == "heading"),
            text_missing=len(missing), id_missing=len(missing_id))

    # ---------------- 11. compatibility with the task-2 samples ----------------
    # The task-2 sample files are kept untouched (they are validation artefacts).
    # The full run intentionally differs in three refined decisions
    # (figure_label_row split, baseline ordering, table fill filter), so the
    # meaningful invariant is: every original line the samples covered must still
    # be present verbatim in the full output.
    print()
    index = json.load(open(os.path.join(L.STRUCT, "samples_index.json"), encoding="utf-8"))
    for doc_id, recs in allrecs.items():
        units = set()
        for r in recs:
            for sl in r.get("source_lines") or []:
                units.add((sl["page"], tuple(sl["bbox"]), sl["text"]))
            if r["record_type"] == "table":
                for sl in r.get("source_text_lines") or []:
                    units.add((sl["page"], tuple(sl["bbox"]), sl["text"]))
        sample_units, sample_recs = 0, 0
        lost = []
        for s in index["samples"]:
            if s["doc_id"] != doc_id:
                continue
            f = os.path.join(L.ROOT, s["file"].replace("/", os.sep))
            for line in open(f, encoding="utf-8"):
                r = json.loads(line)
                sample_recs += 1
                for sl in r.get("source_lines") or []:
                    sample_units += 1
                    if (sl["page"], tuple(sl["bbox"]), sl["text"]) not in units:
                        lost.append((r["record_id"], sl["page"], sl["text"][:30]))
                if r["record_type"] == "table":
                    for sl in r.get("source_text_lines") or []:
                        sample_units += 1
                        if (sl["page"], tuple(sl["bbox"]), sl["text"]) not in units:
                            lost.append((r["record_id"], sl["page"], sl["text"][:30]))
        check("%s sample text units lost by the full run" % doc_id, lost[:10], [])
        headline["%s_sample_compat" % doc_id] = dict(sample_records=sample_recs,
                                                     text_units=sample_units, lost=len(lost))

    # ---------------- 12. notes version never used ----------------
    forbidden = ["没有反制空中支援"]
    hits = []
    for doc_id, recs in allrecs.items():
        if "笔记" in recs[0]["source_file"]:
            hits.append((doc_id, "notes source"))
        txt = open(os.path.join(L.STRUCT, "%s_结构化.jsonl" % doc_id.replace("RMUC", "")),
                   encoding="utf-8").read()
        for w in forbidden:
            if w in txt:
                hits.append((doc_id, w))
    check("notes-version content in the structured output", hits, [])

    # ---------------- write outputs ----------------
    review_items.sort(key=lambda r: ({"high": 0, "medium": 1, "low": 2}[r["priority"]],
                                     r["doc_id"], r["physical_page"], r["record_id"]))
    with open(os.path.join(L.STRUCT, "待人工核验清单.jsonl"), "w", encoding="utf-8") as fh:
        for it in review_items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")

    cat_count = Counter((i["doc_id"], i["category"], i["priority"]) for i in review_items)
    out = dict(generated=__import__("datetime").datetime.now().isoformat(timespec="seconds"),
               checks_total=len(checks),
               checks_pass=sum(1 for c in checks if c[0]),
               checks_fail=sum(1 for c in checks if not c[0]),
               failed=[c[1] for c in checks if not c[0]],
               headline=headline,
               review_items=len(review_items),
               review_by_category=[dict(doc_id=k[0], category=k[1], priority=k[2], count=v)
                                   for k, v in sorted(cat_count.items())],
               records={d: len(r) for d, r in allrecs.items()})
    json.dump(out, open(os.path.join(L.STRUCT, "quality_checks.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print()
    print("review items: %d" % len(review_items))
    for k, v in sorted(cat_count.items()):
        print("   %-9s %-22s %-6s %d" % (k[0], k[1], k[2], v))
    bad = [c for c in checks if not c[0]]
    print()
    print("=" * 74)
    print("TOTAL %d checks, %d PASS, %d FAIL" % (len(checks), len(checks) - len(bad), len(bad)))
    for _, name, got, want in bad:
        print("  FAILED:", name, "got", got, "want", want)
    print("=" * 74)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
