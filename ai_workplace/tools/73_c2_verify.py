#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 7 (phase C 补充核验) -- step 4: independent verification."""
import os
import re
import sys
import json
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b2_lib as L

SEM = os.path.join(L.ROOT, "ai_workplace", "semantic")
checks = []


def check(name, got, want):
    ok = got == want
    checks.append((ok, name, got, want))
    g = ("<%d items>" % len(got)) if isinstance(got, (list, set, dict)) and len(got) > 6 else repr(got)
    w = ("<%d items>" % len(want)) if isinstance(want, (list, set, dict)) and len(want) > 6 else repr(want)
    print(("PASS " if ok else "FAIL ") + "%-60s got=%s want=%s" % (name, g, w))
    return ok


def check_true(name, cond, detail=""):
    checks.append((bool(cond), name, detail, True))
    print(("PASS " if cond else "FAIL ") + "%-60s %s" % (name, detail))
    return bool(cond)


def main():
    rev = L.load_jsonl(os.path.join(SEM, "规则变更候选_修订版.jsonl"))
    old = L.load_jsonl(os.path.join(SEM, "规则变更候选.jsonl"))
    stats = L.load_json(os.path.join(SEM, "revision_stats.json"))
    recheck = L.load_json(os.path.join(SEM, "special_recheck.json"))
    pair = L.load_json(os.path.join(SEM, "配对复核记录.json"))
    diffs = L.load_jsonl(os.path.join(L.OUT, "全文候选差异.jsonl"))
    by_id = {r["diff_id"]: r for r in diffs}

    ev = [r for r in rev if r["record_type"] == "规则事件"]
    sup = [r for r in rev if r["record_type"] == "补充事件"]
    cor = [r for r in rev if r["record_type"] == "配对更正"]
    mig = [r for r in rev if r["record_type"] == "机制迁移判定"]

    # ---------- 1. structure / preservation ----------
    check("total records", len(rev), 101)
    check("record types", dict(Counter(r["record_type"] for r in rev)),
          {"规则事件": 62, "补充事件": 11, "配对更正": 24, "机制迁移判定": 4})
    check("rule events preserved", sorted(r["event_id"] for r in ev),
          sorted(e["event_id"] for e in old))
    oldby = {e["event_id"]: e for e in old}
    bad_diff = [(r["event_id"]) for r in ev
                if r["diff_ids"] != oldby[r["event_id"]]["diff_ids"]]
    check("original diff_ids preserved verbatim", bad_diff, [])
    bad_text = [r["event_id"] for r in ev
                if r["rule_2026"]["texts"] != oldby[r["event_id"]]["rule_2026"]["texts"]
                or r["rule_2027"]["texts"] != oldby[r["event_id"]]["rule_2027"]["texts"]]
    check("original rule texts preserved verbatim", bad_text, [])
    check("original file still 62 events", len(old), 62)
    check("event_id unique across revised", len({r["event_id"] for r in rev}), len(rev))

    # ---------- 2. classification correction (task §一) ----------
    cat = {r["event_id"]: r["revision"]["category"] for r in rev}
    expect = {"CE-51": "文档变化", "CE-18": "文档变化", "CE-52": "文档变化",
              "CE-56": "排版变化", "CE-17": "未定",
              "CE-60": "未定", "CE-61": "未定", "CE-62": "未定"}
    bad = [(k, cat.get(k), v) for k, v in expect.items() if cat.get(k) != v]
    check("category corrections applied", bad, [])
    check_true("1.2 变更说明 not counted as a new mechanism",
               not any(r["revision"]["counts_as_rule_change"]
                       for r in rev if r["event_id"] == "CE-51"))
    check_true("场地图例补充 not counted as a new mechanism",
               not any(r["revision"]["counts_as_rule_change"]
                       for r in rev if r["event_id"] == "CE-18"))
    check("counts_as_rule_change count", stats["counts_as_rule_change"],
          sum(1 for r in rev if r["revision"]["counts_as_rule_change"]))
    nontrivial = [r["event_id"] for r in rev
                  if r["revision"]["category"] in ("文档变化", "排版变化", "未定")
                  and r["revision"]["counts_as_rule_change"]]
    check("doc/layout/undetermined records wrongly counted as rule change", nontrivial, [])

    # ---------- 3. 机制重构内部变化展开 (task §一.4) ----------
    RECON = ["CE-03", "CE-04", "CE-05", "CE-06", "CE-08", "CE-19", "CE-25"]
    missing_internal = [e for e in RECON
                        if not next(r for r in ev if r["event_id"] == e)["revision"]["internal_changes"]]
    check("重构事件缺少 internal_changes", missing_internal, [])
    types_used = Counter()
    for r in ev:
        for ic in r["revision"]["internal_changes"]:
            types_used[ic["type"]] += 1
    check_true("internal changes use 新增/取消/修改 vocabulary",
               set(types_used) <= {"新增", "取消", "修改", "保留", "合并", "替换"},
               str(dict(types_used)))
    check_true("internal changes present", stats["internal_changes"] >= 30,
               "%d items" % stats["internal_changes"])

    # ---------- 4. 证据不足事件逐条保留 (task §三.1) ----------
    weak = [r for r in ev if r["change_type"] == "证据不足"]
    bad_unres = []
    for r in weak:
        got = {x["diff_id"] for x in r["revision"]["unresolved_items"]}
        if got != set(r["diff_ids"]):
            bad_unres.append((r["event_id"], len(got), len(r["diff_ids"])))
    check("证据不足事件未逐条保留", bad_unres, [])
    check("unresolved items count", stats["unresolved_items"],
          sum(len(r["revision"]["unresolved_items"]) for r in rev))
    no_quote = [x["diff_id"] for r in rev for x in r["revision"]["unresolved_items"]
                if x.get("text_2026") and x["diff_id"] in by_id
                and x["text_2026"] != (by_id[x["diff_id"]]["a"] or {}).get("text")]
    check("unresolved item text differs from B2", no_quote, [])

    # ---------- 5. 配对更正 (task §三.3) ----------
    check("corrections count", len(cor), len(pair["corrections"]))
    bad_cor = []
    for c in cor:
        d = c["diff_ids"][0]
        r = by_id.get(d)
        if not r:
            bad_cor.append((c["event_id"], d, "unknown diff"))
            continue
        a_old = (c["rule_2026"]["texts"] or [None])[0]
        b_old = (c["rule_2027"]["texts"] or [None])[0]
        if a_old != (r["a"] or {}).get("text") or b_old != (r["b"] or {}).get("text"):
            bad_cor.append((c["event_id"], d, "text mismatch"))
    check("corrections do not match the B2 record", bad_cor, [])
    check("all corrections are tentative pairs", len(cor),
          len([c for c in cor if by_id[c["diff_ids"][0]]["evidence"].get("tentative_pairing")]))

    # ---------- 6. 机制迁移判定 (task §三.5) ----------
    check("migration records", len(mig), 4)
    bad_mig = [m["event_id"] for m in mig
               if not (m["revision"]["internal_changes"]
                       and any(x["type"] == "保留" for x in m["revision"]["internal_changes"])
                       and any(x["type"] == "取消" for x in m["revision"]["internal_changes"]))]
    check("migration records without both retained and removed parts", bad_mig, [])
    mig_topics = " ".join(m["topic"] for m in mig)
    check_true("migration covers 空中系统/雷达/哨兵",
               all(k in mig_topics for k in ("空中系统", "雷达", "哨兵")))

    # ---------- 7. 特殊内容 (task §二) ----------
    trows = recheck["tables"]["rows"]
    check("table rows have a verdict", [i for i, r in enumerate(trows) if not r.get("verdict")], [])
    check_true("table pairing changed vs B2", len(recheck["tables"]["changed_pairing"]) >= 1,
               "%d changed" % len(recheck["tables"]["changed_pairing"]))
    check_true("table method does not rank by table number",
               "不再以表号为主键" in recheck["method"]["table_pairing"])
    frows = recheck["figures"]["rows"]
    check("figure rows without a verdict", [i for i, r in enumerate(frows) if not r.get("verdict")], [])
    vv = set(r["verdict"] for r in frows)
    check("figure verdict vocabulary", vv <= {"像素完全一致", "纯样式变化候选", "信息变化",
                                              "无法判断", "信息变化"}, True)
    check_true("figures are classified into style/info/unknown",
               {"纯样式变化候选", "信息变化", "无法判断"} <= vv, str(sorted(vv)))
    miss_png = [c["image_2026"] for c in recheck["figures"]["rendered"]
                if not os.path.exists(os.path.join(SEM, c["image_2026"]))]
    miss_png += [c["image_2027"] for c in recheck["figures"]["rendered"]
                 if not os.path.exists(os.path.join(SEM, c["image_2027"]))]
    check("page comparison images missing", miss_png, [])
    check_true("page comparisons rendered", len(recheck["figures"]["rendered"]) >= 5,
               "%d groups" % len(recheck["figures"]["rendered"]))
    check_true("formulas listed", len(recheck["formulas"]) > 0, "%d formulas" % len(recheck["formulas"]))
    check_true("no claim that tables/images are semantically identical",
               "语义完全一致" in ("".join(open(os.path.join(SEM, f), encoding="utf-8").read()
                                          for f in ["特殊内容核验报告.md"])), True)

    # ---------- 8. 补充事件关联 ----------
    check("supplementary events", len(sup), 11)
    no_refs = [s["event_id"] for s in sup if not s.get("spec_refs")]
    check("supplementary events without special refs", no_refs, [])
    check_true("supplementary events link to rule events",
               all(s.get("linked_events") or s["event_id"] in ("CX-09", "CX-11") for s in sup))

    # ---------- 9. deliverables + wording ----------
    files = ["规则变更候选_修订版.jsonl", "特殊内容核验报告.md", "未解决争议清单.md",
             "重点规则人工审核表.md", "阶段C补充核验质量报告.md",
             "special_recheck.json", "revision_stats.json"]
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

    # ---------- 10. 审核表完整性 ----------
    review = open(os.path.join(SEM, "重点规则人工审核表.md"), encoding="utf-8").read()
    for label in ("变化类型", "2026 原文与来源", "2027 原文与来源", "AI 判断",
                  "尚需核实的疑点", "是否可能影响机器人设计或比赛策略"):
        check_true("审核表字段: %s" % label, label in review)
    groups = [g for g in ("一、机器人", "二、比赛机制", "三、场地", "四、违规与判罚")
              if g not in review]
    check("审核表分组缺失", groups, [])
    n_items = review.count("\n### ")
    check_true("审核表条目数", n_items >= 40, "%d items" % n_items)

    # ---------- 11. 上游资产未改动 ----------
    rec26 = L.load_jsonl(os.path.join(L.STRUCT, "2026_结构化.jsonl"))
    rec27 = L.load_jsonl(os.path.join(L.STRUCT, "2027_结构化.jsonl"))
    check("phase-A 2026 records intact", len(rec26), 1853)
    check("phase-A 2027 records intact", len(rec27), 1785)
    check("phase B2 diffs intact", len(diffs), 1333)
    check("phase C original events intact", len(old), 62)

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
