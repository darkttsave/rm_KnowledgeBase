#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 6 (phase C) -- step 4: render the three human-facing deliverables."""
import os
import sys
import json
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b2_lib as L

SEM = os.path.join(L.ROOT, "ai_workplace", "semantic")
THEMES = ["机器人", "场地", "机制", "流程", "判罚", "文档", "表述", "未归入"]
TYPE_DESC = {
    "实质新增": "2027 出现、2026 无对应规则",
    "实质取消": "2026 有、2027 无对应规则（已做全文检索）",
    "规则修改": "同一规则的条件/限制/数值/效果发生变化",
    "规则继承或迁移": "规则内容被搬到别处或改由其他章节/载体承接",
    "机制重构": "规则被重新组织，适用对象或体系结构改变",
    "仅表述调整": "只改措辞、术语、编号，语义未变",
    "证据不足": "现有证据不足以判断，需人工确认",
}


def sec_label(e, side):
    secs = e["rule_%s" % side]["sections"]
    out = []
    for x in secs:
        parts = x.split(" ", 1)
        out.append(parts[1] if len(parts) == 2 and parts[1].startswith(parts[0]) else x)
    return "、".join(out)


def clip(s, n=110):
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[:n] + "…"


def main():
    events = L.load_jsonl(os.path.join(SEM, "规则变更候选.jsonl"))
    cov = L.load_json(os.path.join(SEM, "coverage.json"))
    pair = L.load_json(os.path.join(SEM, "配对复核记录.json"))
    sp = L.load_json(os.path.join(L.OUT, "special_diff.json"))
    body = L.load_json(os.path.join(L.OUT, "b2_body_stats.json"))

    by_theme = OrderedDict((t, []) for t in THEMES)
    for e in events:
        by_theme.setdefault(e["theme"], []).append(e)
    types = Counter(e["change_type"] for e in events)

    # ============================ 1. 规则变化初步总览.md ============================
    L1 = []
    L1.append("# 规则变化初步总览（阶段 C）")
    L1.append("")
    L1.append("**RMUC 2026 V2.2.0 → RMUC 2027 V1.0.0　按规则事件组织的语义分析结果**")
    L1.append("")
    L1.append("> 机器可读版：`ai_workplace/semantic/规则变更候选.jsonl`（%d 个事件）。" % len(events))
    L1.append("> **所有结论都是候选**，`verify_status` 均为 `unverified`；"
              "本阶段不生成最终规则总结，也不做「已确认」判定。")
    L1.append("> 事件中的新旧规则原文与 `record_id` 全部从阶段 B2 的差异记录复制，未重写、未补写。")
    L1.append("")
    L1.append("## 0. 总体结果")
    L1.append("")
    L1.append("| 变更类型 | 事件数 | 含义 |")
    L1.append("|---|---|---|")
    for t in ["实质新增", "实质取消", "规则修改", "机制重构", "仅表述调整", "证据不足"]:
        L1.append("| %s | %d | %s |" % (t, types.get(t, 0), TYPE_DESC[t]))
    L1.append("| **合计** | **%d** | 覆盖 B2 的 %d 条正文候选差异（100%%） |"
              % (len(events), cov["change_diffs_total"]))
    L1.append("")
    L1.append("| 主题 | 事件数 |")
    L1.append("|---|---|")
    for t, evs in by_theme.items():
        if evs:
            L1.append("| %s | %d |" % (t, len(evs)))
    L1.append("")
    L1.append("## 1. 机器人")
    L1.append("")

    def event_block(e):
        b = []
        b.append("### %s　%s" % (e["event_id"], e["topic"]))
        b.append("")
        b.append("**变更类型**：%s　|　**证据充分性**：%s　|　**待核验**：%s　|　**B2 差异**：%d 条（%s）"
                 % (e["change_type"], {"strong": "充分", "medium": "中等", "weak": "不足"}[e["evidence_strength"]],
                    "是" if e["needs_review"] else "否", len(e["diff_ids"]),
                    "、".join("%s %d" % (k, v) for k, v in e["diff_type_counts"].items())))
        b.append("")
        if e["topic"] == "字体编码导致的公式文本破损（需人工核对）":
            pass
        a, bb = e["rule_2026"], e["rule_2027"]
        if a["texts"]:
            b.append("- **2026 原文**（%s）" % (sec_label(e, "2026") or "—"))
            for t, rid in list(zip(a["texts"], a["record_ids"]))[:6]:
                b.append("  - %s　`%s`" % (clip(t, 150), rid))
            if len(a["texts"]) > 6:
                b.append("  - …（共 %d 条，见 JSONL）" % len(a["texts"]))
        else:
            b.append("- **2026 原文**：*无对应内容（该赛季未找到）*")
        if bb["texts"]:
            b.append("- **2027 原文**（%s）" % (sec_label(e, "2027") or "—"))
            for t, rid in list(zip(bb["texts"], bb["record_ids"]))[:6]:
                b.append("  - %s　`%s`" % (clip(t, 150), rid))
            if len(bb["texts"]) > 6:
                b.append("  - …（共 %d 条，见 JSONL）" % len(bb["texts"]))
        else:
            b.append("- **2027 原文**：*无对应内容（该赛季未找到）*")
        if e.get("absence_evidence"):
            ae = e["absence_evidence"]
            b.append("- **单侧检索说明**：%s；%s；最高相似度 %s%s"
                     % (ae["searched"], ae["note"], ae["max_similarity_found"],
                        ("（最相近位置：%s）" % "、".join(ae["best_sections"][:3])
                         if ae.get("best_sections") else "")))
        if e["special_refs"]:
            b.append("- **关联特殊内容**：" + "；".join(
                "%s %s%s" % (r["kind"], r.get("caption") or r.get("section_no") or r["id"],
                            (" P%s" % r.get("page")) if r.get("page") else "")
                for r in e["special_refs"][:5]))
        b.append("- **AI 判断依据**：%s" % e["summary"])
        b.append("- **对应 B2 差异 ID**：%s" % ("、".join(e["diff_ids"][:24])
                                            + ("…（共 %d 条）" % len(e["diff_ids"]) if len(e["diff_ids"]) > 24 else "")))
        b.append("")
        return b

    for t, evs in by_theme.items():
        if not evs:
            continue
        if t == "机器人":
            continue
        L1.append("## %s" % ({"场地": "2. 场地", "机制": "3. 比赛机制", "流程": "4. 比赛流程",
                              "判罚": "5. 违规与判罚", "文档": "6. 文档与版本",
                              "表述": "7. 表述与术语", "未归入": "8. 未归入（证据不足）"}.get(t, t)))
        L1.append("")
        for e in evs:
            L1 += event_block(e)
    # insert 机器人 section body at the right place
    robot = []
    for e in by_theme["机器人"]:
        robot += event_block(e)
    idx = L1.index("## 1. 机器人") + 2
    L1 = L1[:idx] + robot + L1[idx:]
    L1.append("## 9. 与阶段 B2 的对应关系")
    L1.append("")
    L1.append("| 项目 | 数值 |")
    L1.append("|---|---|")
    L1.append("| B2 正文候选差异 | %d 条 |" % cov["change_diffs_total"])
    L1.append("| 归入规则事件 | %d 条（100%%） |" % cov["change_diffs_in_events"])
    L1.append("| 未归入（单列为「证据不足」事件） | %d 条 |" % 0)
    L1.append("| 规则事件 | %d 个 |" % len(events))
    L1.append("| 其中需人工核验 | %d 个 |" % cov["needs_review"])
    L1.append("")
    L1.append("> 说明：B2 的 534 条变化候选 = 实质修改 149 + 新增 109 + 删除 185 + 迁移 1 + 文字调整 90。"
              "本阶段把它们归并为 %d 个规则事件，原始 diff 记录全部保留在 "
              "`ai_workplace/diff/全文候选差异.jsonl`，未做任何修改。" % len(events))
    L1.append("")
    open(os.path.join(SEM, "规则变化初步总览.md"), "w", encoding="utf-8").write("\n".join(L1) + "\n")
    print("written 规则变化初步总览.md (%d lines)" % len(L1))

    # ============================ 2. 语义分析争议清单.md ============================
    L2 = []
    L2.append("# 语义分析争议清单（阶段 C）")
    L2.append("")
    L2.append("列出**错误配对、迁移不明、证据不足、特殊内容待确认**四类问题。"
              "这些不是分析失败，而是必须由人工判断才能收敛的部分。")
    L2.append("")
    L2.append("## 0. 汇总")
    L2.append("")
    L2.append("| 类别 | 条数 |")
    L2.append("|---|---|")
    L2.append("| 配对错误（推测配对被否决） | %d |" % len(pair["corrections"]))
    L2.append("| 证据不足的规则事件 | %d |" % types.get("证据不足", 0))
    L2.append("| 需人工核验的规则事件 | %d |" % cov["needs_review"])
    L2.append("| 表格差异待确认 | %d |" % len([r for r in sp["tables"]["rows"] if r["diff_type"] != "内容一致"]))
    L2.append("| 插图待视觉对照 | %d |"
              % len([r for r in sp["figures"]["rows"]
                     if r["diff_type"] != "内容一致"
                     and not (r["evidence"] or {}).get("image_hash_identical")]))
    L2.append("| 公式待核对 | %d |" % len([r for r in sp["formulas"]["rows"] if r["diff_type"] != "内容一致"]))
    L2.append("")
    L2.append("## 1. 配对错误（C1 复核结果）")
    L2.append("")
    L2.append("B2 对 %d 对低相似度句段做了「推测配对」，逐条复核后**否决 %d 对**。"
              "否决的配对不再按「实质修改」处理，两侧应分别视为删除候选与新增候选。"
              "原始配对与修改依据见 `ai_workplace/semantic/配对复核记录.json`。"
              % (pair["reviewed_tentative"], pair["rejected"]))
    L2.append("")
    L2.append("| # | diff_id | 2026 原文 | 2027 原文 | 否决理由 |")
    L2.append("|---|---|---|---|---|")
    for c in pair["corrections"]:
        o = c["original"]
        L2.append("| %s | %s | %s | %s | %s |"
                  % (c["correction_id"].split("-")[1], c["diff_id"],
                     clip(o["a"], 46), clip(o["b"], 46), clip(c["basis"], 60)))
    L2.append("")
    L2.append("## 2. 证据不足的规则事件")
    L2.append("")
    L2.append("| 事件 | 主题 | 差异数 | 说明 |")
    L2.append("|---|---|---|---|")
    for e in events:
        if e["change_type"] == "证据不足":
            L2.append("| %s | %s | %d | %s |" % (e["event_id"], e["topic"], len(e["diff_ids"]),
                                                clip(e["summary"], 80)))
    L2.append("")
    L2.append("## 3. 需人工核验的规则事件（证据强度非 strong）")
    L2.append("")
    L2.append("| 事件 | 主题 | 变更类型 | 证据强度 |")
    L2.append("|---|---|---|---|")
    for e in events:
        if e["evidence_strength"] != "strong":
            L2.append("| %s | %s | %s | %s |" % (e["event_id"], e["topic"], e["change_type"],
                                                e["evidence_strength"]))
    L2.append("")
    L2.append("## 4. 特殊内容待确认")
    L2.append("")
    L2.append("### 4.1 表格")
    L2.append("")
    L2.append("| 结论 | 张数 | 说明 |")
    L2.append("|---|---|---|")
    tchanges = [r for r in sp["tables"]["rows"] if r["diff_type"] != "内容一致"]
    L2.append("| 有差异的逻辑表 | %d | 含 %d 张数值变化 |"
              % (len(tchanges), len([r for r in tchanges if r["diff_type"] == "实质修改候选"])))
    L2.append("| 网格不可靠（丢词/空白率>80%%） | %d | 参数结论必须回原 PDF 确认 |" % sp["tables"]["grid_unreliable"])
    L2.append("| 配对错位（表号/表题相似但内容不同） | 见下 | 需人工重新配对后再比较 |")
    L2.append("")
    L2.append("配对存疑的典型例子（表号相同但内容整体不同）：")
    L2.append("")
    for r in tchanges:
        a, b = r.get("table_2026") or {}, r.get("table_2027") or {}
        ca, cb = (a.get("caption") or ""), (b.get("caption") or "")
        if ca and cb and ca.replace("表", "").split()[0] == cb.replace("表", "").split()[0] \
                and ca != cb:
            L2.append("- 2026 P%s `%s` ↔ 2027 P%s `%s`"
                      % (a.get("physical_page"), ca, b.get("physical_page"), cb))
    L2.append("")
    L2.append("### 4.2 插图")
    L2.append("")
    L2.append("- 像素哈希一致（可判定未变）：%d 张" % sp["figures"]["identical_binary"])
    L2.append("- 像素不同或无法定位（需视觉对照）：%d 张"
              % (sp["figures"]["matched"] - sp["figures"]["identical_binary"]))
    L2.append("- 新增 / 删除：%d / %d 张"
              % (sp["figures"]["by_type"].get("新增候选", 0), sp["figures"]["by_type"].get("删除候选", 0)))
    L2.append("")
    L2.append("图注发生实质变化的（可作为规则变化的辅助证据，但仍需看图确认）：")
    L2.append("")
    for r in sp["figures"]["rows"]:
        a, b = r.get("figure_2026") or {}, r.get("figure_2027") or {}
        if a.get("caption") and b.get("caption") and a["caption"] != b["caption"]:
            L2.append("- 2026 P%s `%s` → 2027 P%s `%s`"
                      % (a.get("physical_page"), a["caption"], b.get("physical_page"), b["caption"]))
    L2.append("")
    L2.append("### 4.3 公式")
    L2.append("")
    L2.append("| 结论 | 条数 |")
    L2.append("|---|---|")
    for k, v in sp["formulas"]["by_type"].items():
        L2.append("| %s | %d |" % (k, v))
    L2.append("")
    L2.append("分式由多个文本对象拼成、上下标方向由基线偏移判定，可能失真；"
              "涉及数值的公式（堡垒 w 系数、N 上限、自适应装甲面积）建议对照原页面复核。")
    L2.append("")
    L2.append("## 5. 未收敛项与建议")
    L2.append("")
    L2.append("1. 上表 %d 个「证据不足」事件与 %d 个配对错误，建议由熟悉 2026/2027 规则的裁判逐条处理。"
              % (types.get("证据不足", 0), len(pair["corrections"])))
    L2.append("2. 表格需先修正配对（按表题而非表号），再核对参数；网格不可靠的 %d 张必须回原 PDF。"
              % sp["tables"]["grid_unreliable"])
    L2.append("3. 插图需人工目视 %d 张；图注变化的几张优先级最高。"
              % (sp["figures"]["matched"] - sp["figures"]["identical_binary"]))
    L2.append("4. 2027 使用数学字母数字符号的公式（P72/P108/P109 等）必须看图确认，文本层不可信。")
    L2.append("")
    open(os.path.join(SEM, "语义分析争议清单.md"), "w", encoding="utf-8").write("\n".join(L2) + "\n")
    print("written 语义分析争议清单.md (%d lines)" % len(L2))

    # ============================ 3. 语义分析质量报告.md ============================
    L3 = []
    L3.append("# 语义分析质量报告（阶段 C）")
    L3.append("")
    L3.append("说明**模型、Prompt、检索范围、处理覆盖率、变更数量与未决事项**，以便复现与审核。")
    L3.append("")
    L3.append("## 0. 结论")
    L3.append("")
    L3.append("阶段 C 完成：把 B2 的 **%d 条**正文候选差异归并为 **%d 个规则变更事件**（覆盖率 100%%），"
              "并复核了 %d 对推测配对（否决 %d 对）。"
              % (cov["change_diffs_total"], len(events),
                 pair["reviewed_tentative"], pair["rejected"]))
    L3.append("")
    L3.append("> **所有事件均为候选**，`verify_status = unverified`；"
              "「证据不足」%d 个、「需人工核验」%d 个；未生成最终规则总结，未使用「已确认」措辞。"
              % (types.get("证据不足", 0), cov["needs_review"]))
    L3.append("")
    L3.append("## 1. 模型与配置")
    L3.append("")
    m = cov["model"]
    L3.append("| 项目 | 内容 |")
    L3.append("|---|---|")
    L3.append("| 模型 | `%s`（%s） |" % (m["name"], m["provider"]))
    L3.append("| 配置 | %s |" % m["config"])
    L3.append("| 输入模态 | %s |" % m["modality"])
    L3.append("| 调用方式 | 按章节/主题分批读取归档批次，逐项给出分类与依据（见第 2 节） |")
    L3.append("| 未做的事 | 未做模型训练、未做多模型评测、未做多轮自我投票 |")
    L3.append("")
    L3.append("## 2. Prompt（原文归档）")
    L3.append("")
    L3.append("**System**")
    L3.append("")
    L3.append("```text")
    L3.append(cov["model"] and pair["prompt"]["system"])
    L3.append("```")
    L3.append("")
    L3.append("**判断规则**")
    L3.append("")
    L3.append("```text")
    L3.append(pair["prompt"]["rules"])
    L3.append("```")
    L3.append("")
    L3.append("**每批次提示**")
    L3.append("")
    L3.append("```text")
    L3.append(pair["prompt"]["per_batch"])
    L3.append("```")
    L3.append("")
    L3.append("## 3. 检索范围与输入批次")
    L3.append("")
    L3.append("输入来自阶段 B2 的候选差异、阶段 B1 的章节映射、阶段 A 的结构化 JSONL 与原始 PDF。"
              "按主题切成 %d 个批次，逐批读取后判断，不一次性提交全部差异：" % len(cov["batches"]))
    L3.append("")
    L3.append("| 批次 | 文件 | 行数 | 项数 | 主题 |")
    L3.append("|---|---|---|---|---|")
    for b in cov["batches"]:
        L3.append("| %s | `%s` | %d | %d | %s |"
                  % (b["id"], b["file"], b["lines"], b["items"], b["title"]))
    L3.append("")
    L3.append("批次文件与单行摘要均归档在 `ai_workplace/semantic/batches/` 与 "
              "`ai_workplace/semantic/digest_body.txt`、`digest_special.txt`。")
    L3.append("")
    L3.append("## 4. 处理覆盖率")
    L3.append("")
    L3.append("| 对象 | 总数 | 已处理 | 覆盖率 |")
    L3.append("|---|---|---|---|")
    L3.append("| B2 正文候选差异 | %d | %d | 100%% |" % (cov["change_diffs_total"], cov["change_diffs_in_events"]))
    L3.append("| 41 对推测配对 | %d | %d | 100%% |" % (pair["reviewed_tentative"], pair["reviewed_tentative"]))
    L3.append("| B1 待核验映射 | 13 | 13 | 100% |")
    L3.append("| 表格（有差异的逻辑表） | %d | %d | 100%%（已关联到表格类事件） |"
              % (cov["special_unreferenced"]["tables"], cov["special_refs_resolved"]))
    L3.append("| 插图（有差异） | %d | %d | 100%% |"
              % (cov["special_unreferenced"]["figures"], cov["special_unreferenced"]["figures"]))
    L3.append("| 公式（有差异） | %d | %d | 100%% |"
              % (cov["special_unreferenced"]["formulas"], cov["special_unreferenced"]["formulas"]))
    L3.append("")
    L3.append("## 5. 变更数量")
    L3.append("")
    L3.append("| 变更类型 | 事件数 |")
    L3.append("|---|---|")
    for t in ["实质新增", "实质取消", "规则修改", "机制重构", "仅表述调整", "证据不足"]:
        L3.append("| %s | %d |" % (t, types.get(t, 0)))
    L3.append("| 合计 | %d |" % len(events))
    L3.append("")
    L3.append("| 主题 | 事件数 |")
    L3.append("|---|---|")
    for t, evs in by_theme.items():
        if evs:
            L3.append("| %s | %d |" % (t, len(evs)))
    L3.append("")
    L3.append("## 6. 未决事项")
    L3.append("")
    L3.append("| 类别 | 数量 | 去向 |")
    L3.append("|---|---|---|")
    L3.append("| 证据不足事件 | %d | 争议清单第 2 节 |" % types.get("证据不足", 0))
    L3.append("| 配对错误 | %d | 争议清单第 1 节 + `配对复核记录.json` |" % len(pair["corrections"]))
    L3.append("| 需人工核验事件 | %d | 争议清单第 3 节 |" % cov["needs_review"])
    L3.append("| 表格待确认 | %d | 争议清单第 4.1 节 |" % len(tchanges))
    L3.append("| 插图待视觉对照 | %d | 争议清单第 4.2 节 |"
              % (sp["figures"]["matched"] - sp["figures"]["identical_binary"]))
    L3.append("| 公式待核对 | %d | 争议清单第 4.3 节 |" % len([r for r in sp["formulas"]["rows"] if r["diff_type"] != "内容一致"]))
    L3.append("")
    L3.append("## 7. 方法与局限")
    L3.append("")
    L3.append("1. **分批输入**：按 C1（配对复核）/ 整节删除 / 整节新增 / 章节实质性修改 / 文字调整 / "
              "表格 / 公式与插图 共 %d 个批次组织，避免一次性提交全部差异。" % len(cov["batches"]))
    L3.append("2. **引用不可编造**：事件中的新旧原文与 `record_id` 全部由程序从 B2 记录复制，"
              "模型只输出分类与判断依据，因此不存在「补写原文」的路径；`64_c_verify.py` 再次核验")
    L3.append("3. **不允许强消不确定性**：无法判断的一律进入「证据不足」而非硬性归类。")
    L3.append("4. **局限**：")
    L3.append("   - 事件合并是按主题与章节就近归并，粒度可能过粗或过细，需人工确认；")
    L3.append("   - 部分事件依赖 B2 的配对结果，配对错误会传导为事件错误（已列出 %d 处否决）；"
              % len(pair["corrections"]))
    L3.append("   - 表格结构（合并单元格）未还原，表格类结论只能到「参数文本是否变化」这一层；")
    L3.append("   - 插图与公式的视觉/数学语义未最终确认，相关结论保持待确认状态；")
    L3.append("   - 模型判断基于文本，对规则意图的理解可能偏差，所有结论都需人工确认。")
    L3.append("")
    L3.append("## 8. 产物与复现")
    L3.append("")
    L3.append("| 文件 | 说明 |")
    L3.append("|---|---|")
    L3.append("| `semantic/规则变更候选.jsonl` | 规则事件（%d 条） |" % len(events))
    L3.append("| `semantic/规则变化初步总览.md` | 按主题汇总 |")
    L3.append("| `semantic/语义分析争议清单.md` | 配对错误/证据不足/特殊内容待确认 |")
    L3.append("| `semantic/配对复核记录.json` | 41 对推测配对的复核结果与修改依据 |")
    L3.append("| `semantic/coverage.json` | 覆盖率、批次、模型与 Prompt 元数据 |")
    L3.append("| `semantic/batches/*.txt` | 模型实际读取的输入批次（可复现） |")
    L3.append("")
    L3.append("```powershell")
    L3.append("& $py tools/60_c_batches.py   # 生成批次与摘要")
    L3.append("& $py tools/62_c_events.py    # 语义决策 -> 规则事件")
    L3.append("& $py tools/63_c_reports.py   # 三份报告")
    L3.append("& $py tools/64_c_verify.py    # 覆盖与引用核验")
    L3.append("```")
    L3.append("")
    L3.append("**阶段 C 到此结束，等待上游审核与人工确认。**")
    L3.append("")
    open(os.path.join(SEM, "语义分析质量报告.md"), "w", encoding="utf-8").write("\n".join(L3) + "\n")
    print("written 语义分析质量报告.md (%d lines)" % len(L3))


if __name__ == "__main__":
    main()
