#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 5 (phase B2) -- step 4: independent verification of the B2 outputs."""
import os
import re
import sys
import json
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b2_lib as L

checks = []


def check(name, got, want):
    ok = got == want
    checks.append((ok, name, got, want))
    g = ("<%d items>" % len(got)) if isinstance(got, (list, set)) and len(got) > 6 else repr(got)
    w = ("<%d items>" % len(want)) if isinstance(want, (list, set)) and len(want) > 6 else repr(want)
    print(("PASS " if ok else "FAIL ") + "%-58s got=%s want=%s" % (name, g, w))
    return ok


def check_true(name, cond, detail=""):
    checks.append((bool(cond), name, detail, True))
    print(("PASS " if cond else "FAIL ") + "%-58s %s" % (name, detail))
    return bool(cond)


def main():
    diffs = L.load_jsonl(os.path.join(L.OUT, "全文候选差异.jsonl"))
    status = L.load_jsonl(os.path.join(L.OUT, "差异覆盖状态.jsonl"))
    body = L.load_json(os.path.join(L.OUT, "b2_body_stats.json"))
    sp = L.load_json(os.path.join(L.OUT, "special_diff.json"))
    align = L.load_json(os.path.join(L.ALIGN, "章节对应关系.json"))
    recs26 = L.load_jsonl(os.path.join(L.STRUCT, "2026_结构化.jsonl"))
    recs27 = L.load_jsonl(os.path.join(L.STRUCT, "2027_结构化.jsonl"))

    # ---------- 1. diff record integrity ----------
    ids = [r["diff_id"] for r in diffs]
    check("diff_id unique", len(set(ids)), len(ids))
    check("diff_id sequential", ids, ["D%05d" % i for i in range(1, len(diffs) + 1)])
    bad_type = [r["diff_id"] for r in diffs if r["diff_type"] not in L.DIFF_TYPES]
    check("diff_type in the allowed vocabulary", bad_type, [])
    bad_side = [r["diff_id"] for r in diffs if not r["a"] and not r["b"]]
    check("records without either side", bad_side, [])
    bad_ver = [r["diff_id"] for r in diffs if r.get("verify_status") != "unverified"]
    check("all records still unverified", bad_ver, [])
    one_side = [r["diff_id"] for r in diffs
                if r["diff_type"] in ("内容一致", "文字调整候选", "实质修改候选")
                and not (r["a"] and r["b"])]
    check("paired types have both sides", one_side, [])
    del_no_a = [r["diff_id"] for r in diffs if r["diff_type"] == "删除候选" and not r["a"]]
    add_no_b = [r["diff_id"] for r in diffs if r["diff_type"] == "新增候选" and not r["b"]]
    check("delete candidates carry the 2026 side", del_no_a, [])
    check("add candidates carry the 2027 side", add_no_b, [])
    missing_trace = [r["diff_id"] for r in diffs
                     if (r["a"] and not (r["a"].get("record_id") and r["a"].get("physical_page")))
                     or (r["b"] and not (r["b"].get("record_id") and r["b"].get("physical_page")))]
    check("every side has record_id + page", missing_trace, [])

    # ---------- 2. sentence coverage: each sentence used at most once ----------
    used = Counter()
    for r in diffs:
        for k in ("a", "b"):
            sd = r[k]
            if not sd:
                continue
            used[(sd["doc"], sd["record_id"], sd["block_index_in_para"])] += 1
    dup = [k for k, v in used.items() if v > 1]
    check("a sentence bound to more than one diff", dup, [])
    check("sentences used == corpus total",
          len(used), body["sentences_2026"] + body["sentences_2027"])

    # ---------- 3. record status coverage ----------
    check("status records == all structured records", len(status),
          len(recs26) + len(recs27))
    bad_state = [r["record_id"] for r in status
                 if r["status"] in ("未进入比对（异常）", "未分类（异常）")]
    check("records with an anomaly status", bad_state, [])
    body_kinds = L.BODY_KINDS
    need = [(r["doc_id"], r["record_id"]) for r in recs26 + recs27
            if r.get("block_kind") in body_kinds and r.get("region_type") == "section"
            and (r.get("norm_text") or "").strip()]
    have = {(r["doc"], r["record_id"]) for r in status
            if r["status"] in ("全部一致", "仅含轻度候选差异", "含实质候选差异",
                               "无可比对文本（仅符号/空白）")}
    check("body records without a comparison status", sorted(set(need) - have), [])

    # ---------- 4. statistics reconciliation ----------
    both = [r for r in diffs if r["a"] and r["b"]]
    check("matched pairs == records with both sides", len(both), body["matched_pairs"])
    tc = Counter(r["diff_type"] for r in diffs)
    check("diff_by_type reconciles", dict(tc), dict(body["diff_by_type"]))
    check("deleted candidates", tc.get("删除候选", 0), body["deleted_candidates"])
    check("added candidates", tc.get("新增候选", 0), body["added_candidates"])
    check("unchanged pairs retained", tc.get("内容一致", 0) > 0, True)

    # ---------- 5. delete/add candidates carry full-text verification ----------
    bad_ev = []
    for r in diffs:
        if r["diff_type"] in ("删除候选", "新增候选"):
            ev = r["evidence"] or {}
            if "fulltext_best_similarity" not in ev:
                bad_ev.append(r["diff_id"])
    check("delete/add candidates carry full-text best similarity", bad_ev, [])

    # ---------- 6. special content coverage ----------
    n_tab_raw = sum(1 for r in recs26 + recs27 if r["record_type"] == "table")
    check("table raw records == coverage rows", len(sp["table_coverage"]), n_tab_raw)
    check("table raw records (83 + 71)", n_tab_raw, 154)
    n_fig = sum(1 for r in recs26 + recs27
                if r.get("block_kind") == "figure" and r.get("region_type") == "section")
    check("figure records == coverage rows", len(sp["figure_coverage"]), n_fig)
    check("figure records (95 + 81)", n_fig, 176)
    n_frac = sum(1 for r in recs26 + recs27 if r.get("block_kind") == "formula_fraction")
    n_span = sum(1 for r in recs26 + recs27 if r.get("script_spans"))
    check("formula coverage rows", len(sp["formula_coverage"]), n_frac + n_span)
    check("fractions (11 + 15)", n_frac, 26)
    check("script-span records", n_span, 46)
    bad_cov = [r["record_id"] for r in sp["table_coverage"]
               if r["compare_status"] == "未比对（异常）"]
    check("tables without a compare status", bad_cov, [])
    bad_fcov = [r["record_id"] for r in sp["figure_coverage"]
                if r["compare_status"] == "未比对（异常）"]
    check("figures without a compare status", bad_fcov, [])
    bad_xcov = [r["record_id"] for r in sp["formula_coverage"]
                if r["compare_status"] == "未比对（异常）"]
    check("formulas without a compare status", bad_xcov, [])

    # ---------- 7. special diff rows are traceable ----------
    bad_t = [i for i, r in enumerate(sp["tables"]["rows"])
             if not (r.get("table_2026") or r.get("table_2027"))]
    check("table diff rows without a side", bad_t, [])
    bad_f = [i for i, r in enumerate(sp["figures"]["rows"])
             if not (r.get("figure_2026") or r.get("figure_2027"))]
    check("figure diff rows without a side", bad_f, [])
    bad_x = [i for i, r in enumerate(sp["formulas"]["rows"])
             if not (r.get("formula_2026") or r.get("formula_2027"))]
    check("formula diff rows without a side", bad_x, [])

    # ---------- 8. deliverables exist and avoid forbidden wording ----------
    files = ["全文候选差异.jsonl", "全文差异总览.md", "特殊内容差异清单.md",
             "差异覆盖与质量报告.md", "待人工核验的重点差异.md",
             "差异覆盖状态.jsonl", "special_diff.json", "b2_body_stats.json"]
    missing_files = [f for f in files if not os.path.exists(os.path.join(L.OUT, f))]
    check("deliverables missing", missing_files, [])
    FORBID = re.compile(r"已确认(新增|删除|变更)|毫无疑问|完全一致(=|，)规则")
    hits = []
    for f in files:
        if not f.endswith(".md"):
            continue
        txt = open(os.path.join(L.OUT, f), encoding="utf-8").read()
        for m in FORBID.finditer(txt):
            hits.append((f, m.group(0)))
    check("forbidden 'confirmed' wording in reports", hits, [])

    # ---------- 9. chapter coverage in the overview ----------
    ov = open(os.path.join(L.OUT, "全文差异总览.md"), encoding="utf-8").read()
    # same chapter key as the report: the 2026 chapter of the alignment unit,
    # falling back to the 2027 chapter for units that exist only in 2027
    chapters = []
    for u in align["alignments"]:
        if u["sections_2026"]:
            p0 = u["sections_2026"][0]["path"]
            c = p0[0] if p0 else u["sections_2026"][0]["title"]
        elif u["sections_2027"]:
            p0 = u["sections_2027"][0]["path"]
            c = p0[0] if p0 else u["sections_2027"][0]["title"]
        else:
            continue
        if c not in chapters:
            chapters.append(c)
    miss_ch = [c for c in chapters if c not in ov]
    check("chapters missing from 全文差异总览.md", miss_ch, [])

    # ---------- 10. phase-A input intact ----------
    check("phase-A 2026 record count", len(recs26), 1853)
    check("phase-A 2027 record count", len(recs27), 1785)
    check("B1 alignment units", len(align["alignments"]), 135)
    sha = json.load(open(os.path.join(L.STRUCT, "fulltext_summary.json"), encoding="utf-8"))
    ok_sha = True
    for k, v in sha["summary"].items():
        if v["records"] != len(recs26 if k == "RMUC2026" else recs27):
            ok_sha = False
    check_true("phase-A summary still matches the data", ok_sha)

    print()
    bad = [c for c in checks if not c[0]]
    print("=" * 76)
    print("TOTAL %d checks, %d PASS, %d FAIL" % (len(checks), len(checks) - len(bad), len(bad)))
    for _, name, got, want in bad:
        print("  FAILED:", name, "got", got, "want", want)
    print("=" * 76)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
