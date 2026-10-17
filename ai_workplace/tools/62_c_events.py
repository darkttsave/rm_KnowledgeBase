#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 6 (phase C) -- step 3: assemble rule-change events.

Merges the model's decisions (61_c_decide.py) with the original B2 records.  All
quoted rule text and record_id are copied from `全文候选差异.jsonl` -- never
retyped -- so a fabricated citation is structurally impossible; 64_c_verify.py
re-checks this against the phase-A JSONL.
"""
import os
import re
import sys
import json
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b2_lib as L

SEM = os.path.join(L.ROOT, "ai_workplace", "semantic")
CHANGE = ("实质修改候选", "新增候选", "删除候选", "迁移或重组候选", "文字调整候选")
TYPE_CN = {"实质修改候选": "实质修改", "新增候选": "新增", "删除候选": "删除",
           "迁移或重组候选": "迁移", "文字调整候选": "文字调整"}


def load_decisions():
    """61_c_decide.py lives in tools/, import it as a module."""
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "61_c_decide.py")
    spec = importlib.util.spec_from_file_location("c_decide", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def side_ref(sd):
    if not sd:
        return None
    return dict(record_id=sd["record_id"], doc=sd["doc"],
                section_no=sd["section_no"], section_title=sd["section_title"],
                section_path=sd.get("section_path") or [],
                physical_page=sd["physical_page"], printed_page=sd["printed_page"],
                text=sd["text"])


def main():
    dec = load_decisions()
    diffs = L.load_jsonl(os.path.join(L.OUT, "全文候选差异.jsonl"))
    align = L.load_json(os.path.join(L.ALIGN, "章节对应关系.json"))
    sp = L.load_json(os.path.join(L.OUT, "special_diff.json"))
    manifest = L.load_json(os.path.join(SEM, "batches_manifest.json"))
    by_id = {r["diff_id"]: r for r in diffs}
    change = [r for r in diffs if r["diff_type"] in CHANGE]

    # ---------- 1. assign diffs to events ----------
    # two passes: explicit diff_ids win, then selectors fill from the rest
    assigned = {ev["id"]: [] for ev in dec.EVENTS}
    used = set()
    for ev in dec.EVENTS:
        for d in ev.get("diffs", []):
            if d not in by_id:
                print("WARN unknown diff_id in %s: %s" % (ev["id"], d))
                continue
            if d in used:
                continue
            assigned[ev["id"]].append(d)
            used.add(d)
    for ev in dec.EVENTS:
        sel = ev.get("select")
        if sel is None:
            continue
        units = set(sel.get("units") or [])
        types = set(sel.get("types") or [])
        for r in change:
            if r["diff_id"] in used:
                continue
            if units and r["align_id"] not in units:
                continue
            if types and r["diff_type"] not in types:
                continue
            assigned[ev["id"]].append(r["diff_id"])
            used.add(r["diff_id"])
    empty = [k for k, v in assigned.items() if not v]
    if empty:
        print("WARN events with no diff:", empty)

    leftovers = [r for r in change if r["diff_id"] not in used]
    print("assigned %d / %d change diffs; leftovers %d"
          % (len(used), len(change), len(leftovers)))
    if leftovers:
        c = Counter((r["align_id"], r["diff_type"]) for r in leftovers)
        for k, v in c.most_common(20):
            print("   leftover", k, v)

    # ---------- 2. resolve special references ----------
    trows = sp["tables"]["rows"]
    frows = sp["figures"]["rows"]
    xrows = sp["formulas"]["rows"]

    def norm_no(s):
        return re.sub(r"[^0-9.]", "", s or "")

    def resolve(spec):
        kind, _, val = spec.partition(":")
        out = []
        if kind == "table":
            v = norm_no(val)
            for r in trows:
                a, b = r.get("table_2026") or {}, r.get("table_2027") or {}
                nos = " ".join(norm_no(x.get("table_no") or "") for x in (a, b))
                secs = " ".join((x.get("section_no") or "") for x in (a, b))
                candidates = [x for x in (a, b) if x]
                if not candidates:
                    continue
                if v and v in nos.replace(" ", "") and len(v) >= 3:
                    out.append(dict(kind="table", ref=spec, id=candidates[0]["id"],
                                    section_no=candidates[0]["section_no"],
                                    caption=candidates[0].get("caption"),
                                    page=candidates[0].get("physical_page"),
                                    diff_type=r["diff_type"]))
                elif val in secs.split():
                    out.append(dict(kind="table", ref=spec, id=candidates[0]["id"],
                                    section_no=candidates[0]["section_no"],
                                    caption=candidates[0].get("caption"),
                                    page=candidates[0].get("physical_page"),
                                    diff_type=r["diff_type"]))
        elif kind == "figure":
            for r in frows:
                a, b = r.get("figure_2026") or {}, r.get("figure_2027") or {}
                for x in (a, b):
                    if x and val and val.replace("图 ", "") in (x.get("caption") or ""):
                        out.append(dict(kind="figure", ref=spec, id=x["id"],
                                        caption=x.get("caption"),
                                        page=x.get("physical_page"),
                                        diff_type=r["diff_type"]))
                        break
        elif kind == "formula":
            for r in xrows:
                if r["kind"] in ("formula_fraction", "script_spans") and r["diff_type"] != "内容一致":
                    a, b = r.get("formula_2026") or {}, r.get("formula_2027") or {}
                    pa = (a or {}).get("physical_page")
                    pb = (b or {}).get("physical_page")
                    out.append(dict(kind="formula", ref=spec, id=a.get("id") or b.get("id"),
                                    page=pa or pb, diff_type=r["diff_type"]))
        return out

    # ---------- 3. build events ----------
    events = []
    SPEC_CACHE = {}
    for ev in dec.EVENTS:
        ids = assigned[ev["id"]]
        rows = [by_id[i] for i in ids]
        for side, key in (("2026", "a"), ("2027", "b")):
            pass
        a_rows = [r for r in rows if r["a"]]
        b_rows = [r for r in rows if r["b"]]
        # keep reading order: sort by page then original diff id
        a_rows.sort(key=lambda r: (r["a"]["physical_page"], r["diff_id"]))
        b_rows.sort(key=lambda r: (r["b"]["physical_page"], r["diff_id"]))
        special_refs = []
        for s in ev.get("special", []):
            if s not in SPEC_CACHE:
                SPEC_CACHE[s] = resolve(s)
            special_refs.extend(SPEC_CACHE[s])
        # absence evidence for one-sided events
        absence = None
        if ev["change_type"] in ("实质新增", "实质取消") or not a_rows or not b_rows:
            best = []
            for r in rows:
                e = r.get("evidence") or {}
                if e.get("fulltext_best_similarity") is not None:
                    best.append((e["fulltext_best_similarity"], e.get("fulltext_best_section"),
                                 e.get("fulltext_best_record")))
            absence = dict(
                searched="另一赛季全文（阶段 B2 已对全部正文句段做全文兜底检索，阈值 0.80、长度≥12 字）",
                one_sided=("仅 2026 有" if not b_rows else ("仅 2027 有" if not a_rows else "两侧均有")),
                max_similarity_found=(round(max(x[0] for x in best), 4) if best else None),
                best_sections=sorted({x[1] for x in best if x[1]}),
                note=("另一赛季未找到达到阈值的对应表述" if (best and max(x[0] for x in best) < 0.80)
                      else "另一赛季存在相似表述，最高相似度见 max_similarity_found，需人工判断是否为继承/迁移"),
            )
        rec = OrderedDict([
            ("event_id", ev["id"]),
            ("theme", ev["theme"]),
            ("topic", ev["topic"]),
            ("change_type", ev["change_type"]),
            ("evidence_strength", ev["evidence"]),
            ("needs_review", ev["evidence"] != "strong"),
            ("summary", ev["judgment"]),
            ("rule_2026", dict(
                texts=[r["a"]["text"] for r in a_rows],
                record_ids=[r["a"]["record_id"] for r in a_rows],
                sections=sorted({"%s %s" % (r["a"]["section_no"], r["a"]["section_title"]) for r in a_rows}),
                pages=sorted({r["a"]["physical_page"] for r in a_rows}),
            )),
            ("rule_2027", dict(
                texts=[r["b"]["text"] for r in b_rows],
                record_ids=[r["b"]["record_id"] for r in b_rows],
                sections=sorted({"%s %s" % (r["b"]["section_no"], r["b"]["section_title"]) for r in b_rows}),
                pages=sorted({r["b"]["physical_page"] for r in b_rows}),
            )),
            ("diff_ids", ids),
            ("diff_type_counts", {TYPE_CN.get(k, k): v
                                  for k, v in Counter(r["diff_type"] for r in rows).items()}),
            ("special_refs", special_refs),
            ("absence_evidence", absence),
            ("align_units", sorted({r["align_id"] for r in rows})),
            ("b1_relations", sorted({r.get("align_relation") or "" for r in rows})),
            ("verify_status", "unverified"),
            ("note", ""),
        ])
        if ev["id"] in [d.get("event_id") for d in dec.DISPUTES]:
            rec["note"] = "见争议清单"
        events.append(rec)

    # ---------- 4. leftovers become explicit "unresolved" events ----------
    if leftovers:
        for i, (k, v) in enumerate(sorted(Counter((r["align_id"], r["diff_type"])
                                                  for r in leftovers).items()), 1):
            aid, dtype = k
            rows = [r for r in leftovers
                    if r["align_id"] == aid and r["diff_type"] == dtype]
            a_rows = [r for r in rows if r["a"]]
            b_rows = [r for r in rows if r["b"]]
            events.append(OrderedDict([
                ("event_id", "CE-U%02d" % i),
                ("theme", "未归入"),
                ("topic", "未归入事件的差异（%s / %s）" % (aid, TYPE_CN.get(dtype, dtype))),
                ("change_type", "证据不足"),
                ("evidence_strength", "weak"),
                ("needs_review", True),
                ("summary", "该批差异未归入任何规则事件，需人工判断其规则含义。"),
                ("rule_2026", dict(texts=[r["a"]["text"] for r in a_rows],
                                   record_ids=[r["a"]["record_id"] for r in a_rows],
                                   sections=[], pages=[])),
                ("rule_2027", dict(texts=[r["b"]["text"] for r in b_rows],
                                   record_ids=[r["b"]["record_id"] for r in b_rows],
                                   sections=[], pages=[])),
                ("diff_ids", [r["diff_id"] for r in rows]),
                ("diff_type_counts", {TYPE_CN.get(dtype, dtype): len(rows)}),
                ("special_refs", []), ("absence_evidence", None),
                ("align_units", [aid]), ("b1_relations", []),
                ("verify_status", "unverified"), ("note", "B2 差异未被规则事件覆盖"),
            ]))

    # ---------- 5. write ----------
    path = os.path.join(SEM, "规则变更候选.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # pairing corrections
    corrections = []
    for d, why in dec.PAIR_WRONG.items():
        r = by_id.get(d)
        corrections.append(dict(
            correction_id="PC-%03d" % (len(corrections) + 1),
            diff_id=d, action="reject_pairing",
            original=dict(diff_type=r["diff_type"], similarity=r.get("similarity"),
                          a=(r["a"] or {}).get("text"), b=(r["b"] or {}).get("text"),
                          a_record=(r["a"] or {}).get("record_id"),
                          b_record=(r["b"] or {}).get("record_id")),
            new_classification="删除候选 + 新增候选（两侧分别为独立规则）",
            basis=why, verify_status="unverified"))
    json.dump(dict(model=dec.MODEL, prompt=dec.PROMPT,
                   corrections=corrections,
                   reviewed_tentative=len([r for r in diffs if r["evidence"].get("tentative_pairing")]),
                   rejected=len(corrections)),
              open(os.path.join(SEM, "配对复核记录.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ---------- 6. coverage ----------
    by_type = Counter(e["change_type"] for e in events)
    cov = dict(
        generated=__import__("datetime").datetime.now().isoformat(timespec="seconds"),
        model=dec.MODEL,
        batches=[dict(id=k, file=v["file"], title=v["title"], lines=v["lines"], items=v["items"])
                 for k, v in manifest.items()],
        change_diffs_total=len(change),
        change_diffs_in_events=len(used),
        change_diffs_unresolved=len(leftovers),
        events=len(events),
        events_by_type=dict(by_type),
        events_by_theme=dict(Counter(e["theme"] for e in events)),
        needs_review=sum(1 for e in events if e["needs_review"]),
        special_refs_resolved=sum(len(e["special_refs"]) for e in events),
        special_unreferenced=(dict(
            tables=len([r for r in sp["tables"]["rows"] if r["diff_type"] != "内容一致"]),
            figures=len([r for r in sp["figures"]["rows"] if r["diff_type"] != "内容一致"]),
            formulas=len([r for r in sp["formulas"]["rows"] if r["diff_type"] != "内容一致"]))),
        pairing_reviewed=len([r for r in diffs if r["evidence"].get("tentative_pairing")]),
        pairing_rejected=len(corrections),
        disputes=len(dec.DISPUTES),
    )
    json.dump(cov, open(os.path.join(SEM, "coverage.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("events: %d (%s)" % (len(events), dict(by_type)))
    print("by theme:", dict(Counter(e["theme"] for e in events)))
    print("special refs resolved:", cov["special_refs_resolved"])
    print("written 规则变更候选.jsonl / 配对复核记录.json / coverage.json")


if __name__ == "__main__":
    main()
