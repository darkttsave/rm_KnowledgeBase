#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 6 (phase C) -- step 1: build the LLM input batches.

The 534 B2 change candidates are far too many to submit at once, so they are
grouped into topic batches (C1 pairing review, deleted/added candidates, per
chapter substantive changes, special content).  Each batch is written as a plain
text file that is then read and judged by the model; the exact same file is kept
as the archived input for reproducibility.

Outputs
  ai_workplace/semantic/batches/B01_*.txt ... B12_*.txt
  ai_workplace/semantic/batches_manifest.json   (batch -> diff_id list)
"""
import os
import re
import sys
import json
from collections import Counter, defaultdict, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b2_lib as L

SEM = os.path.join(L.ROOT, "ai_workplace", "semantic")
BDIR = os.path.join(SEM, "batches")
os.makedirs(BDIR, exist_ok=True)

CHANGE = ("实质修改候选", "新增候选", "删除候选", "迁移或重组候选", "文字调整候选")
TYPE_CN = {"实质修改候选": "实质修改", "新增候选": "新增", "删除候选": "删除",
           "迁移或重组候选": "迁移", "文字调整候选": "文字调整", "内容一致": "一致",
           "编号变化（不计内容变化）": "编号变化",
           "引用编号更新（不计内容变化）": "引用编号更新"}


def clip(s, n):
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[:n] + "…"


def sec_label(sec):
    if not sec:
        return "—"
    return "%s %s" % (sec.get("no") or "（无编号）", sec.get("title") or "")


def main():
    diffs = L.load_jsonl(os.path.join(L.OUT, "全文候选差异.jsonl"))
    align = L.load_json(os.path.join(L.ALIGN, "章节对应关系.json"))
    body = L.load_json(os.path.join(L.OUT, "b2_body_stats.json"))
    sp = L.load_json(os.path.join(L.OUT, "special_diff.json"))

    by_id = {r["diff_id"]: r for r in diffs}
    units = {u["align_id"]: u for u in align["alignments"]}
    change = [r for r in diffs if r["diff_type"] in CHANGE]

    chapter = {}
    for u in align["alignments"]:
        if u["sections_2026"]:
            chapter[u["align_id"]] = u["sections_2026"][0]["path"][0]
        elif u["sections_2027"]:
            chapter[u["align_id"]] = u["sections_2027"][0]["path"][0]

    def unit_head(aid, extra=""):
        u = units.get(aid) or {}
        s26 = "、".join(x["no"] or x["title"] for x in u.get("sections_2026", [])) or "—"
        s27 = "、".join(x["no"] or x["title"] for x in u.get("sections_2027", [])) or "—"
        rel = {"kept": "保留", "renamed": "重命名", "moved": "迁移", "merged": "合并",
               "split": "拆分", "added": "疑似新增", "deleted": "疑似删除"}.get(u.get("relation"), "—")
        lines = ["## 单元 %s（%s，置信度 %.2f）%s" % (aid, rel, u.get("confidence", 0), extra),
                 "   2026: %s" % s26, "   2027: %s" % s27]
        if u.get("evidence"):
            lines.append("   B1 依据: " + "；".join(clip(e, 130) for e in u["evidence"][:3]))
        if u.get("content_delta_hint"):
            lines.append("   B1 内容线索: " + u["content_delta_hint"])
        return lines

    def diff_lines(r, tlen=180, with_type=True):
        out = []
        head = "[%s] %s" % (r["diff_id"], TYPE_CN.get(r["diff_type"], r["diff_type"]))
        if r.get("similarity") is not None:
            head += " sim=%.2f" % r["similarity"]
        a, b = r["a"], r["b"]
        if a:
            head += " | 2026 %s p%d" % (a["section_no"] or a["section_title"], a["physical_page"])
        if b:
            head += " | 2027 %s p%d" % (b["section_no"] or b["section_title"], b["physical_page"])
        out.append(head)
        if a:
            out.append("   2026: " + clip(a["text"], tlen))
        if b:
            out.append("   2027: " + clip(b["text"], tlen))
        ev = r.get("evidence") or {}
        notes = []
        if ev.get("numbers"):
            notes.append("数值 %s/%s" % (ev["numbers"].get("added"), ev["numbers"].get("removed")))
        if ev.get("units"):
            notes.append("单位 %s/%s" % (ev["units"].get("added"), ev["units"].get("removed")))
        if ev.get("refs"):
            notes.append("引用编号 %s→%s" % (ev["refs"].get("2026"), ev["refs"].get("2027")))
        if ev.get("marker_change"):
            notes.append("编号 %s→%s" % (ev["marker_change"].get("2026"), ev["marker_change"].get("2027")))
        if ev.get("tentative_pairing"):
            notes.append("推测配对(jaccard=%s)" % ev.get("bigram_jaccard"))
        if ev.get("rewrite_cluster"):
            notes.append("同章节双向残余%s" % (ev.get("cluster_leftovers"),))
        if ev.get("fulltext_best_similarity") is not None and r["diff_type"] in ("删除候选", "新增候选"):
            notes.append("全文最高相似=%.2f @ %s" % (ev["fulltext_best_similarity"],
                                                   ev.get("fulltext_best_section") or "—"))
        if ev.get("better_match_outside_unit"):
            notes.append("存在更优匹配 @ %s" % ev["better_match_outside_unit"].get("section_no"))
        if notes:
            out.append("   证据: " + "；".join(notes))
        return out

    batches = OrderedDict()

    # ---------------- B01: C1 tentative pairs ----------------
    tent = [r for r in diffs if r["evidence"].get("tentative_pairing")]
    batches["B01_推测配对复核"] = dict(
        title="C1 复核：41 对低相似度「推测配对」",
        instruction=(
            "这是 B2 用低阈值把同章节残余句强行配对的结果，未必正确。请逐条判断：\n"
            "  a) 确实是同一规则的改写（保留配对，进入 C2 分类）；\n"
            "  b) 配错了（应改为与另一句配对 / 应拆成 1 删除 + 1 新增）；\n"
            "  c) 无法判断。\n"
            "判断依据优先看：适用对象、触发条件、限制、例外、数值与效果是否一致。"),
        items=tent,
    )

    # ---------------- B02: B1 needs-review units ----------------
    rev_ids = [u["align_id"] for u in align["alignments"] if u["needs_review"]]
    items = []
    for aid in rev_ids:
        items.append({"align_id": aid, "unit": units[aid]})
    batches["B02_B1待核验映射"] = dict(
        title="C1 复核：B1 的 %d 个待核验章节映射" % len(rev_ids),
        instruction="复核这些章节对应是否成立；结合 B2 的正文差异证据判断是保留/重命名/迁移/合并/删除/新增。",
        items=items,
    )

    # ---------------- B03/B04: delete candidates ----------------
    deleted_units = {u["align_id"] for u in align["alignments"] if u["relation"] == "deleted"}
    d_in = [r for r in change if r["diff_type"] == "删除候选" and r["align_id"] in deleted_units]
    d_out = [r for r in change if r["diff_type"] == "删除候选" and r["align_id"] not in deleted_units]
    batches["B03_整节删除候选"] = dict(
        title="C1 复核：%d 个「疑似删除」章节中的删除候选（%d 条）" % (len(deleted_units), len(d_in)),
        instruction="这些章节在 B1 被判为疑似删除。请判断其规则是「实质取消」「已迁移到他处」还是「证据不足」。"
                    "B2 已给出每条在整个 2027 文档中的最高相似度与位置。",
        items=d_in,
    )
    batches["B04_保留章节内删除候选"] = dict(
        title="C1 复核：保留章节内的删除候选（%d 条）" % len(d_out),
        instruction="这些章节整体保留，但个别句段在 2027 找不到对应。请判断是实质取消、改写合并、还是配对遗漏。",
        items=d_out,
    )

    # ---------------- B05/B06: add candidates ----------------
    added_units = {u["align_id"] for u in align["alignments"] if u["relation"] == "added"}
    a_in = [r for r in change if r["diff_type"] == "新增候选" and r["align_id"] in added_units]
    a_out = [r for r in change if r["diff_type"] == "新增候选" and r["align_id"] not in added_units]
    batches["B05_整节新增候选"] = dict(
        title="C1 复核：疑似新增章节中的新增候选（%d 条）" % len(a_in),
        instruction="请判断是「实质新增机制」「既有机制的重组/搬移」还是「文档性内容（如变更说明、目录）」。"
                    "注意上游已决定：3 个空容器不计实质机制新增。",
        items=a_in,
    )
    batches["B06_保留章节内新增候选"] = dict(
        title="C1 复核：保留章节内的新增候选（%d 条）" % len(a_out),
        instruction="这些章节整体保留，但出现了新句段。请判断是实质新增、原有内容的拆分搬运、还是配对遗漏。",
        items=a_out,
    )

    # ---------------- B07..B10: substantive modifications by chapter ----------------
    mods = [r for r in change if r["diff_type"] in ("实质修改候选", "迁移或重组候选")]
    group = defaultdict(list)
    for r in mods:
        ch = chapter.get(r["align_id"], "（其他）")
        group[ch].append(r)

    def ch_batch(name, keys):
        items = [r for k in keys for r in group.get(k, [])]
        return dict(title="C2 语义分类：%s（%d 条）" % ("、".join(keys), len(items)),
                    instruction="按规则实际含义给每条差异分类，并说明判断依据。"
                                "重点核对适用对象、触发条件、限制、例外、数值与效果。",
                    items=items)

    batches["B07_机器人章节"] = ch_batch("B07", ["3 机器人与操作手"])
    batches["B08_场地章节"] = ch_batch("B08", ["4 比赛场地"])
    batches["B09_机制章节"] = ch_batch("B09", ["5 比赛机制"])
    batches["B10_流程判罚申诉"] = ch_batch("B10", ["6 比赛流程", "7 违规与判罚", "8 异常情况",
                                                "9 申诉", "2 重要概念", "1 前言",
                                                "阅读提示", "知识产权声明",
                                                "附录1 雷达信息波特性", "附录2 赛前流程说明",
                                                "附录3 未来规则规划"])

    # ---------------- B13: wording-only candidates ----------------
    words = [r for r in change if r["diff_type"] == "文字调整候选"]
    batches["B13_文字调整候选"] = dict(
        title="C2 语义分类：文字调整候选（%d 条）" % len(words),
        instruction="这些差异只改变了表述、相似度 >= 0.90 且无数值变化。请确认是否确为「仅表述调整」，"
                    "若其中隐藏实质变化（条件、例外、适用范围）请指出并升级分类。",
        items=words,
    )

    # ---------------- B11: tables ----------------
    trows = [r for r in sp["tables"]["rows"] if r["diff_type"] != "内容一致"]
    batches["B11_表格差异"] = dict(
        title="C4 表格：%d 张有差异的逻辑表（含 28 张数值变化）" % len(trows),
        instruction="重点核对参数、数值、列标题、适用对象；网格不可靠的表必须依赖 source_text_lines。",
        items=trows,
    )

    # ---------------- B12: formulas + figures ----------------
    frows = [r for r in sp["formulas"]["rows"] if r["diff_type"] != "内容一致"]
    irows = [r for r in sp["figures"]["rows"] if r["diff_type"] != "内容一致"]
    batches["B12_公式与插图"] = dict(
        title="C4 公式（%d）+ 插图（%d）" % (len(frows), len(irows)),
        instruction="公式需确认分式/上下标/变量含义；插图仅文本层无法判断，像素一致方可判定未变。",
        items=frows + irows,
    )

    # ---------------- render ----------------
    manifest = OrderedDict()
    for bid, b in batches.items():
        path = os.path.join(BDIR, bid + ".txt")
        lines = ["# %s" % b["title"], "", "## 分析要求", b["instruction"], "",
                 "## 输入", ""]
        cur = None
        for it in b["items"]:
            if "diff_id" in it:
                aid = it.get("align_id") or "AL-?"
                if aid != cur:
                    cur = aid
                    lines.append("")
                    lines += unit_head(aid)
                lines += diff_lines(it)
            elif "unit" in it:
                lines.append("")
                lines += unit_head(it["align_id"], "【B1 待核验】")
                u = it["unit"]
                lines.append("   B1 说明: " + clip(u.get("note") or "", 300))
                if u.get("evidence"):
                    for e in u["evidence"]:
                        lines.append("   - " + clip(e, 260))
            elif it.get("kind") == "table":
                a, t = it.get("table_2026"), it.get("table_2027")
                lines.append("")
                lines.append("[TABLE] %s  %s → %s" % (
                    it["diff_type"],
                    ("P%d %s" % (a["physical_page"], a["caption"] or a["table_no"] or "-")) if a else "—",
                    ("P%d %s" % (t["physical_page"], t["caption"] or t["table_no"] or "-")) if t else "—"))
                for side, x in (("2026", a), ("2027", t)):
                    if not x:
                        continue
                    lines.append("   %s: %s | %s行×%s列 空白率%s 丢词%s %s"
                                 % (side, clip(x.get("caption") or "", 80),
                                    x.get("rows", "?"), x.get("cols", "?"),
                                    x.get("blank_ratio"), x.get("grid_missing", "?"),
                                    ("(含%s条记录)" % x.get("record_count"))
                                    if (x.get("record_count") or 1) > 1 else ""))
                ev = it.get("evidence") or {}
                for k in ("numbers", "units", "column_headers", "row_labels", "shape", "cells"):
                    if ev.get(k):
                        lines.append("   %s: %s" % (k, clip(json.dumps(ev[k], ensure_ascii=False), 260)))
                if ev.get("grid_reliability"):
                    lines.append("   网格可靠性: " + clip(json.dumps(ev["grid_reliability"], ensure_ascii=False), 220))
            elif it.get("kind") == "figure":
                a, t = it.get("figure_2026"), it.get("figure_2027")
                lines.append("")
                lines.append("[FIG] %s  P%s %s → P%s %s" % (
                    it["diff_type"],
                    a["physical_page"] if a else "—", clip((a or {}).get("caption") or "无图注", 60),
                    t["physical_page"] if t else "—", clip((t or {}).get("caption") or "无图注", 60)))
                ev = it.get("evidence") or {}
                lines.append("   像素一致=%s 尺寸 %s→%s"
                             % (ev.get("image_hash_identical"),
                                [a["w"], a["h"]] if a else None, [t["w"], t["h"]] if t else None))
            else:
                a, t = it.get("formula_2026"), it.get("formula_2027")
                lines.append("")
                lines.append("[%s] %s  %s → %s" % (
                    (it.get("kind") or "formula").upper(), it["diff_type"],
                    ("P%d %s / %s" % (a["physical_page"], a.get("numerator") or clip(a.get("text") or "", 40),
                                      a.get("denominator") or "")) if a else "—",
                    ("P%d %s / %s" % (t["physical_page"], t.get("numerator") or clip(t.get("text") or "", 40),
                                      t.get("denominator") or "")) if t else "—"))
                if (a or {}).get("spans") or (t or {}).get("spans"):
                    lines.append("   上下标 2026=%s 2027=%s"
                                 % ((a or {}).get("spans"), (t or {}).get("spans")))
        Text = "\n".join(lines) + "\n"
        open(path, "w", encoding="utf-8").write(Text)
        nlines = Text.count("\n")
        diffs_in = [it["diff_id"] for it in b["items"] if "diff_id" in it]
        manifest[bid] = dict(file=os.path.basename(path), title=b["title"],
                             lines=nlines, items=len(b["items"]),
                             diff_ids=diffs_in)
        print("%-28s %4d 行  %3d 项  %s" % (bid, nlines, len(b["items"]), b["title"]))

    # ---- compact digest: one line per item, for the judging pass ----
    def dline(r):
        a, b = r["a"], r["b"]
        ev = r.get("evidence") or {}
        extra = []
        if ev.get("fulltext_best_similarity") is not None and r["diff_type"] in ("删除候选", "新增候选"):
            extra.append("best=%.2f@%s" % (ev["fulltext_best_similarity"], ev.get("fulltext_best_section") or "-"))
        if ev.get("numbers"):
            extra.append("num+%s-%s" % (ev["numbers"].get("added"), ev["numbers"].get("removed")))
        if ev.get("tentative_pairing"):
            extra.append("tentative")
        if ev.get("rewrite_cluster"):
            extra.append("rewrite_cluster")
        return "%s %s %s | 2026: %s | 2027: %s" % (
            r["diff_id"], TYPE_CN.get(r["diff_type"], r["diff_type"])[:4],
            r["align_id"] + (" " + ",".join(extra) if extra else ""),
            clip((a or {}).get("text") or "—", 70),
            clip((b or {}).get("text") or "—", 70))

    body_digest, spec_digest = [], []
    for bid, b in batches.items():
        if bid.startswith("B11") or bid.startswith("B12"):
            continue
        body_digest.append("")
        body_digest.append("### %s  %s" % (bid, b["title"]))
        cur = None
        for it in b["items"]:
            if "diff_id" in it:
                if it.get("align_id") != cur:
                    cur = it.get("align_id")
                    u = units.get(cur) or {}
                    s26 = "、".join(x["no"] or x["title"] for x in u.get("sections_2026", [])) or "-"
                    s27 = "、".join(x["no"] or x["title"] for x in u.get("sections_2027", [])) or "-"
                    body_digest.append("  [%s] %s -> %s (%s)" % (cur, s26, s27, u.get("relation")))
                body_digest.append("    " + dline(it))
            elif "unit" in it:
                u = it["unit"]
                body_digest.append("  [%s] B1待核验: %s -> %s" % (
                    it["align_id"],
                    "、".join(x["no"] or x["title"] for x in u["sections_2026"]) or "-",
                    "、".join(x["no"] or x["title"] for x in u["sections_2027"]) or "-"))
    open(os.path.join(SEM, "digest_body.txt"), "w", encoding="utf-8").write("\n".join(body_digest) + "\n")
    for it in trows:
        a, t = it.get("table_2026"), it.get("table_2027")
        ev = it.get("evidence") or {}
        spec_digest.append("T %s %s | 2026 P%s %s | 2027 P%s %s | nums+%s-%s | reliable=%s" % (
            it["diff_type"][:4],
            (a or {}).get("section_no") or "-",
            (a or {}).get("physical_page", "-"), clip((a or {}).get("caption") or (a or {}).get("table_no") or "-", 34),
            (t or {}).get("physical_page", "-"), clip((t or {}).get("caption") or (t or {}).get("table_no") or "-", 34),
            (ev.get("numbers") or {}).get("added"), (ev.get("numbers") or {}).get("removed"),
            it.get("grid_reliable")))
    for it in frows:
        a, t = it.get("formula_2026"), it.get("formula_2027")
        spec_digest.append("F %s %s | 2026 P%s %s / %s | 2027 P%s %s / %s" % (
            it["diff_type"][:4], it.get("kind"),
            (a or {}).get("physical_page", "-"), (a or {}).get("numerator") or clip((a or {}).get("text") or "-", 26),
            (a or {}).get("denominator") or "", 
            (t or {}).get("physical_page", "-"), (t or {}).get("numerator") or clip((t or {}).get("text") or "-", 26),
            (t or {}).get("denominator") or ""))
    for it in irows:
        a, t = it.get("figure_2026"), it.get("figure_2027")
        ev = it.get("evidence") or {}
        spec_digest.append("I %s pixel_same=%s | 2026 P%s %s | 2027 P%s %s" % (
            it["diff_type"][:4], ev.get("image_hash_identical"),
            (a or {}).get("physical_page", "-"), clip((a or {}).get("caption") or "无图注", 30),
            (t or {}).get("physical_page", "-"), clip((t or {}).get("caption") or "无图注", 30)))
    open(os.path.join(SEM, "digest_special.txt"), "w", encoding="utf-8").write("\n".join(spec_digest) + "\n")
    print("digest lines: body=%d special=%d" % (len(body_digest), len(spec_digest)))

    json.dump(manifest, open(os.path.join(SEM, "batches_manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    covered = set()
    for v in manifest.values():
        covered |= set(v["diff_ids"])
    only_body = {r["diff_id"] for r in change}
    print("\nchange diffs covered by batches: %d / %d" % (len(covered & only_body), len(only_body)))
    print("special rows in batches: %d" % (
        len(trows) + len(frows) + len(irows)))
    print("written", SEM)


if __name__ == "__main__":
    main()
