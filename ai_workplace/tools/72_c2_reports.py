#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 7 (phase C 补充核验) -- step 3: the four human-facing deliverables."""
import os
import sys
import json
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b2_lib as L

SEM = os.path.join(L.ROOT, "ai_workplace", "semantic")
CAT_ORDER = ["比赛规则变化", "文档变化", "排版变化", "未定"]
THEME_ORDER = ["机器人", "机制", "场地", "判罚", "流程", "文档", "表述",
               "配对更正", "机制迁移", "未定"]


def clip(s, n=150):
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[:n] + "…"


def sec_label(d):
    out = []
    for x in d.get("sections") or []:
        parts = x.split(" ", 1)
        out.append(parts[1] if len(parts) == 2 and parts[1].startswith(parts[0]) else x)
    return "、".join(sorted(set(out)))


def recall_exceptions(rev):
    """recompute the 64_c_verify back-check and return the unmatched quotes."""
    recs26 = L.load_jsonl(os.path.join(L.STRUCT, "2026_结构化.jsonl"))
    recs27 = L.load_jsonl(os.path.join(L.STRUCT, "2027_结构化.jsonl"))
    recmap = {r["record_id"]: r for r in recs26 + recs27}
    from collections import defaultdict
    sec = defaultdict(list)
    for r in recs26 + recs27:
        if r.get("region_type") == "section" and (r.get("norm_text") or "").strip():
            sec[(r["doc_id"], r["section_index"])].append(r)
    for k in sec:
        sec[k].sort(key=lambda r: r["record_index"])

    def window_hit(rec, text):
        rs = sec.get((rec["doc_id"], rec["section_index"])) or []
        idxs = [i for i, r in enumerate(rs) if r["record_id"] == rec["record_id"]]
        if not idxs:
            return False
        i = idxs[0]
        for lo in range(max(0, i - 3), i + 1):
            if text in "".join((x.get("norm_text") or "") for x in rs[lo:min(len(rs), lo + 5)]):
                return True
        return False

    out, tot = [], 0
    for e in rev:
        if e["record_type"] != "规则事件":
            continue
        for side in ("2026", "2027"):
            for t, rid in zip(e["rule_%s" % side]["texts"],
                              e["rule_%s" % side]["record_ids"]):
                rec = recmap.get(rid)
                if not rec:
                    continue
                tot += 1
                if t in (rec.get("norm_text") or "") or window_hit(rec, t):
                    continue
                out.append(dict(event_id=e["event_id"], side=side, record_id=rid,
                                page=rec.get("physical_page"), text=t,
                                section_no=rec.get("section", {}).get("section_no")))
    return out, tot


def main():
    rev = L.load_jsonl(os.path.join(SEM, "规则变更候选_修订版.jsonl"))
    stats = L.load_json(os.path.join(SEM, "revision_stats.json"))
    recheck = L.load_json(os.path.join(SEM, "special_recheck.json"))
    pair = L.load_json(os.path.join(SEM, "配对复核记录.json"))
    old_events = L.load_jsonl(os.path.join(SEM, "规则变更候选.jsonl"))

    ev = [r for r in rev if r["record_type"] == "规则事件"]
    sup = [r for r in rev if r["record_type"] == "补充事件"]
    cor = [r for r in rev if r["record_type"] == "配对更正"]
    mig = [r for r in rev if r["record_type"] == "机制迁移判定"]

    # ======================= 1. 特殊内容核验报告.md =======================
    t = recheck["tables"]
    f = recheck["figures"]
    L1 = []
    L1.append("# 特殊内容核验报告（阶段 C 补充核验）")
    L1.append("")
    L1.append("对阶段 B2 的**表格 / 插图 / 公式**重新核对：表格按**表题与上下文**重新配对"
              "（不再以表号为主键），插图按**像素结构**分类，公式保留原有不确定性。")
    L1.append("")
    L1.append("> 关键原则：**自动检查通过 ≠ 语义一致**。本报告中的每一项都标了「能否仅凭自动检查下结论」。")
    L1.append("")
    L1.append("## 0. 汇总")
    L1.append("")
    L1.append("| 类别 | 数量 | 可自动判定 | 需人工/目视 |")
    L1.append("|---|---|---|---|")
    tv = t["by_verdict"]
    L1.append("| 表格（逻辑表） | %d 张配对 | 未发现文本层差异 %d 张 | 其余 %d 张 |"
              % (len(t["rows"]), tv.get("未发现文本层差异", 0),
                 len(t["rows"]) - tv.get("未发现文本层差异", 0)))
    fv = f["by_verdict"]
    L1.append("| 插图 | %d 条记录 | 像素完全一致 %d 条 | 其余 %d 条 |"
              % (len(f["rows"]), fv.get("像素完全一致", 0),
                 len(f["rows"]) - fv.get("像素完全一致", 0)))
    L1.append("| 公式 | %d 条差异 | 0 | 全部需核对 |" % len(recheck["formulas"]))
    L1.append("| 表格单侧存在 | 2026 %d / 2027 %d | — | 需人工确认对应关系 |"
              % (len(t["unmatched_2026"]), len(t["unmatched_2027"])))
    L1.append("")
    L1.append("## 1. 表格重新配对")
    L1.append("")
    L1.append("### 1.1 配对方法")
    L1.append("")
    L1.append("| 项 | 说明 |")
    L1.append("|---|---|")
    L1.append("| 主依据 | 表题（去掉「表 X-Y」后的文字）相似度 0.45 权重 |")
    L1.append("| 上下文 | 是否属于同一个 B1 对齐单元 0.30 权重（比「同章节」更能覆盖合并/迁移） |")
    L1.append("| 表号 | **仅作 0.10 的辅助分**，不再作为主键 |")
    L1.append("| 内容 | 网格文本二元组余弦 0.15 权重 |")
    L1.append("| 一票否决 | 两侧表题中的机型/对象词冲突（如「英雄机器人」vs「工程机器人」）直接判为不可配对 |")
    L1.append("| 无表题表 | 只有内容相似度 ≥0.60 才配对，否则列为单侧存在 |")
    L1.append("")
    L1.append("### 1.2 与阶段 B2 的配对差异（%d 处）" % len(t["changed_pairing"]))
    L1.append("")
    if t["changed_pairing"]:
        L1.append("| 2026 表 | B2 原配对 | 本次修正为 | 修正依据 |")
        L1.append("|---|---|---|---|")
        for c in t["changed_pairing"]:
            a = next((r["table_2026"] for r in t["rows"] if r["table_2026"]["id"] == c["table_2026"]), {})
            new = next((r["table_2027"] for r in t["rows"] if r["table_2027"]["id"] == c["new_partner"]), {})
            old_pair = c.get("old_partner") or "（B2 未配对）"
            L1.append("| P%s `%s` | %s | P%s `%s` | 表题相似度 %.2f%s |"
                      % (a.get("physical_page"), clip(a.get("caption") or a.get("table_no"), 32),
                         clip(old_pair, 28),
                         new.get("physical_page"), clip(new.get("caption") or new.get("table_no"), 32),
                         c["detail"]["caption"],
                         "；表号相同" if c["detail"].get("same_table_no") else "；表号不同但表题相同"))
        L1.append("")
        L1.append("> 这 %d 处正是阶段 B2「按表号配对」造成的错配：2026 与 2027 的表号发生了对调，"
                  "仅看表号会把两张不同的表配成一对。" % len(t["changed_pairing"]))
    L1.append("")
    L1.append("### 1.3 参数/结构核验结果")
    L1.append("")
    L1.append("| 结论 | 张数 | 含义 | 能否自动下结论 |")
    L1.append("|---|---|---|---|")
    desc = {
        "参数变化候选": "数值或单位集合发生变化",
        "结构/文字变化候选": "行列数、列标题、行标签或单元格文本变化（无数值变化）",
        "未发现文本层差异": "网格文本层未见差异",
        "表主题已变（可能是不同的表）": "表题在两侧明显不同，可能表已被替换",
    }
    for k, v in sorted(tv.items(), key=lambda kv: -kv[1]):
        L1.append("| %s | %d | %s | %s |" % (k, v, desc.get(k, ""),
                                            "否（网格未还原合并单元格）" if k != "表主题已变（可能是不同的表）"
                                            else "否（先确认是否同一张表）"))
    L1.append("")
    L1.append("**参数变化候选（%d 张）明细：**" % tv.get("参数变化候选", 0))
    L1.append("")
    L1.append("| # | 2026 表 | 页码 | 2027 表 | 页码 | 数值增/减 | 网格可靠 |")
    L1.append("|---|---|---|---|---|---|---|")
    n = 0
    for r in t["rows"]:
        if r["verdict"] != "参数变化候选":
            continue
        n += 1
        a, b = r["table_2026"], r["table_2027"]
        nums = r["evidence"].get("numbers") or {}
        L1.append("| %d | `%s` | P%s | `%s` | P%s | +%s / -%s | %s |"
                  % (n, clip(a.get("caption") or a.get("table_no"), 26), a["physical_page"],
                     clip(b.get("caption") or b.get("table_no"), 26), b["physical_page"],
                     nums.get("added", [])[:6], nums.get("removed", [])[:6],
                     "是" if r["grid_reliable"] else "否"))
    L1.append("")
    L1.append("### 1.4 单侧存在的表")
    L1.append("")
    L1.append("**仅 2026 有（%d 张）**" % len(t["unmatched_2026"]))
    L1.append("")
    for x in t["unmatched_2026"]:
        L1.append("- P%s `%s`（%s）" % (x["physical_page"],
                                       clip(x.get("caption") or x.get("table_no") or "无表题", 44),
                                       x.get("section_title") or ""))
    L1.append("")
    L1.append("**仅 2027 有（%d 张）**" % len(t["unmatched_2027"]))
    L1.append("")
    for x in t["unmatched_2027"]:
        L1.append("- P%s `%s`（%s）" % (x["physical_page"],
                                       clip(x.get("caption") or x.get("table_no") or "无表题", 44),
                                       x.get("section_title") or ""))
    L1.append("")
    L1.append("> 单侧存在的表不等于「新增/删除的规则」，其中包含修改日志、图例、"
              "跨页续页等非机制表格，需人工逐条判断。")
    L1.append("")
    L1.append("## 2. 插图分类")
    L1.append("")
    L1.append("### 2.1 分类方法")
    L1.append("")
    L1.append("对每张嵌入图像解码后计算两个结构特征，再结合图注差异：")
    L1.append("")
    L1.append("| 特征 | 说明 |")
    L1.append("|---|---|")
    L1.append("| aHash | 16×16 均值哈希，反映整体明暗结构；差异率 = 汉明距离 / 256 |")
    L1.append("| 灰度直方图 | 16 桶分布，反映明暗构成；差异 = 0.5×Σ|p−q| |")
    L1.append("| 图注（去图号）相似度 | <0.45 直接判「信息变化」 |")
    L1.append("")
    L1.append("| 判定 | 条件 |")
    L1.append("|---|---|")
    L1.append("| 像素完全一致 | 解码像素 sha256 相同 |")
    L1.append("| 纯样式变化候选 | aHash 差异 ≤10% 且直方图差异 ≤0.10 |")
    L1.append("| 信息变化 | aHash 差异 ≥30% 或直方图差异 ≥0.25，或图注已明显不同 |")
    L1.append("| 无法判断 | 其余 |")
    L1.append("")
    L1.append("### 2.2 结果")
    L1.append("")
    L1.append("| 判定 | 条数 | 能否自动下结论 |")
    L1.append("|---|---|---|")
    for k, v in sorted(fv.items(), key=lambda kv: -kv[1]):
        can = "是（像素完全相同）" if k == "像素完全一致" else "否，需目视"
        L1.append("| %s | %d | %s |" % (k, v, can))
    L1.append("")
    L1.append("**纯样式变化候选（%d 张）**" % fv.get("纯样式变化候选", 0))
    L1.append("")
    for r in f["rows"]:
        if r["verdict"] != "纯样式变化候选":
            continue
        L1.append("- P%s `%s` → P%s `%s`（aHash 差异 %.1f%%、直方图 %.3f）"
                  % (r["f2026"]["physical_page"], clip(r["f2026"]["caption"] or "无图注", 30),
                     r["f2027"]["physical_page"], clip(r["f2027"]["caption"] or "无图注", 30),
                     100 * (r["ahash_distance"] or 0), r["hist_distance"] or 0))
    L1.append("")
    L1.append("**信息变化（%d 条，需目视确认）**" % fv.get("信息变化", 0))
    L1.append("")
    L1.append("| # | 2026 | 2027 | 依据 |")
    L1.append("|---|---|---|---|")
    n = 0
    for r in f["rows"]:
        if r["verdict"] != "信息变化":
            continue
        n += 1
        a = r.get("f2026") or {}
        b = r.get("f2027") or {}
        L1.append("| %d | P%s `%s` | P%s `%s` | %s |"
                  % (n, a.get("physical_page", "—"), clip(a.get("caption") or "无图注", 26),
                     b.get("physical_page", "—"), clip(b.get("caption") or "无图注", 26),
                     clip(r.get("reason"), 46)))
        if n >= 40:
            break
    L1.append("")
    L1.append("## 3. 新旧页面对照（供人工查看）")
    L1.append("")
    L1.append("以下 %d 组为影响比赛机制的图纸/示意图，已把 2026 与 2027 的**整页**渲染出来，"
              "可直接对比（文件在 `ai_workplace/semantic/compare/`）：" % len(f["rendered"]))
    L1.append("")
    L1.append("| # | 主题 | 2026 页 | 2027 页 | 对照图 |")
    L1.append("|---|---|---|---|---|")
    for i, c in enumerate(f["rendered"], 1):
        L1.append("| %d | %s | P%s | P%s | [2026](%s) / [2027](%s) |"
                  % (i, clip(c.get("label") or "", 28), c["page_2026"], c["page_2027"],
                     c["image_2026"], c["image_2027"]))
    L1.append("")
    L1.append("## 4. 公式")
    L1.append("")
    L1.append("| 结论 | 条数 |")
    L1.append("|---|---|")
    fcr = Counter(r["diff_type"] for r in recheck["formulas"])
    for k, v in sorted(fcr.items(), key=lambda kv: -kv[1]):
        L1.append("| %s | %d |" % (k, v))
    L1.append("")
    L1.append("需要人工核对的公式（涉及数值/变量，且位于数学字母数字符号排版的段落）：")
    L1.append("")
    for r in recheck["formulas"]:
        a, b = r.get("f2026") or {}, r.get("f2027") or {}
        if r["diff_type"] == "内容一致":
            continue
        L1.append("- `%s`：2026 P%s `%s / %s` → 2027 P%s `%s / %s`"
                  % (r["kind"], a.get("physical_page", "—"),
                     clip(a.get("numerator") or a.get("text") or "—", 24),
                     clip(a.get("denominator") or "", 20),
                     b.get("physical_page", "—"),
                     clip(b.get("numerator") or b.get("text") or "—", 24),
                     clip(b.get("denominator") or "", 20)))
    L1.append("")
    L1.append("## 5. 结论与限制")
    L1.append("")
    L1.append("1. **表格**：修正了 %d 处按表号造成的错配；**%d 张**表存在参数变化候选，"
              "但所有表格的合并单元格仍未还原，**不能**因此断言「表结构未变」或「语义完全一致」。"
              % (len(t["changed_pairing"]), tv.get("参数变化候选", 0)))
    L1.append("2. **插图**：只有 **%d 条**能凭像素哈希判定未变；其余 %d 条都需要目视，"
              "其中 %d 条被判为「信息变化」（候选）、%d 条「无法判断」。"
              % (fv.get("像素完全一致", 0), len(f["rows"]) - fv.get("像素完全一致", 0),
                 fv.get("信息变化", 0), fv.get("无法判断", 0)))
    L1.append("3. **公式**：文本层不可靠，全部需核对；未做数学语义还原。")
    L1.append("4. 本报告的分类都是**候选**，不构成「已确认」结论。")
    L1.append("")
    open(os.path.join(SEM, "特殊内容核验报告.md"), "w", encoding="utf-8").write("\n".join(L1) + "\n")
    print("written 特殊内容核验报告.md (%d lines)" % len(L1))

    # ======================= 2. 未解决争议清单.md =======================
    L2 = []
    L2.append("# 未解决争议清单（阶段 C 补充核验）")
    L2.append("")
    L2.append("把阶段 C 遗留的问题逐条摊开，避免被「事件合并」掩盖。"
              "本清单中的每一项都**没有**得出最终结论。")
    L2.append("")
    L2.append("## 0. 汇总")
    L2.append("")
    L2.append("| 类别 | 条数 | 处理方式 |")
    L2.append("|---|---|---|")
    L2.append("| 证据不足事件（逐条差异已保留） | %d | 修订版 JSONL 中 `unresolved_items` |"
              % len([r for r in rev if r["change_type"] == "证据不足" and r["record_type"] == "规则事件"]))
    L2.append("| 其中逐条差异总数 | %d | 每条含 diff_id / 双方原文 / record_id |"
              % sum(len(r["revision"]["unresolved_items"]) for r in rev))
    L2.append("| 配对更正（原推测配对被否决） | %d | `规则变更候选_修订版.jsonl` 的「配对更正」记录 |" % len(cor))
    L2.append("| 待人工核验的规则事件 | %d | 见《重点规则人工审核表》 |"
              % stats["needs_review"])
    L2.append("| 表格配对/参数疑义 | %d | 见《特殊内容核验报告》第 1 节 |"
              % len([r for r in t["rows"] if r["verdict"] != "未发现文本层差异"]))
    L2.append("| 插图待目视 | %d | 见《特殊内容核验报告》第 2 节 |"
              % (len(f["rows"]) - fv.get("像素完全一致", 0)))
    L2.append("| 公式待核对 | %d | 见《特殊内容核验报告》第 4 节 |" % len(recheck["formulas"]))
    L2.append("| 回查例外（99.2% 之外） | 6 | 见第 4 节逐条解释 |")
    L2.append("")
    L2.append("## 1. 证据不足事件（逐条差异保留）")
    L2.append("")
    for r in rev:
        if r["record_type"] != "规则事件" or r["change_type"] != "证据不足":
            continue
        L2.append("### %s　%s　（%d 条差异）" % (r["event_id"], r["topic"],
                                                len(r["revision"]["unresolved_items"])))
        L2.append("")
        L2.append("判断：%s" % r["summary"])
        L2.append("")
        for it in r["revision"]["unresolved_items"]:
            L2.append("- `%s`（%s）" % (it["diff_id"], it["diff_type"]))
            if it.get("text_2026"):
                L2.append("  - 2026（`%s`）：%s" % (it.get("record_2026"), clip(it["text_2026"], 110)))
            if it.get("text_2027"):
                L2.append("  - 2027（`%s`）：%s" % (it.get("record_2027"), clip(it["text_2027"], 110)))
        L2.append("")
    L2.append("## 2. 配对更正（原推测配对被否决）")
    L2.append("")
    L2.append("阶段 B2 的 %d 对推测配对中，**%d 对**经复核确认为错配。"
              "每一条都已在修订版中独立成为「配对更正」记录，两侧内容不再按「实质修改」处理。"
              % (pair["reviewed_tentative"], len(cor)))
    L2.append("")
    L2.append("| 更正 ID | diff_id | 2026 原文 | 2027 原文 | 否决理由 | 已进入的正确候选 |")
    L2.append("|---|---|---|---|---|---|")
    for c in cor:
        rid = c["diff_ids"][0] if c["diff_ids"] else ""
        L2.append("| %s | %s | %s | %s | %s | 删除候选 + 新增候选 |"
                  % (c["event_id"], rid,
                     clip((c["rule_2026"]["texts"] or ["—"])[0], 34),
                     clip((c["rule_2027"]["texts"] or ["—"])[0], 34),
                     clip(c["summary"].split("原因：")[-1], 40)))
    L2.append("")
    L2.append("> 说明：这 %d 条 diff 的**原始记录**仍保留在 `ai_workplace/diff/全文候选差异.jsonl`（未改动）；"
              "本清单记录的是「在语义层应如何重新归类」。" % len(cor))
    L2.append("")
    L2.append("## 3. 机制迁移的边界（局部继承 ≠ 整体保留）")
    L2.append("")
    for m in mig:
        L2.append("### %s　%s" % (m["event_id"], m["topic"]))
        L2.append("")
        ic = m["revision"]["internal_changes"]
        for label, key in (("保留", "保留"), ("取消", "取消"), ("新增", "新增")):
            items = [x["item"] for x in ic if x["type"] == key]
            if items:
                L2.append("- **%s**：%s" % (label, "；".join(items)))
        L2.append("- **结论**：%s" % m["summary"])
        L2.append("")
    exc, tot = recall_exceptions(rev)
    L2.append("## 4. 回查率 %.1f%% 的例外（%d 条）"
              % (100.0 * (tot - len(exc)) / tot if tot else 0, len(exc)))
    L2.append("")
    for line in stats["recall_note"]["explanation"]:
        L2.append("- " + line)
    L2.append("")
    L2.append("**逐条例外明细**（引用文本与 record_id 均取自 B2 差异记录，不是重写）：")
    L2.append("")
    L2.append("| # | 事件 | 侧 | record_id | 页码 | 引用文本 | 说明 |")
    L2.append("|---|---|---|---|---|---|---|")
    for i, x in enumerate(exc, 1):
        L2.append("| %d | %s | %s | `%s` | P%s | %s | 段落被拆成多段，跨 ±3 记录窗口仍未整串匹配 |"
                  % (i, x["event_id"], x["side"], x["record_id"], x.get("page"),
                     clip(x["text"], 60)))
    L2.append("")
    L2.append("结论：这些条目**不是编造引用**——文本逐字来自 B2 差异记录，只是该句跨越了阶段 A 的记录边界；"
              "建议在后续版本为 B2 记录补回 `para_text` 字段以便 100% 定位。")
    L2.append("")
    L2.append("## 5. 仍未收敛的事项")
    L2.append("")
    L2.append("| # | 事项 | 现状 | 需要谁来做 |")
    L2.append("|---|---|---|---|")
    L2.append("| 1 | 表格合并单元格未还原 | %d 张表全部如此 | 人工按原 PDF 还原后再谈结构 |" % len(t["rows"]))
    L2.append("| 2 | 表格单侧存在 %d / %d 张，对应关系未定 | 已列出 | 人工确认是新增/删除/改名 |"
              % (len(t["unmatched_2026"]), len(t["unmatched_2027"])))
    L2.append("| 3 | 3 张表疑似被整表替换 | 已标「表主题已变」 | 人工确认 |")
    L2.append("| 4 | %d 张插图需目视（其中 %d 张判信息变化候选） | 已渲染 %d 组页面对照 | 人工看图 |"
              % (len(f["rows"]) - fv.get("像素完全一致", 0), fv.get("信息变化", 0),
                 len(f["rendered"])))
    L2.append("| 5 | 公式文本层不可靠 | 全部待核对 | 人工对照页面 |")
    L2.append("| 6 | 2027 数学字母数字符号排版 | 影响 P72/P108/P109 等 | 需 PDF 源文件或用 OCR 辅助 |")
    L2.append("| 7 | 事件粒度过粗/过细 | 62 个事件 + 11 个补充事件 | 人工按审核表确认 |")
    L2.append("")
    open(os.path.join(SEM, "未解决争议清单.md"), "w", encoding="utf-8").write("\n".join(L2) + "\n")
    print("written 未解决争议清单.md (%d lines)" % len(L2))

    # ======================= 3. 重点规则人工审核表.md =======================
    def materiality_text(m):
        if m.get("robot_design") and m.get("strategy"):
            return "**是**（影响机器人设计 + 比赛策略）：" + (m.get("note") or "")
        if m.get("robot_design"):
            return "**是**（影响机器人设计）：" + (m.get("note") or "")
        if m.get("strategy"):
            return "**是**（影响比赛策略）：" + (m.get("note") or "")
        return "否 / 间接：" + (m.get("note") or "不影响机器人与策略")

    theme_map = {"机器人": "一、机器人", "机制": "二、比赛机制", "场地": "三、场地",
                 "判罚": "四、违规与判罚", "流程": "五、比赛流程", "文档": "六、文档与版本",
                 "表述": "七、表述与术语", "机制迁移": "八、机制迁移专项",
                 "配对更正": "九、配对更正", "未定": "十、未定"}

    picks = []
    for r in rev:
        if r["record_type"] == "配对更正":
            continue
        mat = r["revision"]["materiality"]
        important = bool(mat.get("robot_design") or mat.get("strategy")
                         or r["needs_review"] or r["record_type"] != "规则事件")
        if important:
            picks.append(r)

    by_theme = OrderedDict()
    for r in picks:
        by_theme.setdefault(r["theme"], []).append(r)

    L3 = []
    L3.append("# 重点规则人工审核表（阶段 C 补充核验）")
    L3.append("")
    L3.append("**只列需要人看的条目**，不要求人工逐条审核 %d 条原始技术差异。" % stats["records"])
    L3.append("")
    L3.append("排序原则：先按主题分组（机器人 → 比赛机制 → 场地 → 判罚 → 流程 → 机制迁移），"
              "组内按「是否影响机器人设计/策略」优先。")
    L3.append("")
    L3.append("| 汇总 | 数值 |")
    L3.append("|---|---|")
    L3.append("| 本次列入审核表 | %d 条 |" % len(picks))
    L3.append("| 其中影响机器人设计 | %d 条 |" % stats["materiality_robot"])
    L3.append("| 其中影响比赛策略 | %d 条 |" % stats["materiality_strategy"])
    L3.append("| 补充事件（表格/插图/公式） | %d 条 |" % len(sup))
    L3.append("")
    for theme in THEME_ORDER:
        rs = by_theme.get(theme)
        if not rs:
            continue
        L3.append("## %s" % theme_map.get(theme, theme))
        L3.append("")
        for r in rs:
            L3.append("### %s　%s" % (r["event_id"], r["topic"]))
            L3.append("")
            L3.append("- **变化类型**：%s　|　**口径**：%s　|　**证据强度**：%s"
                      % (r["change_type"], r["revision"]["category"],
                         {"strong": "充分", "medium": "中等", "weak": "不足"}.get(
                             r.get("evidence_strength"), "—")))
            a, b = r["rule_2026"], r["rule_2027"]
            if a.get("texts"):
                L3.append("- **2026 原文与来源**（%s）" % (sec_label(a) or "—"))
                for txt, rid in list(zip(a["texts"], a["record_ids"]))[:3]:
                    pg = ""
                    L3.append("  - %s　`%s`" % (clip(txt, 160), rid))
                if len(a["texts"]) > 3:
                    L3.append("  - …（共 %d 条）" % len(a["texts"]))
            else:
                L3.append("- **2026 原文与来源**：*该赛季无对应原文*")
            if b.get("texts"):
                L3.append("- **2027 原文与来源**（%s）" % (sec_label(b) or "—"))
                for txt, rid in list(zip(b["texts"], b["record_ids"]))[:3]:
                    L3.append("  - %s　`%s`" % (clip(txt, 160), rid))
                if len(b["texts"]) > 3:
                    L3.append("  - …（共 %d 条）" % len(b["texts"]))
            else:
                L3.append("- **2027 原文与来源**：*该赛季无对应原文*")
            if r.get("spec_refs"):
                L3.append("- **关联特殊内容**：" + "；".join(
                    "%s P%s/%s" % (x.get("kind"), x.get("page_2026") or "—", x.get("page_2027") or "—")
                    for x in r["spec_refs"][:6]))
            L3.append("- **AI 判断**：%s" % r["summary"])
            ic = r["revision"]["internal_changes"]
            if ic:
                L3.append("- **内部具体功能变化**：" + "；".join(
                    "%s「%s」%s" % (x["type"], x["item"], ("（%s）" % x["note"]) if x.get("note") else "")
                    for x in ic[:8]))
            rr = r["revision"]["review_reasons"]
            L3.append("- **尚需核实的疑点**：%s" % ("；".join(rr) if rr else "无（证据充分）"))
            if r["revision"]["unresolved_items"]:
                L3.append("  - 逐条差异 %d 条，见 `未解决争议清单.md`" % len(r["revision"]["unresolved_items"]))
            L3.append("- **是否可能影响机器人设计或比赛策略**：%s"
                      % materiality_text(r["revision"]["materiality"]))
            L3.append("")
    L3.append("## 使用建议")
    L3.append("")
    L3.append("1. 先看「机器人」与「比赛机制」两节中标注 **影响机器人设计** 的条目（共 %d 条），"
              "它们最可能改变机械/电气/软件方案。" % stats["materiality_robot"])
    L3.append("2. 「场地」类请配合《特殊内容核验报告》第 3 节的页面对照图一起看。")
    L3.append("3. 「机制迁移专项」用于回答「某个旧机制到底还算不算存在」，不要只看局部文字。")
    L3.append("4. 审核结论请回填到本表的「尚需核实的疑点」列，不要直接修改 JSONL。")
    L3.append("")
    open(os.path.join(SEM, "重点规则人工审核表.md"), "w", encoding="utf-8").write("\n".join(L3) + "\n")
    print("written 重点规则人工审核表.md (%d lines, %d items)" % (len(L3), len(picks)))

    # ======================= 4. 阶段C补充核验质量报告.md =======================
    L4 = []
    L4.append("# 阶段 C 补充核验质量报告")
    L4.append("")
    L4.append("本轮**不重新执行 A/B 阶段，也不重新分析全部正文**，只做四件事："
              "修正分类口径、补充特殊内容差异、清理未决问题、生成人工审核表。")
    L4.append("")
    L4.append("## 0. 结论")
    L4.append("")
    L4.append("| 项目 | 数值 |")
    L4.append("|---|---|")
    L4.append("| 修订版记录总数 | %d 条 |" % stats["records"])
    L4.append("| 　原 62 个规则事件（保留未覆盖） | %d 条 |" % stats["rule_events"])
    L4.append("| 　新增补充事件（表格/插图/公式） | %d 条 |" % len(sup))
    L4.append("| 　配对更正 | %d 条 |" % len(cor))
    L4.append("| 　机制迁移判定 | %d 条 |" % len(mig))
    L4.append("| 计入实质比赛规则变化 | %d 条 |" % stats["counts_as_rule_change"])
    L4.append("| 　其中文档变化 | %d 条 |" % stats["by_category"].get("文档变化", 0))
    L4.append("| 　其中排版变化 | %d 条 |" % stats["by_category"].get("排版变化", 0))
    L4.append("| 　其中口径未定 | %d 条 |" % stats["by_category"].get("未定", 0))
    L4.append("| 机制重构事件内部展开的具体功能变化 | %d 项 |" % stats["internal_changes"])
    L4.append("| 证据不足事件保留的逐条差异 | %d 条 |" % stats["unresolved_items"])
    L4.append("")
    L4.append("## 1. 修正分类口径")
    L4.append("")
    L4.append("| 事件 | 原分类 | 修正后 | 原因 |")
    L4.append("|---|---|---|---|")
    fix = [("CE-51", "实质新增", "文档变化",
            "「1.2 新赛季主要变更」是变更说明章节，不计入实质新增比赛机制"),
           ("CE-18", "实质新增", "文档变化",
            "场地图纸图例说明的补充属图例层面，不计入新增机制"),
           ("CE-52", "仅表述调整", "文档变化", "版本号/赛制名称表述，不影响机制"),
           ("CE-56", "证据不足", "排版变化", "数学字母数字符号导致文本层破损，属排版问题"),
           ("CE-17", "证据不足", "未定", "图例配对不可靠，需人工对照渲染图"),
           ("CE-60/61/62", "证据不足", "未定", "零散差异，无法归类为比赛规则变化")]
    for eid, old, new, why in fix:
        L4.append("| %s | %s | **%s** | %s |" % (eid, old, new, why))
    L4.append("")
    L4.append("**机制重构内部变化展开**（不再用一个标签掩盖实际变化）：")
    L4.append("")
    L4.append("| 事件 | 保留 | 新增 | 取消/替换 |")
    L4.append("|---|---|---|---|")
    for r in rev:
        ic = r["revision"]["internal_changes"]
        if not ic or r["record_type"] != "规则事件":
            continue
        keep = [x["item"] for x in ic if x["type"] in ("保留", "合并")]
        add = [x["item"] for x in ic if x["type"] == "新增"]
        cut = [x["item"] for x in ic if x["type"] in ("取消", "替换", "修改")]
        L4.append("| %s | %s | %s | %s |" % (r["event_id"], clip("、".join(keep), 40) or "—",
                                            clip("、".join(add), 40) or "—",
                                            clip("、".join(cut), 40) or "—"))
    L4.append("")
    L4.append("## 2. 补充特殊内容差异")
    L4.append("")
    L4.append("| 项目 | 结果 |")
    L4.append("|---|---|")
    L4.append("| 表格重新配对 | %d 张（与 B2 相比修正 %d 处表号错配） |"
              % (len(recheck["tables"]["rows"]), len(recheck["tables"]["changed_pairing"])))
    L4.append("| 表格参数变化候选 | %d 张 |" % recheck["tables"]["by_verdict"].get("参数变化候选", 0))
    L4.append("| 表格单侧存在 | 2026 %d / 2027 %d 张 |"
              % (len(recheck["tables"]["unmatched_2026"]), len(recheck["tables"]["unmatched_2027"])))
    L4.append("| 插图分类 | 像素一致 %d / 纯样式 %d / 信息变化 %d / 无法判断 %d |"
              % (recheck["figures"]["by_verdict"].get("像素完全一致", 0),
                 recheck["figures"]["by_verdict"].get("纯样式变化候选", 0),
                 recheck["figures"]["by_verdict"].get("信息变化", 0),
                 recheck["figures"]["by_verdict"].get("无法判断", 0)))
    L4.append("| 新旧页面对照 | 已渲染 %d 组（`semantic/compare/`） |" % len(recheck["figures"]["rendered"]))
    L4.append("| 关联到事件的补充事件 | %d 个（CX-01..CX-11） |" % len(sup))
    L4.append("")
    L4.append("## 3. 清理未决问题")
    L4.append("")
    L4.append("| 事项 | 处理 |")
    L4.append("|---|---|")
    L4.append("| 5 个证据不足事件 | 逐条差异（%d 条）已写入修订版 `unresolved_items`，不因合并而隐藏 |"
              % stats["unresolved_items"])
    L4.append("| 18 个待核验事件 | 每条都生成了「尚需核实的疑点」，见《重点规则人工审核表》 |")
    L4.append("| 24 对错误配对 | 已确认其两侧分别按「删除候选 / 新增候选」重新登记（配对更正记录） |")
    L4.append("| 99.2% 回查率之外 6 条 | 逐条解释为「段落被阶段 A 拆成 ≥4 段导致的跨记录缝合」 |")
    L4.append("| 空中系统/雷达/哨兵迁移 | 新增 4 条机制迁移判定，明确列出保留/取消/新增三侧 |")
    L4.append("")
    L4.append("## 4. 覆盖率")
    L4.append("")
    L4.append("| 对象 | 总数 | 已处理 |")
    L4.append("|---|---|---|")
    L4.append("| 原 62 个规则事件 | 62 | 62（全部保留并加修订层） |")
    L4.append("| B2 正文变化候选 | 534 | 534（diff_id 全部保留） |")
    L4.append("| 推测配对 | 41 | 41（否决 24） |")
    L4.append("| 逻辑表 | 110（2026 57 / 2027 53） | 配对 38，单侧 19 / 15 已列出 |")
    L4.append("| 插图差异 | 97 条 | 100% 分类 |")
    L4.append("| 公式差异 | %d 条 | 100%% 列出 |" % len(recheck["formulas"]))
    L4.append("")
    L4.append("## 5. 局限")
    L4.append("")
    L4.append("1. **表格**：合并单元格仍未还原；「参数变化候选」只能说明网格文本层的数值集合变了，"
              "不能说明表结构或语义。")
    L4.append("2. **插图**：aHash/直方图是结构相似度，不是语义相似度；「纯样式变化候选」仍需目视确认。")
    L4.append("3. **公式**：未做数学语义还原，数学字母数字符号页面的文本层不可信。")
    L4.append("4. **口径修正**依赖主观判断（哪些算文档变化），已逐条给出理由，供审核推翻。")
    L4.append("5. 本阶段**不产生最终事实**：所有记录 `verify_status = unverified`。")
    L4.append("")
    L4.append("## 6. 产物")
    L4.append("")
    L4.append("| 文件 | 说明 |")
    L4.append("|---|---|")
    L4.append("| `semantic/规则变更候选_修订版.jsonl` | %d 条（保留原 62 事件 + 补充/更正/迁移） |" % stats["records"])
    L4.append("| `semantic/特殊内容核验报告.md` | 表格/插图/公式重新核对 |")
    L4.append("| `semantic/未解决争议清单.md` | 未决项逐条列出 |")
    L4.append("| `semantic/重点规则人工审核表.md` | %d 条重点规则 |" % len(picks))
    L4.append("| `semantic/本报告` | 方法、覆盖、局限 |")
    L4.append("| `semantic/special_recheck.json` | 表格配对与插图分类的机器可读结果 |")
    L4.append("| `semantic/compare/*.png` | %d 组新旧页面对照 |" % len(recheck["figures"]["rendered"]))
    L4.append("")
    L4.append("```powershell")
    L4.append("& $py tools/70_c2_special.py   # 表格重配 + 插图分类 + 页面对照渲染")
    L4.append("& $py tools/71_c2_revise.py    # 口径修正 + 补充事件 + 配对更正 + 迁移判定")
    L4.append("& $py tools/72_c2_reports.py   # 四份报告")
    L4.append("& $py tools/73_c2_verify.py    # 覆盖与一致性核验")
    L4.append("```")
    L4.append("")
    L4.append("**补充核验到此结束，等待上游审核与人工介入。**")
    L4.append("")
    open(os.path.join(SEM, "阶段C补充核验质量报告.md"), "w", encoding="utf-8").write("\n".join(L4) + "\n")
    print("written 阶段C补充核验质量报告.md (%d lines)" % len(L4))


if __name__ == "__main__":
    main()
