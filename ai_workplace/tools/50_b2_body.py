#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 5 (phase B2) -- step 1: body-text difference discovery.

Produces candidate differences for every body record (paragraph / list item /
diagram label / figure-label row / formula text fragment), keeping the matched
"内容一致" pairs as well so coverage is provable.
"""
import os
import re
import json
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b2_lib as L

MIN_PAIR = 0.60          # minimum similarity to consider two sentences the same rule
FALLBACK = 0.80          # full-text fallback threshold (migration detection)
FALLBACK_MINLEN = 12


def unit_ranges(align):
    """align_id -> (set of 2026 section_index, set of 2027 section_index)"""
    out = {}
    for u in align["alignments"]:
        s26 = {s["id"] for s in u["sections_2026"]}
        s27 = {s["id"] for s in u["sections_2027"]}
        out[u["align_id"]] = dict(s26=s26, s27=s27, relation=u["relation"],
                                  match_type=u["match_type"],
                                  sec26=[(s["no"], s["title"]) for s in u["sections_2026"]],
                                  sec27=[(s["no"], s["title"]) for s in u["sections_2027"]])
    return out


def side(s):
    if not s:
        return None
    return dict(
        doc=s["doc"], record_id=s["record_id"], record_ids=s["record_ids"],
        stitched=s["stitched"], block_kind=s["block_kind"], block_kinds=s["block_kinds"],
        physical_page=s["physical_page"], printed_page=s["printed_page"],
        section_no=s["section_no"], section_title=s["section_title"],
        section_path=s["section_path"],
        block_index_in_para=s["sent_index"], marker=s["marker"],
        text=s["raw"], bbox=s["bbox"],
    )


def make_record(diff_type, align_id, relation, a, b, extra=None, sim=None,
                fallback=None, needs_review=False, review_reason=""):
    rec = dict(
        diff_type=diff_type,
        counts_as_change=diff_type not in ("内容一致", "编号变化（不计内容变化）",
                                           "引用编号更新（不计内容变化）"),
        align_id=align_id,
        align_relation=relation,
        section_2026=(dict(no=a["section_no"], title=a["section_title"],
                           path=a["section_path"]) if a else None),
        section_2027=(dict(no=b["section_no"], title=b["section_title"],
                           path=b["section_path"]) if b else None),
        a=side(a), b=side(b),
        similarity=(round(sim, 4) if sim is not None else None),
        evidence=extra or {},
        fallback=fallback,
        needs_review=needs_review,
        review_reason=review_reason,
        verify_status="unverified",
    )
    return rec


def main():
    align = L.load_json(os.path.join(L.ALIGN, "章节对应关系.json"))
    recs26 = L.load_jsonl(os.path.join(L.STRUCT, "2026_结构化.jsonl"))
    recs27 = L.load_jsonl(os.path.join(L.STRUCT, "2027_结构化.jsonl"))
    sent26 = L.build_sentences(recs26, "RMUC2026")
    sent27 = L.build_sentences(recs27, "RMUC2027")
    print("sentences: 2026=%d 2027=%d" % (len(sent26), len(sent27)))

    ur = unit_ranges(align)
    sec2unit26 = {}
    sec2unit27 = {}
    for u in align["alignments"]:
        for s in u["sections_2026"]:
            sec2unit26[s["id"]] = u["align_id"]
        for s in u["sections_2027"]:
            sec2unit27[s["id"]] = u["align_id"]

    by_unit26 = defaultdict(list)
    by_unit27 = defaultdict(list)
    for s in sent26:
        by_unit26[sec2unit26[s["section_index"]]].append(s)
    for s in sent27:
        by_unit27[sec2unit27[s["section_index"]]].append(s)

    gidx27 = L.SentIndex(sent27)
    gidx26 = L.SentIndex(sent26)

    used26, used27 = set(), set()
    pairs = []            # (a, b, sim, unit, better)
    unit_order = [u["align_id"] for u in align["alignments"]]

    # ---------------- 1. in-unit matching ----------------
    for aid in unit_order:
        A = by_unit26.get(aid, [])
        B = by_unit27.get(aid, [])
        if not A or not B:
            continue
        idxB = L.SentIndex(B)
        cand = []
        for a in A:
            for i, _sc in idxB.top(a["core"], k=10):
                b = B[i]
                r = L.ratio(a["core"], b["core"])
                if r >= MIN_PAIR:
                    cand.append((r, a["idx"], b["idx"]))
        cand.sort(reverse=True)
        for r, ia, ib in cand:
            if ia in used26 or ib in used27:
                continue
            used26.add(ia)
            used27.add(ib)
            a, b = sent26[ia], sent27[ib]
            # would a better match exist outside this unit? (mapping sanity)
            better = None
            gi, gr = L.best_match(gidx27, a["core"], exclude=None, k=14)
            if gr >= r + 0.10 and gi is not None and gi != ib:
                bo = sent27[gi]
                if bo["section_index"] not in ur[aid]["s27"]:
                    better = dict(section_no=bo["section_no"], section_title=bo["section_title"],
                                  similarity=round(gr, 4))
            pairs.append((a, b, r, aid, better))

    # ------------- 1b. second pass: tentative re-pairing of leftovers in-unit ----
    # A rewritten paragraph usually leaves one 2026 and one 2027 leftover sentence
    # that fail the 0.60 bar.  Pairing them (marked as tentative) turns a false
    # "delete + add" pair into a single "实质修改候选", which is far closer to
    # reality and keeps the review list readable.
    low_pairs = []
    for aid in unit_order:
        A_left = [x for x in by_unit26.get(aid, []) if x["idx"] not in used26]
        B_left = [x for x in by_unit27.get(aid, []) if x["idx"] not in used27]
        if not A_left or not B_left:
            continue
        cand = []
        for a in A_left:
            ga = L.bigrams(a["core"])
            for b in B_left:
                j = L.jaccid(ga, L.bigrams(b["core"]))
                if j >= 0.20:
                    cand.append((j, a["idx"], b["idx"]))
        cand.sort(reverse=True)
        for j, ia, ib in cand:
            if ia in used26 or ib in used27:
                continue
            used26.add(ia)
            used27.add(ib)
            low_pairs.append((sent26[ia], sent27[ib], L.ratio(sent26[ia]["core"], sent27[ib]["core"]),
                              aid, round(j, 3)))
    print("second-pass tentative pairing: %d" % len(low_pairs))
    print("in-unit matched: %d (2026 used %d / %d, 2027 used %d / %d)"
          % (len(pairs), len(used26), len(sent26), len(used27), len(sent27)))

    # ---------------- 2. full-text fallback for leftovers ----------------
    left26 = [s for s in sent26 if s["idx"] not in used26]
    left27 = [s for s in sent27 if s["idx"] not in used27]
    left26.sort(key=lambda s: -len(s["core"]))
    left27.sort(key=lambda s: -len(s["core"]))

    moved = []            # (a, b, sim, reason)
    for a in left26:
        if len(a["core"]) < FALLBACK_MINLEN:
            continue
        for i, _sc in gidx27.top(a["core"], k=14):
            if i in used27:
                continue
            b = sent27[i]
            r = L.ratio(a["core"], b["core"])
            if r >= FALLBACK:
                used26.add(a["idx"])
                used27.add(i)
                moved.append((a, b, r))
                break
    for b in left27:
        if b["idx"] in used27 or len(b["core"]) < FALLBACK_MINLEN:
            continue
        for i, _sc in gidx26.top(b["core"], k=14):
            if i in used26:
                continue
            a = sent26[i]
            r = L.ratio(a["core"], b["core"])
            if r >= FALLBACK:
                used26.add(a["idx"])
                used27.add(b["idx"])
                moved.append((a, b, r))
                break
    print("full-text fallback recovered: %d" % len(moved))

    # ---------------- 3. build diff records ----------------
    out = []

    def unit_of(a, b):
        if a:
            return sec2unit26.get(a["section_index"], "AL-?")
        return sec2unit27.get(b["section_index"], "AL-?")

    pairs.sort(key=lambda p: (unit_order.index(p[3]), p[0]["idx"]))
    for a, b, r, aid, better in pairs:
        dtype, ev = L.classify_pair(a, b)
        if better:
            ev["better_match_outside_unit"] = better
        reason = ""
        need = False
        if dtype in ("实质修改候选", "文字调整候选") and ev.get("numbers"):
            need = True
            reason = "参数数值发生变化，需核对原文"
        if better:
            need = True
            reason = (reason + "；" if reason else "") + "B1 映射可能不准：全文存在更相似的对应句"
        rec = make_record(dtype, aid, ur[aid]["relation"], a, b, ev, sim=r,
                          needs_review=need, review_reason=reason)
        rec["_sort"] = (unit_order.index(aid), a["physical_page"], a["idx"], 0)
        out.append(rec)

    for a, b, r, aid, j in low_pairs:
        dtype, ev = L.classify_pair(a, b)
        if dtype in ("内容一致", "编号变化（不计内容变化）", "引用编号更新（不计内容变化）"):
            dtype = "文字调整候选"
        ev["tentative_pairing"] = True
        ev["bigram_jaccard"] = j
        ev["note"] = "相似度低于 0.60，按同章节残余句配对，属程序推测的改写对应，需人工确认"
        rec = make_record(dtype, aid, ur[aid]["relation"], a, b, ev, sim=r,
                          needs_review=True,
                          review_reason="程序推测为同一规则的改写（同章节、相似度偏低），需核对原文")
        rec["_sort"] = (unit_order.index(aid), a["physical_page"], a["idx"], 0)
        out.append(rec)
    moved.sort(key=lambda p: (p[0]["physical_page"], p[0]["idx"]))
    for a, b, r in moved:
        dtype, ev = L.classify_pair(a, b)
        aid_a = sec2unit26.get(a["section_index"])
        aid_b = sec2unit27.get(b["section_index"])
        ev["source_unit"] = aid_a
        ev["target_unit"] = aid_b
        ev["same_unit"] = (aid_a == aid_b)
        rec = make_record("迁移或重组候选", aid_a or aid_b, ur.get(aid_a, {}).get("relation"),
                          a, b, ev, sim=r, needs_review=True,
                          review_reason="该句在 B1 映射对应的章节中未找到，但在另一章节找到高度相似句，疑为跨章节迁移/重组")
        rec["fallback"] = dict(scope="fulltext",
                               matched_section_no=b["section_no"],
                               matched_section_title=b["section_title"],
                               matched_record_id=b["record_id"],
                               similarity=round(r, 4))
        rec["_sort"] = (unit_order.index(aid_a) if aid_a in unit_order else 999,
                        a["physical_page"], a["idx"], 1)
        out.append(rec)

    for a in sent26:
        if a["idx"] in used26:
            continue
        aid = sec2unit26.get(a["section_index"])
        gi, gr = L.best_match(gidx27, a["core"], exclude=None, k=14)
        ev = dict(
            note="在 B1 对应章节及全文兜底检索中均未找到达到阈值的相似句",
            fulltext_best_similarity=round(gr, 4),
            fulltext_best_section=((sent27[gi]["section_no"] or sent27[gi]["section_title"])
                                  if gi is not None else ""),
            fulltext_best_record=(sent27[gi]["record_id"] if gi is not None else ""),
            fulltext_best_text=(sent27[gi]["raw"][:100] if gi is not None else ""),
        )
        rec = make_record("删除候选", aid, ur.get(aid, {}).get("relation"), a, None, ev,
                          needs_review=True,
                          review_reason="疑似删除，需人工确认（不得直接判定机制取消）")
        rec["_sort"] = (unit_order.index(aid) if aid in unit_order else 999,
                        a["physical_page"], a["idx"], 2)
        out.append(rec)

    for b in sent27:
        if b["idx"] in used27:
            continue
        aid = sec2unit27.get(b["section_index"])
        gi, gr = L.best_match(gidx26, b["core"], exclude=None, k=14)
        ev = dict(
            note="在 B1 对应章节及全文兜底检索中均未找到达到阈值的相似句",
            fulltext_best_similarity=round(gr, 4),
            fulltext_best_section=((sent26[gi]["section_no"] or sent26[gi]["section_title"])
                                  if gi is not None else ""),
            fulltext_best_record=(sent26[gi]["record_id"] if gi is not None else ""),
            fulltext_best_text=(sent26[gi]["raw"][:100] if gi is not None else ""),
        )
        rec = make_record("新增候选", aid, ur.get(aid, {}).get("relation"), None, b, ev,
                          needs_review=True,
                          review_reason="疑似新增，需人工确认（不得直接判定全新机制）")
        rec["_sort"] = (unit_order.index(aid) if aid in unit_order else 999,
                        b["physical_page"], b["idx"], 3)
        out.append(rec)

    out.sort(key=lambda r: r["_sort"])
    for i, r in enumerate(out, 1):
        r["diff_id"] = "D%05d" % i
        del r["_sort"]

    path = os.path.join(L.OUT, "全文候选差异.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ---------------- 4. per-record status ----------------
    status = {}
    for r in out:
        for k in ("a", "b"):
            sd = r[k]
            if not sd:
                continue
            for rid in (sd.get("record_ids") or [sd["record_id"]]):
                st = status.setdefault((sd["doc"], rid), dict(
                    doc=sd["doc"], record_id=rid, block_kind=sd["block_kind"],
                    physical_page=sd["physical_page"], section_no=sd["section_no"],
                    diff_ids=[], types=Counter(), sentences=0))
                if r["diff_id"] not in st["diff_ids"]:
                    st["diff_ids"].append(r["diff_id"])
                st["types"][r["diff_type"]] += 1
                st["sentences"] += 1
    # every body record must have at least one sentence -> status
    body_recs = {}
    for doc, recs in (("RMUC2026", recs26), ("RMUC2027", recs27)):
        for r in recs:
            kind = r.get("block_kind", r.get("record_type"))
            if kind in L.BODY_KINDS and r.get("region_type") == "section" and (r.get("norm_text") or "").strip():
                body_recs[(doc, r["record_id"])] = r
    missing = [k for k in body_recs if k not in status]
    print("body records without status:", len(missing), missing[:5])

    st_out = []
    for key, r in body_recs.items():
        st = status.get(key)
        types = st["types"] if st else Counter()
        if not types:
            cn = L.norm(L.split_marker(r.get("norm_text") or "")[1])
            state = "无可比对文本（仅符号/空白）" if not cn else "未进入比对（异常）"
        elif all(t in ("内容一致", "编号变化（不计内容变化）", "引用编号更新（不计内容变化）")
                 for t in types):
            state = "全部一致"
        elif any(t in ("实质修改候选", "新增候选", "删除候选") for t in types):
            state = "含实质候选差异"
        else:
            state = "仅含轻度候选差异"
        st_out.append(dict(
            doc=r["doc_id"], record_id=r["record_id"],
            block_kind=r.get("block_kind", r["record_type"]),
            physical_page=r["physical_page"], printed_page=r["printed_page"],
            section_no=r["section"]["section_no"], section_title=r["section"]["title"],
            section_path=r["section"]["path"],
            sentences=(st["sentences"] if st else 0),
            status=state,
            diff_type_counts={k: v for k, v in (types or {}).items()},
            diff_ids=(sorted(st["diff_ids"])[:40] if st else []),
        ))
    # excluded records get an explicit status too
    for doc, recs in (("RMUC2026", recs26), ("RMUC2027", recs27)):
        for r in recs:
            kind = r.get("block_kind", r.get("record_type"))
            if kind in L.BODY_KINDS:
                continue
            reason = L.EXCLUDED_KINDS.get(kind)
            st_out.append(dict(
                doc=r["doc_id"], record_id=r["record_id"], block_kind=kind,
                physical_page=r["physical_page"], printed_page=r["printed_page"],
                section_no=r["section"].get("section_no") if r.get("section") else "",
                section_title=r["section"]["title"] if r.get("section") else "",
                section_path=r["section"]["path"] if r.get("section") else [],
                sentences=0,
                status=("转入特殊内容流程" if kind in ("table", "figure", "table_caption",
                                                     "figure_caption", "formula_fraction")
                        else "不计入正文比对" if reason else "未分类（异常）"),
                excluded_reason=reason or "",
                diff_type_counts={}, diff_ids=[],
            ))
    with open(os.path.join(L.OUT, "差异覆盖状态.jsonl"), "w", encoding="utf-8") as f:
        for r in st_out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ---------------- 4b. rewrite-cluster annotation + deleted/added verification ----
    left_by_unit = defaultdict(lambda: [0, 0])
    for a in sent26:
        if a["idx"] in used26:
            continue
        aid = sec2unit26.get(a["section_index"])
        if aid:
            left_by_unit[aid][0] += 1
    for b in sent27:
        if b["idx"] in used27:
            continue
        aid = sec2unit27.get(b["section_index"])
        if aid:
            left_by_unit[aid][1] += 1
    clusters = {k: v for k, v in left_by_unit.items() if v[0] and v[1]}
    for r in out:
        if r["diff_type"] in ("删除候选", "新增候选"):
            lc = left_by_unit.get(r["align_id"])
            if lc and lc[0] and lc[1]:
                r["evidence"]["rewrite_cluster"] = True
                r["evidence"]["cluster_leftovers"] = {"2026": lc[0], "2027": lc[1]}
                r["evidence"]["note"] = (
                    "同章节另一侧也存在 %d 条未匹配句，疑为整段改写；不能据此单独判定删除或新增"
                    % (lc[1] if r["diff_type"] == "删除候选" else lc[0]))

    # 上游要求：6 个疑似删除章节必须进一步检索验证 —— 对每个「疑似删除 / 新增」单元
    # 做一次全量兜底检索，记录最相似句及其所在章节（含低于阈值的最高值）
    verify = []
    for u in align["alignments"]:
        if u["relation"] not in ("deleted", "added"):
            continue
        aid = u["align_id"]
        rows = []
        if u["sections_2026"]:
            pool = [s for s in sent26 if s["section_index"] in ur[aid]["s26"]]
            for s in pool:
                if len(s["core"]) < 12:
                    continue
                gi, gr = L.best_match(gidx27, s["core"], exclude=None, k=14)
                rows.append(dict(side="2026", text=s["raw"][:80], best_similarity=round(gr, 4),
                                 best_section=(sent27[gi]["section_no"] or sent27[gi]["section_title"]) if gi is not None else "",
                                 best_record=(sent27[gi]["record_id"] if gi is not None else "")))
        if u["sections_2027"]:
            pool = [s for s in sent27 if s["section_index"] in ur[aid]["s27"]]
            for s in pool:
                if len(s["core"]) < 12:
                    continue
                gi, gr = L.best_match(gidx26, s["core"], exclude=None, k=14)
                rows.append(dict(side="2027", text=s["raw"][:80], best_similarity=round(gr, 4),
                                 best_section=(sent26[gi]["section_no"] or sent26[gi]["section_title"]) if gi is not None else "",
                                 best_record=(sent26[gi]["record_id"] if gi is not None else "")))
        if not rows:
            continue
        mx = max(r["best_similarity"] for r in rows)
        verify.append(dict(
            align_id=aid, relation=u["relation"],
            sections_2026=[x["no"] or x["title"] for x in u["sections_2026"]],
            sections_2027=[x["no"] or x["title"] for x in u["sections_2027"]],
            sentences=len(rows),
            recovered_above_threshold=sum(1 for r in rows if r["best_similarity"] >= FALLBACK),
            max_similarity=mx,
            max_similarity_detail=[r for r in rows if r["best_similarity"] == mx][:2],
            samples=sorted(rows, key=lambda r: -r["best_similarity"])[:3],
        ))
    # ---------------- 5. stats ----------------
    types = Counter(r["diff_type"] for r in out)
    by_sec = defaultdict(Counter)
    for r in out:
        no = (r["section_2026"] or {}).get("no") or (r["section_2027"] or {}).get("no") or ""
        by_sec[no][r["diff_type"]] += 1
    stats = dict(
        sentences_2026=len(sent26), sentences_2027=len(sent27),
        body_records_2026=sum(1 for k in body_recs if k[0] == "RMUC2026"),
        body_records_2027=sum(1 for k in body_recs if k[0] == "RMUC2027"),
        matched_pairs=len(pairs) + len(low_pairs) + len(moved),
        in_unit_high_threshold=len(pairs),
        tentative_pairs=len(low_pairs),
        recovered_by_fallback=len(moved),
        deleted_candidates=sum(1 for r in out if r["diff_type"] == "删除候选"),
        added_candidates=sum(1 for r in out if r["diff_type"] == "新增候选"),
        diff_by_type={k: types[k] for k in L.DIFF_TYPES if k in types},
        needs_review=sum(1 for r in out if r["needs_review"]),
        better_match_flags=sum(1 for r in out if r["evidence"].get("better_match_outside_unit")),
        by_section={k: dict(v) for k, v in sorted(by_sec.items())},
        record_status=dict(Counter(r["status"] for r in st_out)),
        rewrite_clusters={k: v for k, v in clusters.items()},
        deleted_added_verification=verify,
    )
    L.json = json
    with open(os.path.join(L.OUT, "b2_body_stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in stats.items()
                      if k not in ("by_section",)}, ensure_ascii=False, indent=1))
    print("written 全文候选差异.jsonl (%d records) + 差异覆盖状态.jsonl (%d records)"
          % (len(out), len(st_out)))


if __name__ == "__main__":
    main()
