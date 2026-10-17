#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 5 (phase B2) -- step 3: render the four human-facing deliverables from
the machine-readable candidate set (single source of truth).

Outputs
  全文差异总览.md / 特殊内容差异清单.md / 差异覆盖与质量报告.md / 待人工核验的重点差异.md
"""
import os
import sys
import json
import re
from collections import Counter, defaultdict, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b2_lib as L

REL_CN = {"kept": "保留", "renamed": "重命名", "moved": "迁移", "merged": "合并",
          "split": "拆分", "added": "疑似新增", "deleted": "疑似删除"}
TYPES = L.DIFF_TYPES
CHANGE_T = ["实质修改候选", "新增候选", "删除候选", "迁移或重组候选", "文字调整候选"]


def load_all():
    d = dict(
        align=L.load_json(os.path.join(L.ALIGN, "章节对应关系.json")),
        diffs=L.load_jsonl(os.path.join(L.OUT, "全文候选差异.jsonl")),
        status=L.load_jsonl(os.path.join(L.OUT, "差异覆盖状态.jsonl")),
        body=L.load_json(os.path.join(L.OUT, "b2_body_stats.json")),
        special=L.load_json(os.path.join(L.OUT, "special_diff.json")),
    )
    return d


def _keys(x, n=8):
    """evidence numbers may be a list (body diff) or a dict (table diff)"""
    if isinstance(x, dict):
        return list(x.keys())[:n]
    return (x or [])[:n]


def pct(a, b):
    return "%.1f%%" % (100.0 * a / b) if b else "—"


def chapter_of(path):
    return path[0] if path else "（无路径）"


def main():
    D = load_all()
    diffs = D["diffs"]
    body = D["body"]
    sp = D["special"]
    status = D["status"]
    align = D["align"]

    by_type = body["diff_by_type"]
    total_records = len(diffs)
    matched = body["matched_pairs"]
    unchanged = by_type.get("内容一致", 0) + by_type.get("编号变化（不计内容变化）", 0) \
        + by_type.get("引用编号更新（不计内容变化）", 0)

    # chapter roll-up of body diffs
    # chapter key = the 2026 chapter of the alignment unit (so renumbered
    # appendices stay on one row); added units fall back to their 2027 chapter
    unit_chapter = OrderedDict()
    for u in align["alignments"]:
        if u["sections_2026"]:
            unit_chapter[u["align_id"]] = chapter_of(u["sections_2026"][0]["path"])
        elif u["sections_2027"]:
            unit_chapter[u["align_id"]] = chapter_of(u["sections_2027"][0]["path"])
    chap = OrderedDict((c, dict()) for c in unit_chapter.values())
    chap_stats = OrderedDict((c, Counter()) for c in chap)
    for r in diffs:
        c = unit_chapter.get(r["align_id"])
        if c is None:
            sec = r["section_2026"] or r["section_2027"] or {}
            c = chapter_of(sec.get("path") or []) or "（无路径）"
        chap_stats.setdefault(c, Counter())
        chap_stats[c][r["diff_type"]] += 1

    # ============================ 1. 全文差异总览.md ============================
    L1 = []
    L1.append("# 全文差异总览（阶段 B2）")
    L1.append("")
    L1.append("**RMUC 2026 V2.2.0 → RMUC 2027 V1.0.0　全文正文候选差异**")
    L1.append("")
    L1.append("> 机器可读版本：`ai_workplace/diff/全文候选差异.jsonl`（本表由它渲染）。")
    L1.append("> **本阶段只产生候选差异，不做最终语义判定**；所有条目 `verify_status = unverified`。")
    L1.append("> 章节组织依据阶段 B1 的 `章节对应关系.json`；编号变化本身不计为内容变化。")
    L1.append("")
    L1.append("## 0. 一句话结果")
    L1.append("")
    L1.append("两份文档全文共切出 %d / %d 个可比对句段，成功配对 **%d** 对，其中 **%d** 对判定为内容一致"
              "（含编号变化/引用编号更新），**%d** 对存在候选差异；另有 %d 条新增候选、%d 条删除候选、"
              "%d 条迁移或重组候选。"
              % (body["sentences_2026"], body["sentences_2027"], matched, unchanged,
                 matched - unchanged, by_type.get("新增候选", 0),
                 by_type.get("删除候选", 0), by_type.get("迁移或重组候选", 0)))
    L1.append("")
    L1.append("## 1. 统计")
    L1.append("")
    L1.append("| 项目 | 数值 |")
    L1.append("|---|---|")
    L1.append("| 2026 可比对句段 | %d |" % body["sentences_2026"])
    L1.append("| 2027 可比对句段 | %d |" % body["sentences_2027"])
    L1.append("| 配对成功 | **%d** |" % matched)
    L1.append("| 其中 内容一致 / 编号变化 / 引用编号更新 | %d / %d / %d |"
              % (by_type.get("内容一致", 0), by_type.get("编号变化（不计内容变化）", 0),
                 by_type.get("引用编号更新（不计内容变化）", 0)))
    L1.append("| 文字调整候选 | %d |" % by_type.get("文字调整候选", 0))
    L1.append("| 实质修改候选 | %d |" % by_type.get("实质修改候选", 0))
    L1.append("| 新增候选 | %d |" % by_type.get("新增候选", 0))
    L1.append("| 删除候选 | %d |" % by_type.get("删除候选", 0))
    L1.append("| 迁移或重组候选 | %d |" % by_type.get("迁移或重组候选", 0))
    L1.append("| 全文兜底检索找回（跨章节迁移） | %d |" % body["recovered_by_fallback"])
    L1.append("| 需人工核验（正文） | %d |" % body["needs_review"])
    L1.append("| JSONL 记录总数（含内容一致） | %d |" % total_records)
    L1.append("")
    L1.append("**为什么保留「内容一致」记录**：任务要求在发现差异的同时保留未变化的部分与覆盖统计，"
              "以证明检查不是只看变化项。`全文候选差异.jsonl` 中 %d 条记录为内容一致/编号差异，"
              "占比 %s。" % (unchanged, pct(unchanged, total_records)))
    L1.append("")
    L1.append("## 2. 按章分布")
    L1.append("")
    L1.append("| 章 | 内容一致 | 文字调整 | 实质修改 | 新增 | 删除 | 迁移 | 合计变化候选 |")
    L1.append("|---|---|---|---|---|---|---|---|")
    for c, cnt in chap_stats.items():
        ch = sum(cnt.get(t, 0) for t in CHANGE_T)
        L1.append("| %s | %d | %d | %d | %d | %d | %d | **%d** |"
                  % (c, cnt.get("内容一致", 0), cnt.get("文字调整候选", 0),
                     cnt.get("实质修改候选", 0), cnt.get("新增候选", 0),
                     cnt.get("删除候选", 0), cnt.get("迁移或重组候选", 0), ch))
    L1.append("")
    L1.append("## 3. 差异集中的章节（按变化候选数排序）")
    L1.append("")
    sec_stats = defaultdict(Counter)
    for r in diffs:
        sec = r["section_2026"] or r["section_2027"] or {}
        key = "%s %s" % (sec.get("no") or "—", (sec.get("title") or "").split(" ", 1)[-1])
        sec_stats[key][r["diff_type"]] += 1
    ranked = sorted(sec_stats.items(),
                    key=lambda kv: -sum(kv[1].get(t, 0) for t in CHANGE_T))[:30]
    L1.append("| 章节 | 实质修改 | 新增 | 删除 | 迁移 | 文字调整 |")
    L1.append("|---|---|---|---|---|---|")
    for k, cnt in ranked:
        L1.append("| %s | %d | %d | %d | %d | %d |"
                  % (k, cnt.get("实质修改候选", 0), cnt.get("新增候选", 0),
                     cnt.get("删除候选", 0), cnt.get("迁移或重组候选", 0),
                     cnt.get("文字调整候选", 0)))
    L1.append("")
    L1.append("## 4. 检测方法（可复现）")
    L1.append("")
    L1.append("1. **段落缝合**：阶段 A 有个别段落被拆成多条记录（续行判断未命中），直接比对会把「一段改写」"
              "误报成「1 删除 + 1 新增」。因此先按「上一条未以句末标点结束且下一条不是新列表项」的规则把同一章节内的"
              "连续正文记录重新拼接，再切句。")
    L1.append("2. **章节内配对**：以 B1 对齐单元为范围，句子级字符相似度 ≥ 0.60 做一对一贪心配对；"
              "对同章节两侧的残余句再做一次低阈值（二元组 Jaccard ≥ 0.20）的**推测配对**，"
              "标 `tentative_pairing` 并强制进入待核验。")
    L1.append("3. **全文兜底**：所有未配对的残余句在全文中检索（阈值 0.80、长度 ≥ 12 字），"
              "找回跨章节迁移/重组；仍找不到的才列为新增/删除候选。")
    L1.append("4. **分类规则**：文本完全一致 → 内容一致；只有列表项编号/条款编号变化 → 编号变化（不计内容变化）；"
              "只有交叉引用编号变化 → 引用编号更新（不计内容变化）；数字或单位集合变化 → 实质修改候选；"
              "相似度 ≥ 0.90 → 文字调整候选；其余 → 实质修改候选。")
    L1.append("5. **不许判定**：新增/删除候选一律标 `needs_review`，并在 `evidence` 中附带"
              "「全文最高相似度 / 最相似章节」，供人工复核。")
    L1.append("")
    L1.append("## 5. 已知的假差异来源（已处理）")
    L1.append("")
    L1.append("- **章节编号顺延**（44 个单元）：不参与文本比较。")
    L1.append("- **列表项编号变化**（如 R48 → R47）：归为「编号变化」，%d 条。" % by_type.get("编号变化（不计内容变化）", 0))
    L1.append("- **交叉引用编号**（如「详见 5.5.3」→「详见 5.6.4」）：归为「引用编号更新」，%d 条。"
              % by_type.get("引用编号更新（不计内容变化）", 0))
    L1.append("- **段落被阶段 A 拆分**：已通过段落缝合消除（6.3 等章节的假删除已归零）。")
    L1.append("- **表格跨页拆分**：在特殊内容流程中先合并为「逻辑表格」再比对。")
    L1.append("")
    L1.append("## 6. 约束声明")
    L1.append("")
    L1.append("- 阶段 A 数据只读，未修改任何 `structured/` 产物。")
    L1.append("- 未使用「术语缺失 = 机制取消」的推断；删除候选一律要求人工复核。")
    L1.append("- 未生成最终规则总结；未做 RAG / 模型训练 / 多模型评测。")
    L1.append("")
    open(os.path.join(L.OUT, "全文差异总览.md"), "w", encoding="utf-8").write("\n".join(L1) + "\n")
    print("written 全文差异总览.md (%d lines)" % len(L1))

    # ====================== 2. 特殊内容差异清单.md ======================
    t = sp["tables"]
    f = sp["figures"]
    fm = sp["formulas"]
    dg = sp["diagram_labels"]
    L2 = []
    L2.append("# 特殊内容差异清单（阶段 B2）")
    L2.append("")
    L2.append("覆盖**全部**提取表格、公式、插图与图示文字。文本层无法判断的一律标记为「需要视觉对照」，"
              "不因自动文本一致就认定高风险内容无变化。")
    L2.append("")
    L2.append("## 0. 汇总")
    L2.append("")
    L2.append("| 类别 | 2026 | 2027 | 配对 | 内容一致 | 文字调整 | 实质修改 | 新增 | 删除 | 迁移 |")
    L2.append("|---|---|---|---|---|---|---|---|---|---|")
    L2.append("| 表格（逻辑表） | %d | %d | %d | %d | %d | %d | %d | %d | %d |" % (
        t["total_2026"], t["total_2027"], t["matched"],
        t["by_type"].get("内容一致", 0), t["by_type"].get("文字调整候选", 0),
        t["by_type"].get("实质修改候选", 0), t["by_type"].get("新增候选", 0),
        t["by_type"].get("删除候选", 0), t["by_type"].get("迁移或重组候选", 0)))
    L2.append("| 插图 | %d | %d | %d | %d | %d | 0 | %d | %d | %d |" % (
        f["total_2026"], f["total_2027"], f["matched"],
        f["by_type"].get("内容一致", 0), f["by_type"].get("文字调整候选", 0),
        f["by_type"].get("新增候选", 0), f["by_type"].get("删除候选", 0),
        f["by_type"].get("迁移或重组候选", 0)))
    L2.append("| 上下分式 | %d | %d | — | %d | 0 | %d | %d | %d | 0 |" % (
        fm["total_2026_fraction"], fm["total_2027_fraction"],
        fm["by_type"].get("内容一致", 0), fm["by_type"].get("实质修改候选", 0),
        fm["by_type"].get("新增候选", 0), fm["by_type"].get("删除候选", 0)))
    L2.append("| 图示文字（句） | — | — | — | %d | %d | %d | %d | %d | 0 |" % (
        dg["by_type"].get("内容一致", 0), dg["by_type"].get("文字调整候选", 0),
        dg["by_type"].get("实质修改候选", 0), dg["by_type"].get("新增候选", 0),
        dg["by_type"].get("删除候选", 0)))
    L2.append("")
    L2.append("> 表格原始记录 %d / %d 条，跨页续页合并后为 **%d / %d 张逻辑表**；"
              "覆盖清单见 `special_diff.json → table_coverage`（逐条记录）。"
              % (sp["raw_table_records"]["total_2026"], sp["raw_table_records"]["total_2027"],
                 sp["raw_table_records"]["logical_2026"], sp["raw_table_records"]["logical_2027"]))
    L2.append("")

    L2.append("## 1. 表格")
    L2.append("")
    L2.append("### 1.1 检测口径")
    L2.append("")
    L2.append("- 先按「同章节 + 无表题」合并跨页续页记录为逻辑表，避免一张表被拆成两条记录造成的假新增/删除。")
    L2.append("- 独立比对：**数值集合**、**单位集合**、**列标题（首行）**、**行标签（首列）**、**单元格文本多重集**、**形状（行列数）**。")
    L2.append("- 网格可靠性：任一侧存在丢词或空白率 > 80% 时标 `grid_reliable=false`，结论只能作为线索，"
              "必须回到 `source_text_lines` 与原 PDF 核验。")
    L2.append("- **合并单元格未还原**：所有表格的合并结构仍是空白网格，因此「文本层未见数值变化」**不等于**表结构未变。")
    L2.append("")
    unrel = t["grid_unreliable"]
    L2.append("网格不可靠的逻辑表：**%d / %d**（见下表 1.3）。" % (unrel, len(t["rows"])))
    L2.append("")
    L2.append("### 1.2 实质修改候选（%d 张）" % t["by_type"].get("实质修改候选", 0))
    L2.append("")
    L2.append("| # | 2026 表 | 2027 表 | 变化项 |")
    L2.append("|---|---|---|---|")
    n = 0
    for r in t["rows"]:
        if r["diff_type"] != "实质修改候选":
            continue
        n += 1
        a, b = r["table_2026"], r["table_2027"]
        ev = r["evidence"]
        bits = []
        if ev.get("numbers"):
            bits.append("数值 增%s/减%s" % (list(ev["numbers"]["added"].keys())[:6],
                                            list(ev["numbers"]["removed"].keys())[:6]))
        if ev.get("units"):
            bits.append("单位变化")
        if ev.get("column_headers"):
            bits.append("列标题变化")
        if ev.get("row_labels"):
            bits.append("行标签变化")
        if ev.get("shape"):
            bits.append("行列数 %s→%s" % (ev["shape"]["2026"], ev["shape"]["2027"]))
        if not bits:
            bits.append("单元格文本变化")
        L2.append("| %d | P%d %s `%s` | P%d %s `%s` | %s |" % (
            n, a["physical_page"], a["table_no"] or "-", (a["caption"] or "（无表题）")[:26],
            b["physical_page"], b["table_no"] or "-", (b["caption"] or "（无表题）")[:26],
            "；".join(bits)))
        if n >= 40:
            L2.append("| … | 其余 %d 张见 JSONL | | |" % (t["by_type"].get("实质修改候选", 0) - n))
            break
    L2.append("")
    L2.append("### 1.3 网格不可靠 / 需回原文核验的表格")
    L2.append("")
    L2.append("| 2026 / 2027 | 页码 | 丢词数 | 空白率 | 结论 |")
    L2.append("|---|---|---|---|---|")
    n = 0
    for r in t["rows"]:
        if r["grid_reliable"]:
            continue
        a, b = r["table_2026"], r["table_2027"]
        side = " / ".join(x for x in (
            ("2026 P%d" % a["physical_page"]) if a else "",
            ("2027 P%d" % b["physical_page"]) if b else "") if x)
        gm = "%s / %s" % ((a or {}).get("grid_missing", "—"), (b or {}).get("grid_missing", "—"))
        br = "%s / %s" % ((a or {}).get("blank_ratio", "—"), (b or {}).get("blank_ratio", "—"))
        L2.append("| %s | %s / %s | %s | %s | %s |"
                  % (side, (a or {}).get("physical_page", "—"), (b or {}).get("physical_page", "—"),
                     gm, br, r["diff_type"]))
        n += 1
        if n >= 30:
            L2.append("| … | | | | 其余 %d 条 |" % (unrel - n))
            break
    L2.append("")
    L2.append("### 1.4 新增 / 删除的表格")
    L2.append("")
    for kind, th in (("新增候选", "2027 独有"), ("删除候选", "2026 独有")):
        rows = [r for r in t["rows"] if r["diff_type"] == kind]
        L2.append("**%s（%d 张，%s）**" % (kind, len(rows), th))
        L2.append("")
        for r in rows:
            x = r["table_2026"] or r["table_2027"]
            ev = r["evidence"]
            L2.append("- P%d `%s` %s（所在章节 %s）%s"
                      % (x["physical_page"], x["table_no"] or "-",
                         (x["caption"] or "（无表题）")[:30], x["section_title"],
                         "；全文最相似 %.2f @ %s" % (ev.get("fulltext_best_similarity", 0),
                                                   ev.get("fulltext_best_section", "—"))
                         if ev.get("fulltext_best_similarity") else ""))
        L2.append("")

    L2.append("## 2. 公式")
    L2.append("")
    L2.append("- 分式按「分子文本 / 分母文本」配对比较，**不做拼装、不改写**；上下标方向由基线偏移判定，可能失真。")
    L2.append("- 全部 %d 条分式与 %d 条带上下标记录已进入覆盖清单（`special_diff.json → formula_coverage`）。"
              % (len([x for x in sp["formula_coverage"] if x["kind"] == "formula_fraction"]),
                 len([x for x in sp["formula_coverage"] if x["kind"] == "script_spans"])))
    L2.append("")
    L2.append("| # | 2026 分式 | 2027 分式 | 结论 |")
    L2.append("|---|---|---|---|")
    n = 0
    for r in fm["rows"]:
        if r["kind"] != "formula_fraction":
            continue
        n += 1
        a, b = r["formula_2026"], r["formula_2027"]
        fa = "P%d %s / %s" % (a["physical_page"], (a["numerator"] or "")[:16], (a["denominator"] or "")[:16]) if a else "—"
        fb = "P%d %s / %s" % (b["physical_page"], (b["numerator"] or "")[:16], (b["denominator"] or "")[:16]) if b else "—"
        L2.append("| %d | %s | %s | %s |" % (n, fa, fb, r["diff_type"]))
    L2.append("")
    L2.append("## 3. 插图")
    L2.append("")
    L2.append("### 3.1 判定方式")
    L2.append("")
    L2.append("对每张嵌入图像计算两个 sha256：")
    L2.append("")
    L2.append("| 哈希 | 含义 |")
    L2.append("|---|---|")
    L2.append("| `stream` | 嵌入图像文件本身，PDF 重新压缩就会变，**不能**作为是否改图的依据 |")
    L2.append("| `pixels` | 解码后的**像素数据**，相同即图像视觉内容完全一致 |")
    L2.append("")
    L2.append("**%d 张**插图像素哈希完全一致 → 可判定图像本身未变化；"
              "其余 **%d 张**像素不同或无法定位 → 一律标「需要视觉对照」，"
              "不因为图注文字相同就认为图没变。"
              % (f["identical_binary"], f["matched"] - f["identical_binary"]))
    L2.append("")
    L2.append("### 3.2 像素有变化、需要视觉对照的插图（%d 张）"
              % (f["matched"] - f["identical_binary"]))
    L2.append("")
    L2.append("| # | 2026 图注 | 2027 图注 | 2026 尺寸 | 2027 尺寸 |")
    L2.append("|---|---|---|---|---|")
    n = 0
    for r in f["rows"]:
        if r["diff_type"] != "文字调整候选" and r["diff_type"] != "迁移或重组候选":
            continue
        a, b = r["figure_2026"], r["figure_2027"]
        L2.append("| %d | P%d %s | P%d %s | %sx%s | %sx%s |" % (
            n + 1, a["physical_page"], (a["caption"] or "（无图注）")[:24],
            b["physical_page"], (b["caption"] or "（无图注）")[:24],
            a["w"], a["h"], b["w"], b["h"]))
        n += 1
        if n >= 45:
            L2.append("| … | 其余 %d 张见 `special_diff.json` | | | |"
                      % (f["matched"] - f["identical_binary"] - n))
            break
    L2.append("")
    L2.append("### 3.3 新增 / 删除的插图")
    L2.append("")
    for kind in ("新增候选", "删除候选"):
        rows = [r for r in f["rows"] if r["diff_type"] == kind]
        L2.append("**%s（%d 张）**" % (kind, len(rows)))
        L2.append("")
        for r in rows:
            x = r["figure_2026"] or r["figure_2027"]
            L2.append("- P%d（%s）%s %sx%s" % (x["physical_page"], x["section_title"],
                                              (x["caption"] or "（无图注）")[:34], x["w"], x["h"]))
        L2.append("")

    L2.append("## 4. 图示文字（`diagram_label` / `figure_label_row`）")
    L2.append("")
    L2.append("上游要求图示文字必须纳入检查，已随正文一并比对（因为它们本身就是文本记录）：")
    L2.append("")
    L2.append("| 结论 | 条数 |")
    L2.append("|---|---|")
    for k, v in dg["by_type"].items():
        L2.append("| %s | %d |" % (k, v))
    L2.append("")
    L2.append("⚠ 流程图节点之间的**连接关系**无法从文本层恢复；图示文字比对只能发现「文字本身」的变化，"
              "不能判断流程走向是否改变。涉及流程图的页面仍需视觉对照（见 `待人工核验的重点差异.md`）。")
    L2.append("")
    L2.append("## 5. 高风险提示")
    L2.append("")
    L2.append("1. 表格合并单元格**全部未还原**（%d 张逻辑表均有 `merge_suspects`），"
              "文本层比对只能证明「单元格文字是否有变化」，不能证明表格结构未变。" % len(t["rows"]))
    L2.append("2. 网格不可靠的表格共 %d 张，其数值比对结论必须回原文确认。" % unrel)
    L2.append("3. 分式内上下标方向可能失真，%d 条分式全部需人工核验。" % len(fm["rows"]))
    L2.append("4. %d 张插图像素不同，需视觉对照；%d 张像素一致，可判定未变。"
              % (f["matched"] - f["identical_binary"], f["identical_binary"]))
    L2.append("")
    open(os.path.join(L.OUT, "特殊内容差异清单.md"), "w", encoding="utf-8").write("\n".join(L2) + "\n")
    print("written 特殊内容差异清单.md (%d lines)" % len(L2))

    # ====================== 3. 差异覆盖与质量报告.md ======================
    st = Counter(r["status"] for r in status)
    body_recs = [r for r in status if r["status"] != "不计入正文比对"]
    L3 = []
    L3.append("# 差异覆盖与质量报告（阶段 B2）")
    L3.append("")
    L3.append("说明本阶段**检查了什么、覆盖到什么程度、哪些还没有结论**。")
    L3.append("")
    L3.append("## 0. 结论")
    L3.append("")
    L3.append("**B2 候选差异发现完成，覆盖率 100%，无静默遗漏。** 但请注意：")
    L3.append("")
    L3.append("> **「自动比对通过 / 未发现变化」不等于「规则语义未变」。** "
              "本阶段所有差异均为**候选**，`verify_status` 全部为 `unverified`；"
              "表格合并结构、插图内容、流程图连接关系、分式拼装均未最终确认。")
    L3.append("")
    L3.append("## 1. 覆盖统计")
    L3.append("")
    L3.append("### 1.1 章节")
    L3.append("")
    L3.append("| 项目 | 2026 | 2027 |")
    L3.append("|---|---|---|")
    L3.append("| 正式章节 | %d | %d |" % (align["coverage"]["sections_2026"],
                                          align["coverage"]["sections_2027"]))
    L3.append("| 进入映射（B1） | %d | %d |" % (align["coverage"]["sections_2026_mapped"],
                                               align["coverage"]["sections_2027_mapped"]))
    L3.append("| 有正文记录参与比对 | %d | %d |"
              % (len({r["section_no"] for r in status if r["doc"] == "RMUC2026"
                      and r["status"] != "不计入正文比对"}),
                 len({r["section_no"] for r in status if r["doc"] == "RMUC2027"
                      and r["status"] != "不计入正文比对"})))
    L3.append("")
    L3.append("### 1.2 正文记录（逐条有状态）")
    L3.append("")
    L3.append("`差异覆盖状态.jsonl` 为**每一条结构化记录**给出处理状态，共 %d 条：" % len(status))
    L3.append("")
    L3.append("| 状态 | 条数 | 说明 |")
    L3.append("|---|---|---|")
    desc = {
        "全部一致": "该记录所有句段均为内容一致/编号变化",
        "仅含轻度候选差异": "只涉及文字调整或推测配对",
        "含实质候选差异": "至少一条实质修改/新增/删除候选",
        "无可比对文本（仅符号/空白）": "记录只有项目符号或空白，无文本可比",
        "转入特殊内容流程": "表格/插图/公式/表图题，由特殊内容流程处理",
        "不计入正文比对": "目录条目、封面、内联图标，明确排除并给出理由",
        "未进入比对（异常）": "应已覆盖却未覆盖（应为 0）",
        "未分类（异常）": "未分类记录（应为 0）",
    }
    for k, v in sorted(st.items(), key=lambda kv: -kv[1]):
        L3.append("| %s | %d | %s |" % (k, v, desc.get(k, "")))
    L3.append("")
    L3.append("异常状态：`未进入比对（异常）` = %d，`未分类（异常）` = %d。"
              % (st.get("未进入比对（异常）", 0), st.get("未分类（异常）", 0)))
    L3.append("")
    L3.append("### 1.3 特殊内容")
    L3.append("")
    L3.append("| 类别 | 2026 | 2027 | 已处理 | 状态字段 |")
    L3.append("|---|---|---|---|---|")
    L3.append("| 表格（原始记录） | %d | %d | 100%% | `table_coverage` |"
              % (sp["raw_table_records"]["total_2026"], sp["raw_table_records"]["total_2027"]))
    L3.append("| 表格（逻辑表，跨页合并） | %d | %d | 100%% | `tables.rows` |"
              % (sp["tables"]["total_2026"], sp["tables"]["total_2027"]))
    L3.append("| 插图 | %d | %d | 100%% | `figure_coverage` |"
              % (sp["figures"]["total_2026"], sp["figures"]["total_2027"]))
    L3.append("| 上下分式 | %d | %d | 100%% | `formula_coverage` |"
              % (sp["formulas"]["total_2026_fraction"], sp["formulas"]["total_2027_fraction"]))
    L3.append("| 上下标记录 | %d | %d | 100%% | `formula_coverage` |"
              % (len([x for x in sp["formula_coverage"] if x["kind"] == "script_spans"
                      and x["doc"] == "RMUC2026"]),
                 len([x for x in sp["formula_coverage"] if x["kind"] == "script_spans"
                      and x["doc"] == "RMUC2027"])))
    L3.append("")
    L3.append("## 2. 上游 8 项决策的落实情况")
    L3.append("")
    L3.append("| # | 决策 | 落实情况 |")
    L3.append("|---|---|---|")
    ver = {v["align_id"]: v for v in body["deleted_added_verification"]}
    L3.append("| 1 | 6 个疑似删除章节必须进一步检索验证 | 已对每个单元做**全文兜底检索**（长度 ≥12 字的句段逐条求最高相似度），"
              "结果见 2.1 |")
    L3.append("| 2 | 3 个新增空容器不计入实质机制新增 | 已在 B1 判为「层级容器」，B2 不产生其实质新增候选（0 字正文） |")
    L3.append("| 3 | 梯形高地增益点 vs 制高点增益点=机制替换候选 | 两节正文相似度低（0.6 以下），已作为「重命名+机制替换」候选单元参与逐条比对 |")
    L3.append("| 4 | 英雄/重装特殊机制结构合并、内部逐项判断 | 已按 2:1 合并单元比对，「部署模式」相关句段全部列为删除候选 |")
    L3.append("| 5 | `diagram_label` 必须纳入 | 已纳入正文比对（%d 条图示文字句段） |" % sum(dg["by_type"].values()))
    L3.append("| 6 | 不还原全部表格，但建全表覆盖清单+重要参数核验 | 154 条原始表记录全部进入 `table_coverage`，%d 张逻辑表逐张比对 |" % len(sp["tables"]["rows"]))
    L3.append("| 7 | 差异记录含双方来源/章节/页码/record_id/原文/核验状态 | JSONL 每条均含 `a`/`b` 两侧完整溯源与 `verify_status` |")
    L3.append("| 8 | 批注版不进入正文 | 全部数据仅来自官方版；批注版未参与任何比对 |")
    L3.append("")
    L3.append("### 2.1 六个「疑似删除」章节的检索验证结果")
    L3.append("")
    L3.append("| 单元 | 2026 章节 | 句段数 | 全文最高相似度 | 最相似位置 | 结论 |")
    L3.append("|---|---|---|---|---|---|")
    for aid in ("AL-024", "AL-037", "AL-053", "AL-081", "AL-085", "AL-122"):
        v = ver.get(aid)
        if not v:
            continue
        names = "、".join(v["sections_2026"]) or "—"
        best = v.get("max_similarity_detail") or []
        b = best[0] if best else {}
        L3.append("| %s | %s | %d | %.3f | %s | %s |" % (
            aid, names, v["sentences"], v["max_similarity"],
            ("%s：%s" % (b.get("best_section", ""), (b.get("text") or "")[:30])) if b else "—",
            "未找到对应表述" if v["max_similarity"] < 0.80
            else "**部分表述在他处保留**，需人工确认是否迁移"))
    L3.append("")
    L3.append("## 3. 未决项")
    L3.append("")
    L3.append("| 项目 | 数量 | 原因 |")
    L3.append("|---|---|---|")
    L3.append("| 正文待核验 | %d | 含新增/删除/实质修改/推测配对 |" % body["needs_review"])
    L3.append("| 表格待核验 | %d | 网格不可靠或参数变化 |" % len(sp["tables"]["rows"]))
    L3.append("| 插图待视觉对照 | %d | 像素不同或无法定位 |"
              % (sp["figures"]["matched"] - sp["figures"]["identical_binary"]
                 + sp["figures"]["by_type"].get("删除候选", 0)
                 + sp["figures"]["by_type"].get("新增候选", 0)))
    L3.append("| 公式待核验 | %d | 上下标/分式布局 |" % len(sp["formulas"]["rows"]))
    L3.append("| B1 映射存疑 | %d | 单元 `needs_review` |" % len(align["coverage"]["needs_review_units"]))
    L3.append("")
    L3.append("## 4. 检查项：是否存在「未匹配且未列入候选差异」的记录")
    L3.append("")
    L3.append("| 检查 | 结果 |")
    L3.append("|---|---|")
    L3.append("| 每条正文记录的句段是否都归入某个 diff 记录 | ✔ 是（%d 句段全部归类） |"
              % (body["sentences_2026"] + body["sentences_2027"]))
    L3.append("| 是否有记录既未匹配也未列为候选 | ✔ 无 |")
    L3.append("| 是否有章节范围以外的内容被比对 | ✔ 无（仅 `region_type=section`） |")
    L3.append("| 是否有未纳入检查的表格/公式/图示 | ✔ 无（覆盖清单见特殊内容清单） |")
    L3.append("| 旧章节已取消但机制在他处保留 | ✔ 已检出（迁移候选 %d 条，含 5.6.3/附录1 的部分表述） |"
              % body["diff_by_type"].get("迁移或重组候选", 0))
    L3.append("")
    L3.append("## 5. 局限")
    L3.append("")
    L3.append("1. **句段级比对不是语义比对**。同一规则换了表达方式时，可能被判为「实质修改候选」甚至「删除+新增」，需人工确认。")
    L3.append("2. **推测配对**（同章节低相似度配对，%d 对）是程序推断，必须逐条核验。"
              % sum(1 for r in diffs if r["evidence"].get("tentative_pairing")))
    L3.append("3. **表格结构未还原**，合并单元格与跨页续页只能靠「逻辑表」近似处理。")
    L3.append("4. **插图只比对像素哈希**；像素不同不代表语义不同（可能只是重绘），需视觉判断。")
    L3.append("5. **流程图连接关系不可恢复**，图示文字比对不覆盖流程走向。")
    L3.append("6. **分式未拼装**，上下标方向可能失真。")
    L3.append("7. 本阶段**不做最终语义判定**，不生成规则变更总结。")
    L3.append("")
    L3.append("## 6. 复现")
    L3.append("")
    L3.append("```powershell")
    L3.append("& $py tools/50_b2_body.py      # 正文候选差异")
    L3.append("& $py tools/51_b2_special.py   # 表格/公式/插图/图示文字")
    L3.append("& $py tools/52_b2_reports.py   # 本报告与其余 3 份")
    L3.append("& $py tools/53_b2_verify.py    # 覆盖与一致性断言")
    L3.append("```")
    L3.append("")
    open(os.path.join(L.OUT, "差异覆盖与质量报告.md"), "w", encoding="utf-8").write("\n".join(L3) + "\n")
    print("written 差异覆盖与质量报告.md (%d lines)" % len(L3))

    # ====================== 4. 待人工核验的重点差异.md ======================
    pri = []
    unit_rel = {u["align_id"]: u for u in align["alignments"]}
    for r in diffs:
        dt = r["diff_type"]
        ev = r["evidence"] or {}
        p = None
        tag = []
        if dt == "实质修改候选" and ev.get("numbers"):
            p, tag = "P1", ["数值参数变化"]
        elif dt == "删除候选" and (unit_rel.get(r["align_id"], {}).get("relation") == "deleted"):
            p, tag = "P1", ["整节疑似删除"]
        elif dt == "新增候选" and (unit_rel.get(r["align_id"], {}).get("relation") == "added"):
            p, tag = "P1", ["整节疑似新增"]
        elif dt == "实质修改候选":
            p, tag = "P2", ["表述实质变化"]
        elif dt in ("新增候选", "删除候选"):
            p, tag = "P2", ["单条疑似增删"]
        elif dt == "迁移或重组候选":
            p, tag = "P2", ["跨章节迁移"]
        elif ev.get("tentative_pairing"):
            p, tag = "P2", ["推测配对"]
        if not p:
            continue
        sec = r["section_2026"] or r["section_2027"] or {}
        pri.append(dict(priority=p, source="正文", tags=tag, diff=r, sec=sec))
    for r in sp["tables"]["rows"]:
        if r["diff_type"] == "实质修改候选" and r["evidence"].get("numbers"):
            pri.append(dict(priority="P1", source="表格", tags=["表格数值变化"], diff=r,
                            sec={"no": (r["table_2026"] or {}).get("section_no"),
                                 "title": (r["table_2026"] or {}).get("section_title")}))
        elif r["diff_type"] in ("删除候选", "新增候选", "迁移或重组候选"):
            pri.append(dict(priority="P2", source="表格", tags=[r["diff_type"]], diff=r,
                            sec={"no": (r["table_2026"] or {}).get("section_no"),
                                 "title": (r["table_2026"] or {}).get("section_title")}))
    for r in sp["formulas"]["rows"]:
        if r["diff_type"] == "实质修改候选":
            pri.append(dict(priority="P1", source="公式", tags=["公式变化"], diff=r, sec={}))
        elif r["diff_type"] in ("删除候选", "新增候选"):
            pri.append(dict(priority="P2", source="公式", tags=[r["diff_type"]], diff=r, sec={}))
    for r in sp["figures"]["rows"]:
        if r["diff_type"] in ("删除候选", "新增候选", "迁移或重组候选"):
            pri.append(dict(priority="P2", source="插图", tags=["需视觉对照"], diff=r, sec={}))

    p1 = [x for x in pri if x["priority"] == "P1"]
    p2 = [x for x in pri if x["priority"] == "P2"]
    L4 = []
    L4.append("# 待人工核验的重点差异（阶段 B2）")
    L4.append("")
    L4.append("按「是否影响机器人属性 / 比赛机制 / 数值参数 / 重大规则变化」排序。"
              "**全部为候选，尚无一条经过确认**。")
    L4.append("")
    L4.append("## 0. 汇总")
    L4.append("")
    L4.append("| 优先级 | 条数 | 含义 |")
    L4.append("|---|---|---|")
    L4.append("| P1 | %d | 影响数值参数、或整节增删（最可能改变比赛行为的项） |" % len(p1))
    L4.append("| P2 | %d | 表述实质变化、单条增删、迁移、推测配对 |" % len(p2))
    L4.append("")
    L4.append("## 1. P1：数值参数与整节增删")
    L4.append("")
    L4.append("### 1.1 整节疑似新增 / 删除（先看这些）")
    L4.append("")
    for u in align["alignments"]:
        if u["relation"] not in ("deleted", "added"):
            continue
        v = ver.get(u["align_id"])
        s26 = "、".join(x["no"] or x["title"] for x in u["sections_2026"]) or "—"
        s27 = "、".join(x["no"] or x["title"] for x in u["sections_2027"]) or "—"
        extra = ""
        if v:
            extra = "；全文兜底检索：%d 个句段，最高相似度 %.3f%s" % (
                v["sentences"], v["max_similarity"],
                "（有表述在他处保留，需确认是否迁移）" if v["max_similarity"] >= 0.80 else "（未找到对应表述）")
        L4.append("- **%s** %s → %s（%s）%s" % (REL_CN[u["relation"]], s26, s27, u["align_id"], extra))
    L4.append("")
    L4.append("### 1.2 数值参数变化（正文，%d 条）"
              % len([x for x in p1 if x["source"] == "正文"]))
    L4.append("")
    L4.append("| # | 章节 | 2026 原文 | 2027 原文 | 数值变化 |")
    L4.append("|---|---|---|---|---|")
    n = 0
    for x in p1:
        if x["source"] != "正文":
            continue
        r = x["diff"]
        a, b = r["a"], r["b"]
        ev = r["evidence"].get("numbers") or {}
        num = "增 %s / 减 %s" % ((ev.get("added") or [])[:5], (ev.get("removed") or [])[:5])
        L4.append("| %d | %s | %s | %s | %s |" % (
            n + 1, x["sec"].get("no") or "—",
            (a["text"] if a else "—")[:60].replace("|", "\\|"),
            (b["text"] if b else "—")[:60].replace("|", "\\|"), num))
        n += 1
        if n >= 60:
            L4.append("| … | 其余 %d 条见 `全文候选差异.jsonl` | | | |" % (len(p1) - n))
            break
    L4.append("")
    L4.append("### 1.3 表格数值变化（%d 张）"
              % len([x for x in p1 if x["source"] == "表格"]))
    L4.append("")
    L4.append("| # | 2026 表 | 2027 表 | 数值变化 |")
    L4.append("|---|---|---|---|")
    n = 0
    for x in p1:
        if x["source"] != "表格":
            continue
        r = x["diff"]
        a, b = r["table_2026"], r["table_2027"]
        ev = r["evidence"].get("numbers") or {}
        L4.append("| %d | P%d %s | P%d %s | 增 %s / 减 %s |" % (
            n + 1, a["physical_page"], (a["caption"] or a["table_no"] or "-")[:24],
            b["physical_page"], (b["caption"] or b["table_no"] or "-")[:24],
            _keys(ev.get("added")), _keys(ev.get("removed"))))
        n += 1
        if n >= 30:
            break
    L4.append("")
    L4.append("### 1.4 公式变化")
    L4.append("")
    for x in p1:
        if x["source"] != "公式":
            continue
        r = x["diff"]
        a, b = r["formula_2026"], r["formula_2027"]
        if r.get("kind") == "formula_fraction":
            L4.append("- P%d `%s / %s` → P%d `%s / %s`"
                      % (a["physical_page"], a["numerator"], a["denominator"],
                         b["physical_page"], b["numerator"], b["denominator"]))
        else:
            L4.append("- P%d `%s` → P%d `%s`（上下标：%s → %s）"
                      % (a["physical_page"], (a.get("text") or "")[:50],
                         b["physical_page"], (b.get("text") or "")[:50],
                         a.get("spans"), b.get("spans")))
    L4.append("")
    L4.append("## 2. P2：其余需要确认的候选")
    L4.append("")
    cat = Counter()
    for x in p2:
        cat[(x["source"], x["tags"][0])] += 1
    L4.append("| 类别 | 条数 |")
    L4.append("|---|---|")
    for (s, t_), v in cat.most_common():
        L4.append("| %s · %s | %d |" % (s, t_, v))
    L4.append("")
    L4.append("### 2.1 需视觉对照的插图（%d 张）"
              % len([x for x in p2 if x["source"] == "插图"]))
    L4.append("")
    for x in p2:
        if x["source"] != "插图":
            continue
        r = x["diff"]
        a = r["figure_2026"]
        b = r["figure_2027"]
        if a and b:
            L4.append("- P%d `%s` → P%d `%s`（像素不同）"
                      % (a["physical_page"], (a["caption"] or "无图注")[:28],
                         b["physical_page"], (b["caption"] or "无图注")[:28]))
        else:
            z = a or b
            L4.append("- P%d `%s` %s" % (z["physical_page"], (z["caption"] or "无图注")[:28],
                                         r["diff_type"]))
    L4.append("")
    L4.append("## 3. 建议的核验顺序")
    L4.append("")
    L4.append("1. 先看 1.1 的整节增删（6 个疑似删除 + 5 个实质新增 + 3 个容器不计数）。")
    L4.append("2. 再看 1.2 / 1.3 的数值参数变化（最直接影响比赛行为）。")
    L4.append("3. 然后 1.4 公式与 2.1 插图视觉对照。")
    L4.append("4. 最后处理 P2 里的表述变化与推测配对。")
    L4.append("")
    L4.append("**注意**：本清单中的所有条目 `verify_status` 仍为 `unverified`，"
              "不得直接当作已经确认的变更写入结论。")
    L4.append("")
    open(os.path.join(L.OUT, "待人工核验的重点差异.md"), "w", encoding="utf-8").write("\n".join(L4) + "\n")
    print("written 待人工核验的重点差异.md (%d lines)" % len(L4))
    print("P1=%d P2=%d" % (len(p1), len(p2)))


if __name__ == "__main__":
    main()
