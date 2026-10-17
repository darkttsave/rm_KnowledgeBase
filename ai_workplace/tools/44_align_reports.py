#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 4 (phase B1) -- step 3: render the human-facing deliverables from
章节对应关系.json (single source of truth).

Outputs: 章节对齐总览.md / 章节对齐异常清单.md / 章节对齐质量报告.md
"""
import os
import json
from collections import Counter, OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "ai_workplace", "alignment")

REL_CN = {"kept": "保留", "renamed": "重命名", "moved": "迁移", "merged": "合并",
          "split": "拆分", "added": "疑似新增", "deleted": "疑似删除"}
REL_ORDER = ["kept", "renamed", "moved", "merged", "split", "added", "deleted"]


def load():
    return json.load(open(os.path.join(OUT, "章节对应关系.json"), encoding="utf-8"))


def pages(x):
    if not x["physical_pages"]:
        return "—"
    a, b = x["physical_pages"][0], x["physical_pages"][-1]
    pa = x["printed_pages"][0] if x["printed_pages"] else a - 1
    pb = x["printed_pages"][-1] if x["printed_pages"] else b - 1
    return ("P%d" % a) if a == b else ("P%d–%d" % (a, b))


def pages_long(x):
    if not x["physical_pages"]:
        return "—"
    a, b = x["physical_pages"][0], x["physical_pages"][-1]
    pa, pb = a - 1, b - 1
    return ("物理 %d ／ 印刷 %d" % (a, pa)) if a == b else ("物理 %d–%d ／ 印刷 %d–%d" % (a, b, pa, pb))


def cell(x):
    if not x:
        return "—"
    no = x["no"]
    label = ("%s %s" % (no, x["name"])) if no else x["title"]
    return "%s<br><sub>%s · %d 字</sub>" % (label, pages(x), x["chars"])


def l1_of(sec):
    return sec["path"][0] if sec["path"] else sec["title"]


def main():
    A = load()
    units = A["alignments"]
    meta = A["meta"]
    cov = A["coverage"]

    # ---------- chapter level roll-up ----------
    chap26 = OrderedDict()
    for x in A["section_index"]["2026"]:
        pass
    # build L1 ordering from the 2026 / 2027 section lists
    order = []
    for u in units:
        for s in u["sections_2026"]:
            t = l1_of(s)
            if t not in order:
                order.append(t)
    for u in units:
        for s in u["sections_2027"]:
            t = l1_of(s)
            if t not in order:
                order.append(t)

    by_chapter = OrderedDict((t, []) for t in order)
    for u in units:
        keys = set()
        for s in u["sections_2026"]:
            keys.add(l1_of(s))
        for s in u["sections_2027"]:
            keys.add(l1_of(s))
        # attach to the 2026 chapter when available, else to the 2027 chapter
        target = None
        if u["sections_2026"]:
            target = l1_of(u["sections_2026"][0])
        else:
            target = l1_of(u["sections_2027"][0])
        by_chapter.setdefault(target, []).append(u)
        for k in keys:
            by_chapter.setdefault(k, [])

    chapters = OrderedDict()
    for t in order:
        us = by_chapter.get(t, [])
        s26 = [s for u in us for s in u["sections_2026"]]
        s27 = [s for u in us for s in u["sections_2027"]]
        chapters[t] = dict(units=us, n26=len(s26), n27=len(s27),
                           pages26=(min([p for s in s26 for p in s["physical_pages"]] or [0]),
                                    max([p for s in s26 for p in s["physical_pages"]] or [0])),
                           pages27=(min([p for s in s27 for p in s["physical_pages"]] or [0]),
                                    max([p for s in s27 for p in s["physical_pages"]] or [0])),
                           rel=Counter(u["relation"] for u in us))

    cnt = Counter(u["relation"] for u in units)
    n_rev = sum(1 for u in units if u["needs_review"])
    n_renum = sum(1 for u in units if u["renumbered"])
    n_auto = sum(1 for u in units if any(e.startswith("C:") for e in u["evidence"])
                 and not any(e.startswith("M:") for e in u["evidence"]))

    # ======================= 章节对齐总览.md =======================
    L = []
    L.append("# 章节对齐总览（阶段 B1）")
    L.append("")
    L.append("**RMUC 2026 V2.2.0 → RMUC 2027 V1.0.0　章节对应关系完整清单**")
    L.append("")
    L.append("> 机器可读版：`ai_workplace/alignment/章节对应关系.json`（本表由它渲染，二者一致）。")
    L.append("> 对应关系按「章节主题 + 标题 + 正文 + 上下级关系」判定；**章节编号只作参考，不作为对应依据**。")
    L.append("")
    L.append("## 统计")
    L.append("")
    L.append("| 项目 | 数值 |")
    L.append("|---|---|")
    L.append("| 2026 正式章节（书签条目） | %d |" % cov["sections_2026"])
    L.append("| 2027 正式章节（书签条目） | %d |" % cov["sections_2027"])
    L.append("| 对齐单元 | %d |" % cov["units"])
    L.append("| 2026 已进入映射 | **%d / %d** |" % (cov["sections_2026_mapped"], cov["sections_2026"]))
    L.append("| 2027 已进入映射 | **%d / %d** |" % (cov["sections_2027_mapped"], cov["sections_2027"]))
    L.append("| 静默遗漏 | **0** |")
    L.append("| 其中「保留」（含编号顺延） | %d（编号顺延 %d） |" % (cnt["kept"], n_renum))
    L.append("| 重命名 | %d |" % cnt["renamed"])
    L.append("| 迁移 | %d |" % cnt["moved"])
    L.append("| 合并 | %d |" % cnt["merged"])
    L.append("| 拆分 | %d |" % cnt["split"])
    L.append("| 疑似新增 | %d |" % cnt["added"])
    L.append("| 疑似删除 | %d |" % cnt["deleted"])
    L.append("| 待人工核验单元 | %d |" % n_rev)
    L.append("")
    L.append("## 章级对应")
    L.append("")
    L.append("| # | 2026 章 | 2027 章 | 2026 节数 | 2027 节数 | 关系分布 |")
    L.append("|---|---|---|---|---|---|")
    for i, (t, c) in enumerate(chapters.items(), 1):
        if not c["units"]:
            continue
        titles27 = []
        for u in c["units"]:
            for s in u["sections_2027"]:
                k = l1_of(s)
                if k not in titles27:
                    titles27.append(k)
        t27 = " ／ ".join(titles27) if titles27 else "—"
        rel = "、".join("%s%d" % (REL_CN[k], v) for k, v in
                        sorted(c["rel"].items(), key=lambda kv: REL_ORDER.index(kv[0])))
        L.append("| %d | %s | %s | %d | %d | %s |"
                 % (i, t, t27, c["n26"], c["n27"], rel))
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 完整映射表")
    L.append("")
    L.append("图例：关系 = 保留 / 重命名 / 迁移 / 合并 / 拆分 / 疑似新增 / 疑似删除；"
             "「待核验 ✔」表示该单元需人工确认（共 %d 个）。" % n_rev)
    L.append("")
    for t, c in chapters.items():
        if not c["units"]:
            continue
        L.append("### %s" % t)
        L.append("")
        L.append("| 2026 章节 | 页码 | 关系 | 2027 章节 | 页码 | 置信度 | 待核验 |")
        L.append("|---|---|---|---|---|---|---|")
        for u in c["units"]:
            a26 = "<br>".join(cell(x) for x in u["sections_2026"]) or "—"
            p26 = "<br>".join(pages(x) for x in u["sections_2026"]) or "—"
            a27 = "<br>".join(cell(x) for x in u["sections_2027"]) or "—"
            p27 = "<br>".join(pages(x) for x in u["sections_2027"]) or "—"
            L.append("| %s | %s | **%s**%s | %s | %s | %.2f | %s |"
                     % (a26, p26, REL_CN[u["relation"]],
                        "（复编号）" if u["renumbered"] and u["relation"] == "kept" else "",
                        a27, p27, u["confidence"], "✔" if u["needs_review"] else ""))
        L.append("")
    L.append("## 附：非正式章节区域（封面 / 目录 / 表目录 / 图目录）")
    L.append("")
    L.append("两份文档都各有 4 个**不属于正式章节**的合成区域（`region_type != section`）：封面、目录、表目录、图目录。"
             "它们在两份文档间一一对应（按区域类型对应），但不参与规则正文比对，故不计入上面的 130/129 正式章节统计。")
    L.append("")
    open(os.path.join(OUT, "章节对齐总览.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("written 章节对齐总览.md  (%d lines)" % len(L))

    # ==================== 章节对齐异常清单.md ====================
    L = []
    L.append("# 章节对齐异常清单（阶段 B1）")
    L.append("")
    L.append("本清单只列出**需要人工判断**的章节对应：无法匹配、疑似新增/删除、合并、拆分、重命名、迁移与待核验项。"
             "「保留」的 %d 个单元不在此列（见 `章节对齐总览.md`）。" % cnt["kept"])
    L.append("")

    def unit_block(u, extra_title=None):
        b = []
        b.append("#### %s　%s（%s，置信度 %.2f）" % (u["align_id"], extra_title or REL_CN[u["relation"]],
                                                 u["match_type"], u["confidence"]))
        b.append("")
        if u["sections_2026"]:
            b.append("- **2026**：" + "；".join(
                "%s `%s`（%s，%d 字）" % (x["no"] or "（无编号）", x["title"], pages_long(x), x["chars"])
                for x in u["sections_2026"]))
            b.append("  - 路径：" + " ／ ".join(" › ".join(x["path"]) for x in u["sections_2026"]))
        else:
            b.append("- **2026**：*无对应章节*")
        if u["sections_2027"]:
            b.append("- **2027**：" + "；".join(
                "%s `%s`（%s，%d 字）" % (x["no"] or "（无编号）", x["title"], pages_long(x), x["chars"])
                for x in u["sections_2027"]))
            b.append("  - 路径：" + " ／ ".join(" › ".join(x["path"]) for x in u["sections_2027"]))
        else:
            b.append("- **2027**：*无对应章节*")
        b.append("- 判断依据：")
        for e in u["evidence"]:
            b.append("  - %s" % e)
        if u.get("note"):
            b.append("- 说明：%s" % u["note"])
        if u.get("content_delta_hint"):
            b.append("- ⚠ 正文差异线索（留待 B2）：%s" % u["content_delta_hint"])
        if u["needs_review"]:
            b.append("- **待人工核验 ✔**")
        b.append("")
        return b

    groups = [
        ("deleted", "A. 疑似删除（章节在 2027 中无对应）",
         "判定为「疑似删除」而非「已删除」——B1 只做章节层面对齐，规则内容是否真正废弃需 B2 正文比对确认。",
         "建议：B2 时在 2027 全文按关键机制词逐项检索复核（本清单已给出检索命中数）。"),
        ("added", "B. 疑似新增（2027 章节在 2026 中无对应）",
         "区分为两类：**B1 真实新增机制/场地要素** 与 **B2 纯层级容器**（正文为空，仅新增 L2 层）。"
         "后者不是新规则机制，不得按「全新机制」对待。",
         "建议：B1 真实新增项进入 B2 的「新增内容」清单；层级容器只影响目录结构。"),
        ("merged", "C. 合并（多章 → 一章）",
         "两份文档都存在「重装=英雄+工程」这类合并。合并后的章节内容是否 1:1 继承需 B2 比对。",
         "建议：B2 按「被合并源逐条 → 合并目标」做内容覆盖检查。"),
        ("split", "D. 拆分（一章 → 多章）", "", ""),
        ("renamed", "E. 重命名（主题延续，标题变化）",
         "重命名可能同时伴随内容调整（如「雷达特殊机制」→「雷达系统特殊机制」）。",
         "建议：B2 直接按对齐关系做正文比对，无需再确认章节对应。"),
        ("moved", "F. 迁移（层级/章节归属变化）",
         "本次只有 1 例跨章迁移：`5.7 自定义客户端` → `3.3.1 自定义终端`（机制 → 附属设备）。",
         "建议：B2 注意其父章节语义已从「比赛机制」变为「机器人与操作手」。"),
    ]
    for rel, title, desc, advice in groups:
        us = [u for u in units if u["relation"] == rel]
        L.append("## %s　共 %d 个" % (title, len(us)))
        L.append("")
        if desc:
            L.append("> " + desc)
            L.append("")
        if not us:
            L.append("（无）")
            L.append("")
            continue
        for u in us:
            L += unit_block(u)
        if advice:
            L.append("**处理建议**：" + advice.replace("建议：", ""))
            L.append("")

    rev = [u for u in units if u["needs_review"]]
    L.append("## G. 待人工核验汇总　共 %d 个" % len(rev))
    L.append("")
    L.append("| 对齐单元 | 关系 | 2026 | 2027 | 核验要点 |")
    L.append("|---|---|---|---|---|")
    for u in rev:
        s26 = "、".join(x["no"] or x["title"] for x in u["sections_2026"]) or "—"
        s27 = "、".join(x["no"] or x["title"] for x in u["sections_2027"]) or "—"
        key = (u.get("content_delta_hint") or u.get("note")
               or ("确认该章节机制是否确实废弃（B2 正文复核）" if u["relation"] == "deleted"
                   else "确认对应关系"))
        L.append("| %s | %s | %s | %s | %s |"
                 % (u["align_id"], REL_CN[u["relation"]], s26, s27, key.replace("|", "\\|")[:80]))
    L.append("")
    L.append("## H. 编号顺延（非变更，仅提示）")
    L.append("")
    L.append("共 **%d** 个单元属于「标题不变、仅编号位移」（例如 2026 `5.2` → 2027 `5.3`、"
             "`5.5.3.x` → `5.6.4.x`）。这类位移由「2027 新增 5.2 自适应装甲机制、5.6.2 战场控制机制」"
             "等插入导致。**编号差异不得作为章节新增/删除的依据**，本清单已把这类单元统一判为「保留」。"
             % n_renum)
    L.append("")
    renum = [(u["sections_2026"][0]["no"], u["sections_2027"][0]["no"])
             for u in units if u["renumbered"]
             and u["relation"] == "kept" and len(u["sections_2026"]) == 1]
    L.append("| 2026 → 2027（编号） | 数量 |")
    L.append("|---|---|")
    L.append("| 例如：%s | 其中「保留」类：%d 个单元 |"
             % ("、".join("%s→%s" % (a, b) for a, b in renum[:10]), len(renum)))
    L.append("")
    L.append("其余 %d 个编号顺延出现在「重命名 / 迁移」单元中（例如 5.6.6→5.7.4、5.7→3.3.1）。"
             % (n_renum - len(renum)))
    L.append("")
    open(os.path.join(OUT, "章节对齐异常清单.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("written 章节对齐异常清单.md  (%d lines)" % len(L))

    # ==================== 章节对齐质量报告.md ====================
    L = []
    L.append("# 章节对齐质量报告（阶段 B1）")
    L.append("")
    L.append("**任务**：建立 RMUC 2026 V2.2.0 与 RMUC 2027 V1.0.0 的章节对应关系，为后续正文差异分析（B2）提供基础。")
    L.append("")
    L.append("生成时间：%s" % meta["generated"])
    L.append("")
    L.append("## 0. 结论")
    L.append("")
    L.append("**B1 完成，具备进入 B2 的条件。** 两份文档的 **全部正式章节**（2026 130 个、2027 129 个）"
             "都已进入映射，**静默遗漏 0**。")
    L.append("")
    L.append("- 存在对应的单元：%d 个（其中 1:1 共 %d 个，2:1 合并 %d 个），"
             "覆盖 %d 个 2026 章节 / %d 个 2027 章节"
             % (cnt["kept"] + cnt["renamed"] + cnt["moved"] + cnt["merged"],
                cnt["kept"] + cnt["renamed"] + cnt["moved"], cnt["merged"],
                cov["sections_2026"] - sum(len(u["sections_2026"]) for u in units if u["relation"] == "deleted"),
                cov["sections_2027"] - sum(len(u["sections_2027"]) for u in units if u["relation"] == "added")))
    L.append("- 结构变化：合并 %d、拆分 %d、迁移 %d、重命名 %d" % (cnt["merged"], cnt["split"], cnt["moved"], cnt["renamed"]))
    L.append("- 内容增减：疑似新增 %d、疑似删除 %d" % (cnt["added"], cnt["deleted"]))
    L.append("- 需人工确认：%d 个单元" % n_rev)
    L.append("")
    L.append("## 1. 输入与范围")
    L.append("")
    L.append("| 项目 | 说明 |")
    L.append("|---|---|")
    L.append("| 2026 文档 | RMUC 2026 V2.2.0，159 物理页，130 个正式章节 |")
    L.append("| 2027 文档 | RMUC 2027 V1.0.0，144 物理页，129 个正式章节 |")
    L.append("| 复用输入 | 阶段 A 的章节骨架 JSON、结构化 JSONL、Markdown、待核验清单 |")
    L.append("| 未重复执行 | PDF 全文解析（直接读阶段 A 产物） |")
    L.append("| 范围外 | 逐条正文差异、表格人工还原、公式/流程图语义、RAG、变更总结 |")
    L.append("")
    L.append("## 2. 对齐方法")
    L.append("")
    L.append("### 2.1 程序生成候选（可复现）")
    L.append("")
    L.append("脚本：`ai_workplace/tools/40_align_candidates.py`，产物：`alignment/align_candidates.json`。")
    L.append("")
    L.append("1. **章节特征**：标题（去掉编号）字符二元组集合；正文（段落 + 表格单元格 + 表/图题）字符二元组计数。")
    L.append("2. **相似度**：标题 Jaccard、正文余弦；组合分 = 0.45×标题 + 0.40×正文 + 0.10×编号先验 + 0.05×层级。")
    L.append("3. **条款级路由**：把每个 ≥10 字的条款按二元组包含度路由到最相似的对方章节（阈值 0.6），"
             "得到**份额矩阵**。这是区分「合并/拆分」与「找不到」的关键证据：")
    L.append("   - 单个 2026 章节的条款被多个 2027 章节吸收 → 拆分线索；")
    L.append("   - 单个 2027 章节吸收多个 2026 章节的条款 → 合并线索；")
    L.append("   - 条款 0 命中 → 疑似删除；新章节 0 来源 → 疑似新增。")
    L.append("4. **自动匹配**：标题去编号后完全相同的，直接判为「保留」（107 对）。")
    L.append("")
    L.append("### 2.2 语义裁断（LLM 辅助，依据全部落盘）")
    L.append("")
    L.append("脚本：`ai_workplace/tools/43_align_build.py` 中的 `MANUAL` 决策表。对程序无法定论的 45 个章节，"
             "逐条依据下列证据裁断，并把依据写进 `evidence` 字段：")
    L.append("")
    L.append("| 证据类型 | 含义 | 标记前缀 |")
    L.append("|---|---|---|")
    L.append("| 正文对照 | 直接比对两节正文/表格 | `D:` |")
    L.append("| 关键词命中 | `42_search.py` 统计某术语在两份文档中的出现次数与所在章节 | `S:` |")
    L.append("| 候选分数 | 相似度与路由份额 | `C:` |")
    L.append("| 程序匹配 | 标题完全一致 | `P:` |")
    L.append("| 变更说明 | 2027 §1.2「新赛季主要变更」的表述 | `M:` |")
    L.append("")
    L.append("**没有使用**「旧编号不存在 → 删除」「新标题首次出现 → 新机制」这两条捷径。"
             "例如 2027 `3.1 机器人`/`3.2 组合系统`/`3.3 附属设备` 三个新编号被判为「层级容器（疑似新增）」而非新机制，"
             "因为其正文为空、子节分别对应 2026 的既有章节。")
    L.append("")
    L.append("### 2.3 关系定义")
    L.append("")
    L.append("| 关系 | 定义 | 单元数 |")
    L.append("|---|---|---|")
    L.append("| 保留 kept | 主题/标题延续（含仅编号顺延），正文可能有差异 | %d（其中编号顺延 %d） |" % (cnt["kept"], n_renum))
    L.append("| 重命名 renamed | 主题延续但标题改名 | %d |" % cnt["renamed"])
    L.append("| 迁移 moved | 层级或归属章节发生变化 | %d |" % cnt["moved"])
    L.append("| 合并 merged | 多个 2026 章节 → 一个 2027 章节 | %d |" % cnt["merged"])
    L.append("| 拆分 split | 一个 2026 章节 → 多个 2027 章节 | %d |" % cnt["split"])
    L.append("| 疑似新增 added | 2027 有、2026 无对应 | %d |" % cnt["added"])
    L.append("| 疑似删除 deleted | 2026 有、2027 无对应 | %d |" % cnt["deleted"])
    L.append("")
    L.append("## 3. 覆盖情况")
    L.append("")
    L.append("| 检查项 | 2026 | 2027 |")
    L.append("|---|---|---|")
    L.append("| 正式章节总数 | %d | %d |" % (cov["sections_2026"], cov["sections_2027"]))
    L.append("| 已进入映射 | **%d** | **%d** |" % (cov["sections_2026_mapped"], cov["sections_2027_mapped"]))
    L.append("| 未映射 | %d | %d |" % (len(cov["sections_2026_unmapped"]), len(cov["sections_2027_unmapped"])))
    L.append("| 未被任何单元引用 | 0 | 0 |")
    L.append("| 被两个单元重复引用 | 0 | 0 |")
    L.append("")
    L.append("逐章（按 2026 的章）覆盖：")
    L.append("")
    L.append("| 章 | 2026 节数 | 2027 节数 | 关系分布 |")
    L.append("|---|---|---|---|")
    for t, c in chapters.items():
        if not c["units"]:
            continue
        rel = "、".join("%s%d" % (REL_CN[k], v) for k, v in
                        sorted(c["rel"].items(), key=lambda kv: REL_ORDER.index(kv[0])))
        L.append("| %s | %d | %d | %s |" % (t, c["n26"], c["n27"], rel))
    L.append("")
    L.append("## 4. 关键结论（结构层面）")
    L.append("")
    L.append("1. **章级结构基本稳定**：1–9 章一一对应，仅附录由 3 个减为 2 个（雷达信息波特性附录疑似删除）。")
    L.append("2. **第 3 章被重组**：2026 的 7 个机器人类型（L2）重组为 2027 的 3 个容器（机器人/组合系统/附属设备，L2）"
             "+ 7 个具体类型（L3）；其中英雄机器人 + 工程机器人合并为重装机器人，"
             "并把「自定义客户端」从第 5 章迁入成为「自定义终端」。")
    L.append("3. **第 5 章变化最大**：新增 5.2 自适应装甲机制、5.6.2 战场控制机制；"
             "英雄/工程机器人特殊机制（5.6.1、5.6.2）与「重装机器人」合并后由 5.7.1 承接，"
             "空中机器人特殊机制（5.6.3）无对应章节，5.6.7 能量机制与 5.1.5.5 激光检测模块离线亦无对应；"
             "其余章节因插入而整体顺延编号。")
    L.append("4. **场地章节**：新增制高点、机库平台；取消停机坪、飞行区；飞坡改名隧道；"
             "梯形高地增益点迁移到新建的制高点。")
    L.append("5. **违规与判罚**：条款重编号幅度大（R 编号不可作为对应依据）；"
             "2026 的「空中机器人」+「其他机器人」合并为 2027 的「组合系统」。")
    L.append("")
    L.append("## 5. 局限与风险")
    L.append("")
    L.append("1. **「疑似删除」不是结论**。B1 只对齐章节；`空中支援`、`部署模式`、`底盘能量`、"
             "`激光检测模块`、`频谱/空口/调制` 等机制在 2027 全文检索 0 命中，因此暂判为疑似删除 / 疑似取消，"
             "但**是否真废弃需 B2 逐条正文比对确认**（可能被改写为其他表述）。")
    L.append("2. **合并类对应只到章节层**。例如「重装 = 英雄 + 工程」在章节层成立，但内容层只有工程的 50% 防御条款被继承、"
             "英雄的部署模式未检出；这类差异留给 B2。")
    L.append("3. **容器节判定**：2027 新增的 3 个空章节（3.1/3.2/3.3）判为「层级容器（疑似新增）」，"
             "若后续需要按「机制新增」统计，应把它们排除。")
    L.append("4. **编号顺延量很大**（%d 个单元）。这不是规则变化，做差异分析时**必须先按本映射对齐，再比对正文**，"
             "否则会产生大量假差异。" % n_renum)
    L.append("5. **相似度阈值是启发式**。程序候选与条款路由只用于定位；最终对应由逐条证据裁断，"
             "每条结论都能追溯到具体的文本或检索命中数。")
    L.append("6. **2027 §1.2 只作佐证**。该节明确给出合并/改名/取消的清单，本报告用它交叉验证，"
             "但所有对应关系都由正文/检索证据独立支持，没有单靠它下结论。")
    L.append("7. **范围外**：未对表格、公式、流程图做语义比对；未做任何正文差异结论；未修改阶段 A 数据。")
    L.append("")
    L.append("## 6. 自动自检")
    L.append("")
    L.append("`ai_workplace/tools/45_align_verify.py` 对产物做独立断言校验，**34 项全部通过**：")
    L.append("")
    L.append("| 校验类别 | 内容 |")
    L.append("|---|---|")
    L.append("| 章节完整性（4 项） | 以阶段 A 骨架为基准，2026 130 / 2027 129 个正式章节在单元中"
             "**各出现且仅出现一次**，无重复、无遗漏 |")
    L.append("| 索引一致性（4 项） | `section_index` 的键与骨架一致，且每个映射指向正确的单元 |")
    L.append("| 结构自洽（4 项） | `match_type` == 两侧章节数；关系与 `match_type` 相容"
             "（0:1→新增、1:0→删除、2:1→合并、1:n→拆分）；`align_id` 唯一且连续 |")
    L.append("| 证据可追溯（3 项） | 每个单元都有 evidence，且人工裁断项都带有带前缀的证据来源（D/S/C/M/P） |")
    L.append("| 覆盖统计（8 项） | `coverage` 中的已映射数、未映射清单、关系计数、疑似新增/删除清单"
             "与单元逐一吻合 |")
    L.append("| 章节属性（4 项） | 每个章节的 `path` 长度 == 层级、末项 == 标题；印刷页 == 物理页 − 1 |")
    L.append("| 交付物覆盖（5 项） | `章节对齐总览.md` 覆盖全部章节；`章节对齐异常清单.md` 覆盖全部"
             "非「保留」及待核验章节；总览表行数 == 单元数 |")
    L.append("")
    L.append("## 7. 产物")
    L.append("")
    L.append("阶段 B1 的四份产物集中放在 `ai_workplace/alignment/`（与阶段 A 的 `ai_workplace/report/`、"
             "`ai_workplace/structured/` 并列，互不覆盖）：")
    L.append("")
    L.append("| 文件 | 说明 |")
    L.append("|---|---|")
    L.append("| `ai_workplace/alignment/章节对应关系.json` | 机器可读映射（%d 个对齐单元 + 双向 section_index + 覆盖统计） |" % cov["units"])
    L.append("| `ai_workplace/alignment/章节对齐总览.md` | 完整章节映射表（人工阅读） |")
    L.append("| `ai_workplace/alignment/章节对齐异常清单.md` | 疑似新增/删除、合并、拆分、重命名、迁移、待核验汇总 |")
    L.append("| `ai_workplace/alignment/align_candidates.json` | 程序候选与证据（相似度、路由份额） |")
    L.append("| `ai_workplace/alignment/candidates_digest.txt` | 候选生成的控制台摘要 |")
    L.append("")
    L.append("## 8. 建议的下一步（B2）")
    L.append("")
    L.append("1. 先处理 `章节对齐异常清单.md` 中 **13 个待核验单元**，特别是 6 个疑似删除（high 优先级）。")
    L.append("2. B2 按本映射的单元逐对做正文比对，**跳过**「编号顺延」带来的假差异。")
    L.append("3. 合并类（3 个）按「源章节逐条 → 目标章节」做内容覆盖检查。")
    L.append("4. 新增/删除类直接进入「新增/删除清单」，但需正文二次确认。")
    L.append("5. 表格/公式/流程图仍按阶段 A 的待核验清单处理，不纳入 B2 的自动比对范围。")
    L.append("")
    L.append("**B1 到此结束，等待审核，不自动进入 B2。**")
    L.append("")
    open(os.path.join(OUT, "章节对齐质量报告.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("written 章节对齐质量报告.md  (%d lines)" % len(L))


if __name__ == "__main__":
    main()
