#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 6 (phase C) -- step 5: independent verification of the semantic output.

The important one is the anti-fabrication check: every quoted rule text and every
record_id in 规则变更候选.jsonl must trace back to a real B2 difference record and to
a real phase-A record.
"""
import os
import re
import sys
import json
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b2_lib as L

SEM = os.path.join(L.ROOT, "ai_workplace", "semantic")
VOCAB = {"实质新增", "实质取消", "规则修改", "规则继承或迁移", "机制重构", "仅表述调整", "证据不足"}
checks = []


def check(name, got, want):
    ok = got == want
    checks.append((ok, name, got, want))
    g = ("<%d items>" % len(got)) if isinstance(got, (list, set, dict)) and len(got) > 6 else repr(got)
    w = ("<%d items>" % len(want)) if isinstance(want, (list, set, dict)) and len(want) > 6 else repr(want)
    print(("PASS " if ok else "FAIL ") + "%-58s got=%s want=%s" % (name, g, w))
    return ok


def check_true(name, cond, detail=""):
    checks.append((bool(cond), name, detail, True))
    print(("PASS " if cond else "FAIL ") + "%-58s %s" % (name, detail))
    return bool(cond)


def main():
    events = L.load_jsonl(os.path.join(SEM, "规则变更候选.jsonl"))
    cov = L.load_json(os.path.join(SEM, "coverage.json"))
    pair = L.load_json(os.path.join(SEM, "配对复核记录.json"))
    diffs = L.load_jsonl(os.path.join(L.OUT, "全文候选差异.jsonl"))
    sp = L.load_json(os.path.join(L.OUT, "special_diff.json"))
    recs26 = L.load_jsonl(os.path.join(L.STRUCT, "2026_结构化.jsonl"))
    recs27 = L.load_jsonl(os.path.join(L.STRUCT, "2027_结构化.jsonl"))
    align = L.load_json(os.path.join(L.ALIGN, "章节对应关系.json"))
    by_id = {r["diff_id"]: r for r in diffs}
    recmap = {}
    for r in recs26 + recs27:
        recmap[r["record_id"]] = r
    CHANGE = ("实质修改候选", "新增候选", "删除候选", "迁移或重组候选", "文字调整候选")
    change = [r for r in diffs if r["diff_type"] in CHANGE]

    # ---------- 1. event structural integrity ----------
    ids = [e["event_id"] for e in events]
    check("event_id unique", len(set(ids)), len(ids))
    bad_vocab = [(e["event_id"], e["change_type"]) for e in events
                 if e["change_type"] not in VOCAB]
    check("change_type in the C2 vocabulary", bad_vocab, [])
    bad_ev = [(e["event_id"], e["evidence_strength"]) for e in events
              if e["evidence_strength"] not in ("strong", "medium", "weak")]
    check("evidence_strength valid", bad_ev, [])
    bad_ver = [e["event_id"] for e in events if e["verify_status"] != "unverified"]
    check("all events still unverified", bad_ver, [])
    empty = [e["event_id"] for e in events
             if not e["diff_ids"] or (not e["rule_2026"]["texts"] and not e["rule_2027"]["texts"])]
    check("events without diffs or without any rule text", empty, [])
    no_sum = [e["event_id"] for e in events if len(e.get("summary") or "") < 10]
    check("events without a judgment summary", no_sum, [])

    # ---------- 2. every change diff assigned exactly once ----------
    seen = Counter()
    for e in events:
        for d in e["diff_ids"]:
            seen[d] += 1
    dup = [d for d, v in seen.items() if v > 1]
    check("diff assigned to more than one event", dup, [])
    unknown = [d for d in seen if d not in by_id]
    check("unknown diff_id in events", unknown, [])
    missing = sorted({r["diff_id"] for r in change} - set(seen))
    check("change diffs missing from events", missing, [])
    check("all change diffs covered", len(seen), len(change))
    non_change = [d for d in seen if by_id[d]["diff_type"] not in CHANGE]
    check("non-change diffs used in events", non_change, [])

    # ---------- 3. anti-fabrication: quotes must equal the B2 side text ----------
    bad_quote, checked = [], 0
    for e in events:
        rows = [by_id[d] for d in e["diff_ids"] if d in by_id]
        for side, key in (("2026", "a"), ("2027", "b")):
            texts = e["rule_%s" % side]["texts"]
            rids = e["rule_%s" % side]["record_ids"]
            allow = {(r[key]["text"], r[key]["record_id"]) for r in rows if r[key]}
            for t, rid in zip(texts, rids):
                checked += 1
                if (t, rid) not in allow:
                    bad_quote.append((e["event_id"], side, t[:40], rid))
    check("quotes not traceable to the B2 record", bad_quote, [])
    check_true("quotes checked", checked > 0, "%d quoted strings traced back to B2" % checked)

    # ---------- 4. record_id must exist in phase A ----------
    unknown_rec = set()
    for e in events:
        for side in ("2026", "2027"):
            for rid in e["rule_%s" % side]["record_ids"]:
                if rid not in recmap:
                    unknown_rec.add(rid)
    check("record_id not found in phase-A JSONL", sorted(unknown_rec), [])

    # ---------- 5. quote should be a substring of the phase-A record text ----------
    # a quote is acceptable if it is a substring of the record itself OR of a
    # stitched paragraph spanning it: phase A split some paragraphs into 2-4
    # records and B2 rejoined them before sentence splitting, so a quoted sentence
    # can straddle record boundaries inside the same section.
    from collections import defaultdict

    def window_hit(rec, text):
        doc, sidx = rec.get("doc_id"), rec.get("section_index")
        rs = [r for r in (recs26 if doc == "RMUC2026" else recs27)
              if r.get("region_type") == "section" and r.get("section_index") == sidx
              and (r.get("norm_text") or "").strip()]
        rs.sort(key=lambda r: r["record_index"])
        idxs = [k for k, r in enumerate(rs) if r["record_id"] == rec["record_id"]]
        if not idxs:
            return False
        i = idxs[0]
        for lo in range(max(0, i - 3), i + 1):
            joined = "".join((x.get("norm_text") or "") for x in rs[lo:min(len(rs), lo + 5)])
            if text in joined:
                return True
        return False

    hits = tot = 0
    stitched_miss = []
    for e in events:
        for side in ("2026", "2027"):
            for t, rid in zip(e["rule_%s" % side]["texts"], e["rule_%s" % side]["record_ids"]):
                rec = recmap.get(rid)
                if not rec:
                    continue
                tot += 1
                if t in (rec.get("norm_text") or "") or window_hit(rec, t):
                    hits += 1
                else:
                    stitched_miss.append((e["event_id"], rid))
    ratio = hits / tot if tot else 0
    check_true("quotes appear verbatim in the phase-A record text",
               ratio >= 0.98, "%d/%d = %.1f%%（允许跨记录缝合窗口 ±3）"
               % (hits, tot, 100 * ratio))
    check_true("unmatched quotes", len(stitched_miss) <= 8,
               "%d unmatched %s" % (len(stitched_miss), stitched_miss[:4]))

    # ---------- 6. special references resolve ----------
    tids = {r["table_2026"]["id"] for r in sp["tables"]["rows"] if r.get("table_2026")}
    tids |= {r["table_2027"]["id"] for r in sp["tables"]["rows"] if r.get("table_2027")}
    fids = {r["figure_2026"]["id"] for r in sp["figures"]["rows"] if r.get("figure_2026")}
    fids |= {r["figure_2027"]["id"] for r in sp["figures"]["rows"] if r.get("figure_2027")}
    xids = set()
    for r in sp["formulas"]["rows"]:
        for k in ("formula_2026", "formula_2027"):
            if r.get(k):
                xids.add(r[k]["id"])
    bad_spec = []
    for e in events:
        for s in e["special_refs"]:
            pool = {"table": tids, "figure": fids, "formula": xids}.get(s["kind"], set())
            if s["id"] not in pool:
                bad_spec.append((e["event_id"], s["kind"], s["id"]))
    check("special refs not found in special_diff", bad_spec, [])
    n_spec = sum(len(e["special_refs"]) for e in events)
    check_true("special refs resolved", n_spec > 0, "%d refs" % n_spec)

    # ---------- 7. C1 pairing review ----------
    tent = [r for r in diffs if r["evidence"].get("tentative_pairing")]
    check("tentative pairs reviewed", pair["reviewed_tentative"], len(tent))
    bad_corr = [c["diff_id"] for c in pair["corrections"] if c["diff_id"] not in
                {r["diff_id"] for r in tent}]
    check("corrections pointing at non-tentative diffs", bad_corr, [])
    no_basis = [c["correction_id"] for c in pair["corrections"] if len(c.get("basis") or "") < 8]
    check("corrections without a stated basis", no_basis, [])
    check("corrections counted in coverage", cov["pairing_rejected"], len(pair["corrections"]))
    check_true("model recorded", bool(pair["model"].get("name")), pair["model"].get("name"))
    check_true("prompt recorded", len(pair["prompt"].get("rules") or "") > 50,
               "%d chars" % len(pair["prompt"].get("rules") or ""))

    # ---------- 8. batches archived as claimed ----------
    batch_ids = [b["id"] for b in cov["batches"]]
    missing_b = [b["id"] for b in cov["batches"]
                 if not os.path.exists(os.path.join(SEM, "batches", b["file"]))]
    check("batch files missing", missing_b, [])
    line_mismatch = []
    for b in cov["batches"]:
        p = os.path.join(SEM, "batches", b["file"])
        if os.path.exists(p):
            n = sum(1 for _ in open(p, encoding="utf-8"))
            if n != b["lines"]:
                line_mismatch.append((b["id"], n, b["lines"]))
    check("batch line counts differ from manifest", line_mismatch, [])
    check_true("batches present", len(batch_ids) >= 10, "%d batches" % len(batch_ids))

    # ---------- 9. deliverables + wording ----------
    files = ["规则变更候选.jsonl", "规则变化初步总览.md", "语义分析争议清单.md",
             "语义分析质量报告.md", "配对复核记录.json", "coverage.json"]
    check("deliverables missing", [f for f in files
                                   if not os.path.exists(os.path.join(SEM, f))], [])
    FORBID = re.compile(r"已确认(新增|删除|变更)|毫无疑问|最终结论是")
    hits = []
    for f in files:
        if f.endswith(".md"):
            txt = open(os.path.join(SEM, f), encoding="utf-8").read()
            for m in FORBID.finditer(txt):
                hits.append((f, m.group(0)))
    check("forbidden 'confirmed' wording", hits, [])

    # ---------- 10. upstream assets intact ----------
    check("phase-A 2026 records", len(recs26), 1853)
    check("phase-A 2027 records", len(recs27), 1785)
    check("B1 units", len(align["alignments"]), 135)
    check("B2 diff records", len(diffs), 1333)
    check("B2 change candidates", len(change), 534)

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
