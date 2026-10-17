#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 3 -- readable Markdown view of the full-document JSONL.

Markdown is only a VIEW: every byte of original text lives in the JSONL, and the
renderer never drops text to satisfy a Markdown limitation.  Items that cannot
be represented faithfully (tables with unresolved merges, stacked fractions,
diagram labels, figures) are rendered with an explicit "待核验" marker plus the
record id, so a reader can jump back to the authoritative record.
"""
import os
import re
import json
import datetime
from collections import defaultdict

import struct_lib as L

MD_SPECIAL = "\\`*_[]<>|~"


def esc(text):
    out = []
    for ch in text:
        out.append("\\" + ch if ch in MD_SPECIAL else ch)
    s = "".join(out)
    # a line that starts with "1." / "#" etc. would be re-interpreted as a list
    m = re.match(r"^(\s*)(\d+)([.)])(\s)", s)
    if m:
        s = m.group(1) + m.group(2) + "\\" + m.group(3) + m.group(4) + s[m.end():]
    if s.startswith("#"):
        s = "\\" + s
    return s


def jump(rec):
    """Compact traceability suffix: physical page + record id."""
    return "`P%d` · `%s`" % (rec.get("physical_page"), rec["record_id"])


def md_cell(text):
    """Display-only cleanup for table cells: Wingdings bullets live in the
    Unicode private use area and render as boxes; map them the same way the
    text normalization does.  Nothing else is touched."""
    if text is None:
        return ""
    for k, v in L.PUA_MAP.items():
        text = text.replace(k, v)
    return text.replace("|", "\\|")


def render_table(rec, rendered_captions):
    out = []
    cap = rec.get("caption")
    tn = rec.get("table_no")
    if cap and cap in rendered_captions:
        head = "**表格 · %s**" % esc(tn or "")
    elif cap:
        head = "**%s**" % esc(cap)
    else:
        head = "**表格（无表题，可能是跨页续页）**"
    out.append("%s　%s" % (head, jump(rec)))
    if rec["coverage_check"]["data_loss_suspected"]:
        out.append("")
        out.append("> ⚠ **网格丢词告警**：%d 个词未进入 `find_tables()` 网格（已在 `source_text_lines` 保留，未做猜测填充）。"
                   % rec["coverage_check"]["missing_from_grid"])
    out.append("")
    # re-render the grid so PUA bullets are visible; cell text is unchanged
    grid = [[md_cell(c) for c in row] for row in rec["grid_raw"]]
    cols = max((len(r) for r in grid), default=0)
    if cols:
        padded = [list(r) + [""] * (cols - len(r)) for r in grid]
        out.append("| " + " | ".join(padded[0]) + " |")
        out.append("|" + "---|" * cols)
        for row in padded[1:]:
            out.append("| " + " | ".join(row) + " |")
    notes = ["%d 行 × %d 列" % (rec["extraction"]["rows"], rec["extraction"]["cols"]),
             "空白单元格 %d/%d（%.0f%%）" % (rec["extraction"]["blank_cells"],
                                      rec["extraction"]["cells"],
                                      100 * rec["extraction"]["blank_ratio"]),
             "合并单元格证据 %d 条（未应用）" % len(rec["merge_suspects"]),
             "原始文本行 %d 行" % rec["extraction"]["source_text_lines_inside_box"]]
    out.append("")
    out.append("> 表格：%s；**合并单元格待人工还原**，未做任何猜测填充。" % "；".join(notes))
    return "\n".join(out)


def render_record(rec, rendered_captions):
    kind = rec.get("block_kind", rec["record_type"])
    if kind == "heading":
        return None                                    # section heading comes from the skeleton
    if kind == "paragraph":
        return esc(rec["norm_text"])
    if kind == "table_caption":
        rendered_captions.add(rec["norm_text"])
        return "**%s**　%s" % (esc(rec["norm_text"]), jump(rec))
    if kind == "figure_caption":
        rendered_captions.add(rec["norm_text"])
        return "*%s*　%s" % (esc(rec["norm_text"]), jump(rec))
    if kind == "cover_text":
        return "> 封面文本层：%s　%s" % (esc(rec["norm_text"]), jump(rec))
    if kind == "index_entry":
        return "- %s　%s" % (esc(rec["norm_text"]), jump(rec))
    if kind == "figure_label_row":
        return "> 图例编号行：%s　%s" % (esc(rec["norm_text"]), jump(rec))
    if kind == "diagram_label":
        return "> 图示文字（待核验）：%s　%s" % (esc(rec["norm_text"]), jump(rec))
    if kind == "formula_fraction_part":
        return "> 公式片段（待核验，几何序≠数学读序）：`%s`　%s" % (esc(rec["norm_text"]), jump(rec))
    if kind == "formula_fraction":
        return ("> 分式（待核验）：分子 `%s` ／ 分母 `%s`；片段 %d 个，横线 bbox `%s`　%s"
                % (esc(rec["numerator_text"]), esc(rec["denominator_text"]),
                   len(rec["part_record_ids"]), rec["fraction_bar"], jump(rec)))
    if kind == "figure":
        ii = rec.get("image_info") or {}
        return ("> 🖼 图片：%s × %s px，显示尺寸 %s pt　%s"
                % (ii.get("width_px"), ii.get("height_px"), ii.get("box_pt"), jump(rec)))
    if kind == "inline_icon":
        return "> ▫ 内联图标：显示尺寸 %s pt（未做语义提取）　%s" % (
            (rec.get("image_info") or {}).get("box_pt"), jump(rec))
    if rec["record_type"] == "table":
        return render_table(rec, rendered_captions)
    return "> （未渲染的类型：%s）　%s" % (kind, jump(rec))


HEADING_CHAR = {1: 2, 2: 3, 3: 4, 4: 5, 0: 2}


def build_markdown(doc_id):
    year = doc_id.replace("RMUC", "")
    skel = L.load_skeleton(doc_id)
    cfg = L.DOCS[doc_id]
    jsonl = os.path.join(L.STRUCT, "%s_结构化.jsonl" % year)
    recs = [json.loads(l) for l in open(jsonl, encoding="utf-8")]

    by_section = defaultdict(list)
    for r in recs:
        by_section[r["section_index"]].append(r)

    doc = skel["doc"]
    out = []
    out.append("# RMUC %s 结构化全文（%s）" % (year, cfg["version"]))
    out.append("")
    out.append("> **这是 Markdown 视图，不是事实主数据。** 事实主数据是同目录下的 "
               "`%s_结构化.jsonl`；Markdown 只做排版，不因为展示限制丢弃任何原文。"
               % year)
    out.append("> 表格合并单元格、上下分式、流程图文字、图片内容均**未做自动语义还原**，"
               "相关条目已就地标注“待核验”并附记录 ID。")
    out.append("")
    out.append("| 项目 | 值 |")
    out.append("|---|---|")
    out.append("| 源文件 | `%s` |" % doc["source_file"])
    out.append("| SHA256 | `%s` |" % doc["sha256"])
    out.append("| 版本 | %s |" % cfg["version"])
    out.append("| 物理页数 / 印刷页码 | %d / 1–%d（印刷 = 物理 − 1） |"
               % (doc["page_count"], doc["page_count"] - 1))
    out.append("| 区域 | %d 个（%d 书签章节 + %d 合成区域） |"
               % (doc["regions_total"], doc["outline_entries"], len(doc["synthetic_regions"])))
    out.append("| 记录 | %d 条 |" % len(recs))
    out.append("| 生成 | %s · PyMuPDF %s |" % (datetime.datetime.now().isoformat(timespec="seconds"),
                                               __import__("pymupdf").__version__))
    out.append("")
    out.append("## 章节索引")
    out.append("")
    out.append("| 章节号 | 标题 | 层级 | 物理页 | 印刷页 | 记录 |")
    out.append("|---|---|---|---|---|---|")
    for s in skel["sections"]:
        n = len(by_section.get(s["section_id"], []))
        if n == 0:
            continue
        pages = s["pages_with_content"] or [s["start_physical_page"]]
        out.append("| %s | %s | L%d | %s | %s | %d |"
                   % (s["section_no"] or "—", esc(s["title"]), s["level"],
                      ("%d" % pages[0]) if len(pages) == 1 else ("%d–%d" % (pages[0], pages[-1])),
                      ("%d" % (pages[0] - 1)) if len(pages) == 1
                      else ("%d–%d" % (pages[0] - 1, pages[-1] - 1)), n))
    out.append("")
    out.append("---")
    out.append("")

    for s in skel["sections"]:
        srecs = by_section.get(s["section_id"], [])
        if not srecs:
            continue
        depth = HEADING_CHAR.get(s["level"], 3)
        label = s["title"] if s["section_no"] else s["title"]
        pages = s["pages_with_content"] or [s["start_physical_page"]]
        pr = (("%d" % pages[0]) if len(pages) == 1 else ("%d–%d" % (pages[0], pages[-1])))
        prn = (("%d" % (pages[0] - 1)) if len(pages) == 1
               else ("%d–%d" % (pages[0] - 1, pages[-1] - 1)))
        tag = ""
        if s["region_type"] != "section":
            tag = "（非规则正文区域）"
        out.append("%s %s%s" % ("#" * depth, esc(label), tag))
        out.append("")
        out.append("<sub>物理页 %s ／ 印刷页 %s ／ 层级 L%d ／ 路径 %s ／ 记录 %d 条</sub>"
                   % (pr, prn, s["level"], esc(" › ".join(s["path"])), len(srecs)))
        out.append("")
        if s["region_type"] == "front_matter":
            out.append("> 封面为整页矢量图，文本层乱码（见预检查 6.1/6.2）；以下为原始乱码"
                       "文本，**不可作为规则正文**。")
            out.append("")
        rendered_captions = set()
        for r in srecs:
            md = render_record(r, rendered_captions)
            if md:
                out.append(md)
                out.append("")
        out.append("")

    # ---- review index ----
    out.append("---")
    out.append("")
    out.append("## 附：待核验索引")
    out.append("")
    groups = defaultdict(list)
    for r in recs:
        if not r.get("needs_review"):
            continue
        groups[r.get("block_kind", r["record_type"])].append(r)
    if not groups:
        out.append("（无）")
    for kind, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        out.append("### %s（%d 条）" % (kind, len(rs)))
        out.append("")
        for r in rs:
            out.append("- `%s` · 物理页 %d · %s · %s"
                       % (r["record_id"], r["physical_page"],
                          r["section"]["section_no"] or r["section"]["title"],
                          esc((r.get("norm_text") or r.get("caption") or "")[:60])))
        out.append("")

    return "\n".join(out)


def main():
    for doc_id in L.DOCS:
        year = doc_id.replace("RMUC", "")
        print("== markdown", doc_id, flush=True)
        md = build_markdown(doc_id)
        out = os.path.join(L.STRUCT, "%s_结构化.md" % year)
        open(out, "w", encoding="utf-8").write(md)
        print("   %s %.1f KB, %d lines" % (out, os.path.getsize(out) / 1024, md.count("\n") + 1))


if __name__ == "__main__":
    main()
