#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 2 -- step 2: small-scale structuring trial (paragraph reconstruction).

The two official PDFs emit one *block per visual line*, so a logical paragraph
is spread over several blocks.  This script therefore rebuilds paragraphs from
line-level geometry, and allows a paragraph to continue onto the next page
(cross-page section case).  Every record keeps the exact source lines
(page + line bbox), so the record can be mapped back to the PDF and re-extracted.

Groups requested by the task: 普通正文 / 跨页章节 / 复杂表格 / 公式 / 同页多章节 / 流程图页.

Read-only.
"""
import os
import re
import json
import datetime
import statistics

import pymupdf

import struct_lib as L

os.makedirs(L.SAMPLES, exist_ok=True)

GROUPS_BY_DOC = {
    "RMUC2026": [
        ("body_text", ["1.2", "1.3"], "普通正文（项目符号 / URL / 同页多章节）"),
        ("cross_page", ["5.2.2"], "跨页章节（章节内容跨 2 个物理页）"),
        ("cross_page_paragraph", ["4.2.5"], "跨页段落（同一段落在页边界处续接）",
         dict(keep_only_cross_page=True)),
        ("tables", ["5.4.2"], "复杂表格（多级表头 / 合并单元格）"),
        ("formulas", ["5.5.2"], "公式（三角函数转速模型 / 分式）"),
        ("multi_section_page", ["6.4", "6.5", "6.6", "6.7", "6.8"], "同页多章节"),
        ("flowchart", ["5.1.3"], "流程图 + 变量（Q0/Q1/Q2）"),
    ],
    "RMUC2027": [
        ("body_text", ["1.3", "1.4"], "普通正文（项目符号 / URL / 同页多章节）"),
        ("cross_page", ["5.3.2"], "跨页章节（章节内容跨 2 个物理页）"),
        ("cross_page_paragraph", ["5.4.3"], "跨页段落（同一段落在页边界处续接）",
         dict(keep_only_cross_page=True)),
        ("tables", ["5.5.2"], "复杂表格（多级表头 / 合并单元格）"),
        ("formulas", ["5.6.3"], "公式（三角函数转速模型 / 分式）"),
        ("multi_section_page", ["6.4", "6.5", "6.6", "6.7", "6.8"], "同页多章节"),
        ("flowchart", ["5.1.3"], "流程图 + 变量（Q0/Q1/Q2）"),
    ],
}

CAP_TABLE = re.compile(r"^表\s?(\d{1,2})-(\d{1,2})")
CAP_FIGURE = re.compile(r"^图\s?(\d{1,2})-(\d{1,2})")
GREEK = re.compile(r"[ωλθπΔΣ∑√]")
FORMULA_HINT = re.compile(r"[=<>≤≥≠±√∑∏∫ωλθπΔ×÷^]|[A-Za-z]\s*[=<>≤≥]")
BULLETS = "\u2022\u25e6\uf06c\uf0d8"
SMALL_TEXT = 9.5      # diagram / table annotation type size (body text is 10.6)
MIN_TABLE_W, MIN_TABLE_H = 80.0, 40.0
MIN_TABLE_FILL = 0.10  # real tables fill 19%-54%; artwork grids fill ~3%


def is_bullet_only(text):
    t = L.normalize([text]).strip()
    return bool(t) and all(ch in BULLETS for ch in t)


def valid_table(t):
    """Reject boxes that find_tables() reports on artwork / flowchart pages.

    Real tables in these documents fill 19%-54% of their grid (merged cells make
    the rest blank).  Vector artwork can be reported as a huge, nearly empty
    grid (e.g. the cover page yields a 59x8 box with 3% fill), which would
    swallow the page text if accepted.
    """
    data = t.extract()
    nonempty = sum(1 for r in data for c in r if (c or "").strip())
    cells = max(1, t.row_count * t.col_count)
    w = t.bbox[2] - t.bbox[0]
    h = t.bbox[3] - t.bbox[1]
    fill = nonempty / cells
    return (t.row_count >= 2 and t.col_count >= 2
            and w >= MIN_TABLE_W and h >= MIN_TABLE_H
            and nonempty >= 4 and fill >= MIN_TABLE_FILL)


def fraction_zones(page, table_boxes=()):
    """Detect stacked (two-level) fractions: a short horizontal rule with a text
    line whose baseline sits just above it (numerator) and another just below it
    (denominator).  Rules that belong to a table grid are ignored."""
    lines = []
    for b in L.blocks_of(page)[0]:
        if b["kind"] != "text":
            continue
        for line in b["line_objs"]:
            txt = "".join(s["text"] for s in line["spans"])
            if not txt.strip():
                continue
            lines.append(dict(bbox=line["bbox"], text=txt,
                              baseline=max(s["origin"][1] for s in line["spans"])))
    zones = []
    for dr in page.get_drawings():
        r = dr["rect"]
        if not (3 <= r.width <= 260 and r.height <= 1.6):
            continue
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        if any(tb[0] - 2 <= cx <= tb[2] + 2 and tb[1] - 2 <= cy <= tb[3] + 2 for tb in table_boxes):
            continue                              # table grid rule, not a fraction bar
        above = [l for l in lines
                 if r.y0 - 12 <= l["baseline"] <= r.y0 - 1
                 and l["bbox"][2] > r.x0 - 2 and l["bbox"][0] < r.x1 + 2]
        below = [l for l in lines
                 if r.y1 + 1 <= l["baseline"] <= r.y1 + 16
                 and l["bbox"][2] > r.x0 - 2 and l["bbox"][0] < r.x1 + 2]
        if not (above and below):
            continue
        zones.append(dict(
            bar=[round(v, 2) for v in r],
            x0=r.x0 - 160, x1=r.x1 + 160,
            y0=min(l["baseline"] for l in above) - 14,
            y1=max(l["baseline"] for l in below) + 14,
            numerator=L.normalize([above[0]["text"]]),
            denominator=L.normalize([below[0]["text"]]),
        ))
    return zones


def in_fraction_zone(bbox, zones):
    cy = (bbox[1] + bbox[3]) / 2
    cx = (bbox[0] + bbox[2]) / 2
    for z in zones:
        if z["y0"] <= cy <= z["y1"] and z["x0"] <= cx <= z["x1"]:
            return True
    return False


# --------------------------------------------------------------------------- #
# line-level extraction
# --------------------------------------------------------------------------- #
def section_lines(doc, secs, section):
    """(page, line, block) items of one section in reading order; images are
    returned as (page, block) markers so figures are not lost."""
    out, images = [], []
    for pno in section["pages_with_content"]:
        for b in L.blocks_of(doc.load_page(pno - 1))[0]:
            s = L.find_section(secs, pno, b["bbox"][1])
            if s["section_id"] != section["section_id"]:
                continue
            if b["kind"] == "image":
                images.append((pno, b))
                continue
            for line in b["line_objs"]:
                text = "".join(sp["text"] for sp in line["spans"])
                if not text.strip():
                    continue
                size = max(sp["size"] for sp in line["spans"])
                base_span = max(line["spans"], key=lambda sp: sp["size"])
                base_origin = base_span["origin"][1]
                script_spans = []
                for sp in line["spans"]:
                    kind = "normal"
                    if sp["size"] < size * 0.8:
                        dy = sp["origin"][1] - base_origin
                        kind = ("subscript" if dy > 0.8
                                else ("superscript" if dy < -0.8 else "small"))
                    if kind != "normal":
                        script_spans.append(dict(text=sp["text"], size=round(sp["size"], 2),
                                                 base_size=round(size, 2),
                                                 baseline_dy=round(sp["origin"][1] - base_origin, 2),
                                                 script=kind))
                out.append(dict(
                    page=pno, block_bbox=b["bbox"], bbox=[round(v, 2) for v in line["bbox"]],
                    baseline=round(max(sp["origin"][1] for sp in line["spans"]), 2),
                    text=text, size=round(size, 2),
                    fonts=sorted({sp["font"].split("+")[-1] for sp in line["spans"]}),
                    origin=[round(sp["origin"][0], 2) for sp in line["spans"]],
                    script_spans=script_spans,
                ))
    # order by baseline (not bbox top): a Wingdings bullet box sits higher than
    # the text it introduces, and would otherwise be read after it
    out.sort(key=lambda x: (x["page"], x["baseline"], x["bbox"][0]))
    images.sort(key=lambda t: (t[0], t[1]["bbox"][1]))
    return out, images


def page_margins(lines_by_page):
    marg = {}
    for pno, lines in lines_by_page.items():
        body = [l for l in lines if 10.0 <= l["size"] <= 11.2]
        if not body:
            body = lines
        marg[pno] = (min(l["bbox"][0] for l in body), max(l["bbox"][2] for l in body))
    return marg


def estimate_pitch(lines):
    ys = sorted({round(l["bbox"][1], 2) for l in lines if 10.0 <= l["size"] <= 11.2})
    d = [round(b - a, 2) for a, b in zip(ys, ys[1:]) if 8 <= b - a <= 40]
    return statistics.median(d) if d else 19.7


# --------------------------------------------------------------------------- #
# paragraph assembly
# --------------------------------------------------------------------------- #
def assemble_paragraphs(lines, marg, pitch):
    """Group body lines into paragraphs.  Returns list of paragraphs, each a
    dict with lines / raw / bbox / pages."""
    paras = []
    cur = None
    for ln in lines:
        if cur is not None and _continues(cur["lines"][-1], ln, marg, pitch):
            cur["lines"].append(ln)
        else:
            cur = dict(lines=[ln])
            paras.append(cur)
    for p in paras:
        p["pages"] = sorted({l["page"] for l in p["lines"]})
        p["bbox"] = [min(l["bbox"][0] for l in p["lines"]), min(l["bbox"][1] for l in p["lines"]),
                     max(l["bbox"][2] for l in p["lines"]), max(l["bbox"][3] for l in p["lines"])]
        p["raw"] = "\n".join(l["text"] for l in p["lines"])
        p["norm"] = L.normalize([l["text"] for l in p["lines"]])
    return paras


def _continues(prev, cur, marg, pitch):
    # a Wingdings bullet on its own visual line always belongs to the text that
    # follows it; a bullet line itself always starts a new list item
    if is_bullet_only(prev["text"]):
        return not is_bullet_only(cur["text"])
    if is_bullet_only(cur["text"]):
        return False
    if abs(prev["size"] - cur["size"]) > 0.4:
        return False
    if prev["page"] == cur["page"]:
        dy = cur["baseline"] - prev["baseline"]
        if not (0.7 * pitch <= dy <= 1.6 * pitch):
            return False
        left, right = marg[prev["page"]]
        # a paragraph ends when its last visual line is clearly short
        if prev["bbox"][2] < right - 3.0 * prev["size"]:
            return False
        return True
    if cur["page"] == prev["page"] + 1:
        left, right = marg[prev["page"]]
        left2, _ = marg[cur["page"]]
        if prev["bbox"][2] < right - 3.0 * prev["size"]:
            return False                       # paragraph ended on the previous page
        if abs(cur["bbox"][0] - left2) > 2.5:
            return False                       # next page starts indented / centred
        return True
    return False


# --------------------------------------------------------------------------- #
# formula span layout (evidence only -- text is never rewritten)
# --------------------------------------------------------------------------- #
def formula_span_layout(doc, page_no, line_bbox):
    page = doc.load_page(page_no - 1)
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for line in b["lines"]:
            if [round(v, 2) for v in line["bbox"]] != line_bbox:
                continue
            base = max(sp["size"] for sp in line["spans"])
            base_span = max(line["spans"], key=lambda sp: sp["size"])
            base_origin = base_span["origin"][1]
            out = []
            for sp in line["spans"]:
                dy = round(sp["origin"][1] - base_origin, 2)
                script = "normal"
                if sp["size"] < base * 0.8:
                    script = "subscript" if dy > 0.8 else ("superscript" if dy < -0.8 else "small")
                out.append(dict(text=sp["text"], font=sp["font"].split("+")[-1],
                                size=round(sp["size"], 2),
                                origin=[round(v, 1) for v in sp["origin"]],
                                baseline_dy=dy, script=script))
            return out
    return []


# --------------------------------------------------------------------------- #
def table_records(doc, secs, section, meta):
    recs = []
    for pno in section["pages_with_content"]:
        page = doc.load_page(pno - 1)
        found = page.find_tables()
        if not found.tables:
            continue
        text_lines = []
        for b in L.blocks_of(page)[0]:
            if b["kind"] != "text":
                continue
            for line in b["line_objs"]:
                text_lines.append("".join(sp["text"] for sp in line["spans"]))
        for t_i, t in enumerate(found.tables):
            if not valid_table(t):
                continue
            if L.find_section(secs, pno, t.bbox[1])["section_id"] != section["section_id"]:
                continue
            caption = None
            for b in sorted([b for b in L.blocks_of(page)[0] if b["kind"] == "text"],
                            key=lambda b: -b["bbox"][1]):
                if b["bbox"][3] <= t.bbox[1] + 5:      # caption may slightly overlap
                    n = L.normalize(b["lines"])
                    if CAP_TABLE.match(n):
                        caption = n
                        break
            data = t.extract()
            cells = [[("" if c is None else c.replace("\n", " ")) for c in row] for row in data]
            n_rows, n_cols = len(cells), max((len(r) for r in cells), default=0)
            blank = sum(1 for r in cells for c in r if not c.strip())

            suspects = []
            for c in range(n_cols):
                run = 0
                for r in range(n_rows):
                    v = cells[r][c] if c < len(cells[r]) else ""
                    if not v.strip():
                        run += 1
                        continue
                    if run:
                        suspects.append(dict(kind="vertical", col=c,
                                             empty_rows=[r - run, r - 1],
                                             anchor_row=r,
                                             reason="该列在锚点行上方有连续空白，疑似纵向合并"))
                    run = 0
            for r in range(n_rows):
                run = 0
                for c in range(n_cols):
                    v = cells[r][c] if c < len(cells[r]) else ""
                    if not v.strip():
                        run += 1
                        continue
                    if run:
                        suspects.append(dict(kind="horizontal", row=r,
                                             empty_cols=[c - run, c - 1],
                                             anchor_col=c,
                                             reason="该行在锚点列左侧有连续空白，疑似横向合并"))
                    run = 0

            words = [w[4] for w in page.get_text("words")
                     if t.bbox[0] - 1 <= (w[0] + w[2]) / 2 <= t.bbox[2] + 1
                     and t.bbox[1] - 1 <= (w[1] + w[3]) / 2 <= t.bbox[3] + 1]
            cell_text = L.norm_ws("".join("".join(r) for r in cells))
            missing = [w for w in words if L.norm_ws(w) and L.norm_ws(w) not in cell_text]

            # how many raw text lines fall inside this box, and their exact text:
            # they are NOT emitted as separate records (grid_raw carries them),
            # but they are kept here so that no source data can be lost even when
            # find_tables() mis-assigns a cell
            inside_lines = []
            for b in L.blocks_of(page)[0]:
                if b["kind"] != "text":
                    continue
                for line in b["line_objs"]:
                    cy = (line["bbox"][1] + line["bbox"][3]) / 2
                    cx = (line["bbox"][0] + line["bbox"][2]) / 2
                    if (t.bbox[0] - 1 <= cx <= t.bbox[2] + 1
                            and t.bbox[1] - 1 <= cy <= t.bbox[3] + 1):
                        inside_lines.append(dict(
                            page=pno, bbox=[round(v, 2) for v in line["bbox"]],
                            text="".join(sp["text"] for sp in line["spans"])))
            source_text = L.norm_ws("".join(l["text"] for l in inside_lines))
            missing_from_source = [w for w in words
                                   if L.norm_ws(w) and L.norm_ws(w) not in source_text]

            recs.append(dict(
                record_id="%s:p%d:t%d" % (meta["prefix"], pno, t_i),
                record_type="table", sample=meta["sample"],
                doc_id=meta["doc_id"], version=meta["version"],
                source_file=meta["source_file"], sha256=meta["sha256"],
                section=meta["section_brief"],
                physical_page=pno, printed_page=pno + L.PRINTED_OFFSET,
                bbox=[round(v, 2) for v in t.bbox],
                table_no=(CAP_TABLE.match(caption).group(0).replace(" ", "") if caption else None),
                caption=caption,
                extraction=dict(engine="PyMuPDF %s find_tables()" % pymupdf.__version__,
                                strategy="graphics-lines",
                                rows=n_rows, cols=n_cols, cells=n_rows * n_cols,
                                blank_cells=blank, blank_ratio=round(blank / max(1, n_rows * n_cols), 3),
                                source_text_lines_inside_box=len(inside_lines)),
                source_text_lines=inside_lines,
                grid_raw=cells,
                grid_markdown=markdown_table(cells),
                merge_status="unresolved",
                merge_suspects=suspects,
                merge_suspects_applied=False,
                needs_review=True,
                review_note="合并单元格未做任何推断或填充；grid_raw 为 find_tables() 原始输出，"
                            "空白单元格原样保留；merge_suspects 仅记录证据，未改写任何单元格。",
                coverage_check=dict(
                    words_in_box=len(words),
                    missing_words=missing,
                    missing_from_grid=len(missing),
                    data_loss_suspected=bool(missing),
                    missing_also_from_source_lines=missing_from_source,
                    raw_source_lines_preserved=True,
                    note="missing_words 表示 find_tables() 网格里找不到、但页面文本层里存在的词；"
                         "这些词已完整保存在 source_text_lines 中，未做任何填充或猜测。"),
            ))
    return recs


def markdown_table(cells):
    if not cells:
        return ""
    cols = max(len(r) for r in cells)
    rows = [[(c if i < len(r) else "").replace("|", "\\|")
             for i, c in enumerate(list(r) + [""] * (cols - len(r)))] for r in cells]
    return "\n".join(["| " + " | ".join(rows[0]) + " |", "|" + "---|" * cols] +
                     ["| " + " | ".join(r) + " |" for r in rows[1:]])


# --------------------------------------------------------------------------- #
def build_doc(doc_id, groups):
    cfg = L.DOCS[doc_id]
    skel = L.load_skeleton(doc_id)
    secs = skel["sections"]
    doc = pymupdf.open(L.doc_path(doc_id))
    index, preview = [], {}

    for group in groups:
        gname, sec_nos, desc = group[0], group[1], group[2]
        gopt = group[3] if len(group) > 3 else {}
        recs = []
        for no in sec_nos:
            section = L.section_by_no(skel, no)
            brief = dict(section_id=section["section_id"], section_no=section["section_no"],
                         title=section["title"], name=section["name"], level=section["level"],
                         path=section["path"])
            meta = dict(sample=gname, doc_id=doc_id, version=cfg["version"],
                        source_file=cfg["source_file"], sha256=skel["doc"]["sha256"],
                        section_brief=brief, prefix="%s:%s" % (doc_id, no))

            lines, images = section_lines(doc, secs, section)
            # ---- classify lines that must NOT be merged into paragraphs ----
            table_boxes = []
            for pno in section["pages_with_content"]:
                for t in doc.load_page(pno - 1).find_tables().tables:
                    if valid_table(t):
                        table_boxes.append((pno, t.bbox))
            heading_keys = [(s["start_physical_page"], s["start_y"]) for s in secs]
            zones_by_page = {}
            for p in section["pages_with_content"]:
                pg = doc.load_page(p - 1)
                zones_by_page[p] = fraction_zones(
                    pg, [tb for tp, tb in table_boxes if tp == p])

            def in_table(pno, bb):
                cy = (bb[1] + bb[3]) / 2
                cx = (bb[0] + bb[2]) / 2
                return any(p == pno and tb[1] - 1 <= cy <= tb[3] + 1 and tb[0] - 1 <= cx <= tb[2] + 1
                           for p, tb in table_boxes)

            standalone, body = [], []
            for ln in lines:
                n = L.normalize([ln["text"]])
                if (ln["size"] >= 14.5
                        and any(abs(ln["bbox"][1] - k[1]) < 1.0 and ln["page"] == k[0]
                                for k in heading_keys)):
                    standalone.append(("heading", ln))
                elif CAP_TABLE.match(n):
                    standalone.append(("table_caption", ln))
                elif CAP_FIGURE.match(n):
                    standalone.append(("figure_caption", ln))
                elif in_table(ln["page"], ln["bbox"]):
                    continue                       # fully represented by grid_raw
                elif in_fraction_zone(ln["bbox"], zones_by_page.get(ln["page"], [])):
                    standalone.append(("formula_fraction_part", ln))
                elif ln["size"] < SMALL_TEXT:
                    standalone.append(("diagram_label", ln))
                else:
                    body.append(ln)

            by_page = {}
            for ln in body:
                by_page.setdefault(ln["page"], []).append(ln)
            marg = page_margins(by_page)
            pitch = estimate_pitch(body)
            paras = assemble_paragraphs(body, marg, pitch)

            # ---- build records: standalone lines + paragraphs + figures + tables
            items = []
            for kind, ln in standalone:
                items.append(("line", kind, ln))
            for p in paras:
                items.append(("para", "paragraph", p))
            for pno, b in images:
                items.append(("image", "figure", (pno, b)))

            items.sort(key=lambda it: (it[2]["page"] if it[0] == "line" else
                                       (it[2]["lines"][0]["page"] if it[0] == "para" else it[2][0]),
                                       it[2]["bbox"][1] if it[0] != "image" else it[2][1]["bbox"][1]))
            for k, it in enumerate(items):
                kind = it[0]
                if kind == "image":
                    pno, b = it[2]
                    recs.append(dict(
                        record_id="%s:p%03d:i%03d" % (meta["prefix"], pno, k),
                        record_type="figure", sample=gname, doc_id=doc_id, version=cfg["version"],
                        source_file=cfg["source_file"], sha256=skel["doc"]["sha256"],
                        section=brief, physical_page=pno, printed_page=pno + L.PRINTED_OFFSET,
                        bbox=b["bbox"], block_kind="figure", raw_text="", norm_text="",
                        extraction=dict(engine="PyMuPDF %s get_text('dict')" % pymupdf.__version__,
                                        block_type="image"),
                        flags=dict(semantic_content_extracted=False), needs_review=True,
                        review_note="图片内容未做任何语义提取；仅记录位置，供人工或后续图像处理使用。"))
                    continue
                bk = it[1]
                if kind == "line":
                    ln = it[2]
                    raw = ln["text"]
                    n = L.normalize([raw])
                    rec = dict(
                        record_id="%s:p%03d:s%03d" % (meta["prefix"], ln["page"], k),
                        record_type="block", sample=gname, doc_id=doc_id, version=cfg["version"],
                        source_file=cfg["source_file"], sha256=skel["doc"]["sha256"],
                        section=brief, physical_page=ln["page"],
                        printed_page=ln["page"] + L.PRINTED_OFFSET, bbox=ln["bbox"],
                        block_kind=bk, raw_text=raw, norm_text=n,
                        source_lines=[dict(page=ln["page"], bbox=ln["bbox"], text=raw)],
                        line_count=1,
                        normalization=dict(rules=["join_visual_linebreaks", "map_pua_bullets",
                                                  "collapse_whitespace"],
                                           chars_preserved=L.preserved(raw, n)),
                        extraction=dict(engine="PyMuPDF %s get_text('dict')" % pymupdf.__version__,
                                        fonts=ln["fonts"], max_font_size=ln["size"]),
                        flags=line_flags(bk, n, ln["fonts"], ln["script_spans"]),
                    )
                    if ln["script_spans"]:
                        rec["script_spans"] = ln["script_spans"]
                    if rec["flags"]["contains_formula"]:
                        rec["formula_span_layout"] = formula_span_layout(doc, ln["page"], ln["bbox"])
                    if bk == "diagram_label":
                        rec["needs_review"] = True
                        rec["review_note"] = ("图形/图例文字（字号 %.1f pt，小于正文 10.6 pt）："
                                              "未做任何语义推断，仅供人工判断其在流程图中的作用。" % ln["size"])
                    if bk == "formula_fraction_part":
                        rec["needs_review"] = True
                        rec["review_note"] = ("检测到分式横线（stacked fraction）：该文本行是分式的分子/分母/"
                                              "同行片段之一，几何顺序与数学读序不一定一致，需人工按渲染页核对。")
                    recs.append(rec)
                else:
                    p = it[2]
                    first, last = p["lines"][0], p["lines"][-1]
                    n = p["norm"]
                    all_scripts = [s for l in p["lines"] for s in l["script_spans"]]
                    rec = dict(
                        record_id="%s:p%03d:p%03d" % (meta["prefix"], first["page"], k),
                        record_type="block", sample=gname, doc_id=doc_id, version=cfg["version"],
                        source_file=cfg["source_file"], sha256=skel["doc"]["sha256"],
                        section=brief, physical_page=first["page"],
                        printed_page=first["page"] + L.PRINTED_OFFSET,
                        physical_pages=p["pages"],
                        bbox=p["bbox"], block_kind=bk, raw_text=p["raw"], norm_text=n,
                        source_lines=[dict(page=l["page"], bbox=l["bbox"], text=l["text"])
                                      for l in p["lines"]],
                        line_count=len(p["lines"]),
                        cross_page=len(p["pages"]) > 1,
                        normalization=dict(rules=["join_visual_linebreaks", "map_pua_bullets",
                                                  "collapse_whitespace"],
                                           chars_preserved=L.preserved(p["raw"], n)),
                        extraction=dict(engine="PyMuPDF %s get_text('dict')" % pymupdf.__version__,
                                        fonts=sorted({f for l in p["lines"] for f in l["fonts"]}),
                                        max_font_size=max(l["size"] for l in p["lines"]),
                                        assembled_from="visual lines merged by geometry"),
                        flags=line_flags(bk, n, sorted({f for l in p["lines"] for f in l["fonts"]}),
                                         all_scripts),
                    )
                    if all_scripts:
                        rec["script_spans"] = all_scripts
                    if rec["flags"]["contains_formula"] and len(p["lines"]) <= 4:
                        rec["formula_span_layout"] = [
                            formula_span_layout(doc, l["page"], l["bbox"]) for l in p["lines"]]
                    if rec["flags"]["starts_with_figure_marker"]:
                        rec["needs_review"] = True
                        rec["review_note"] = ("该段落首行以图形标注编号 [n] 开头，可能是图例行被段落合并规则"
                                              "并入正文，需人工确认是否应在图注处断开。")
                    recs.append(rec)

            recs += table_records(doc, secs, section, meta)

            # ---- one record per detected stacked fraction (evidence envelope) --
            for pno, zones in sorted(zones_by_page.items()):
                for j, z in enumerate(zones):
                    inside = [r["record_id"] for r in recs
                              if r["physical_page"] == pno
                              and r.get("block_kind") == "formula_fraction_part"
                              and z["y0"] <= (r["bbox"][1] + r["bbox"][3]) / 2 <= z["y1"]]
                    if not inside:
                        continue
                    recs.append(dict(
                        record_id="%s:p%d:f%d" % (meta["prefix"], pno, j),
                        record_type="formula_fraction", sample=gname,
                        doc_id=doc_id, version=cfg["version"],
                        source_file=cfg["source_file"], sha256=skel["doc"]["sha256"],
                        section=brief, physical_page=pno,
                        printed_page=pno + L.PRINTED_OFFSET,
                        bbox=[round(z["x0"], 2), round(z["y0"], 2),
                              round(z["x1"], 2), round(z["y1"], 2)],
                        block_kind="formula_fraction",
                        fraction_bar=z["bar"],
                        numerator_text=z["numerator"], denominator_text=z["denominator"],
                        part_record_ids=inside,
                        raw_text="", norm_text="",
                        needs_review=True,
                        review_note="分式由分子/分母/同行片段多个独立文本对象拼成，横线为矢量绘制；"
                                    "本记录的 part_record_ids 保留全部原始片段与坐标，未拼装或改写公式。",
                    ))

            if gopt.get("keep_only_cross_page"):
                # focused demo: keep only the paragraphs that really continue
                # across a page boundary, plus the section heading for context
                kept = [r for r in recs if r.get("cross_page")]
                heads = [r for r in recs if r.get("block_kind") == "heading"]
                recs = sorted(heads + kept,
                              key=lambda r: (r["physical_page"], r["bbox"][1]))

        recs.sort(key=lambda r: (r["physical_page"], r["bbox"][1], r["record_type"] != "table"))
        out = os.path.join(L.SAMPLES, "%s_%s.jsonl" % (doc_id, gname))
        with open(out, "w", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

        kinds = {}
        for r in recs:
            k = r.get("block_kind", r["record_type"])
            kinds[k] = kinds.get(k, 0) + 1
        pages = sorted({p for r in recs for p in r.get("physical_pages", [r["physical_page"]])})
        index.append(dict(doc_id=doc_id, sample=gname, description=desc,
                          sections=sec_nos,
                          section_titles=[L.section_by_no(skel, n)["title"] for n in sec_nos],
                          file=os.path.relpath(out, L.ROOT).replace("\\", "/"),
                          records=len(recs), block_kinds=kinds,
                          paragraphs=sum(1 for r in recs if r.get("block_kind") == "paragraph"),
                          cross_page_records=sum(1 for r in recs if r.get("cross_page")),
                          tables=sum(1 for r in recs if r["record_type"] == "table"),
                          physical_pages=pages, printed_pages=[p - 1 for p in pages],
                          chars=sum(len(r.get("raw_text") or "") for r in recs)))
        preview[gname] = recs
        print("   %-20s %4d records  pages %s" % (gname, len(recs), pages), flush=True)
    doc.close()
    return index, preview


def line_flags(kind, norm, fonts, script_spans=()):
    return dict(is_heading=kind == "heading",
                is_list_item=norm[:1] in ("\u2022", "\u25e6"),
                is_caption=kind in ("table_caption", "figure_caption"),
                inside_table=kind == "table_text",
                uses_cambria_math=any("CambriaMath" in f for f in fonts),
                script_span_count=len(script_spans),
                starts_with_figure_marker=bool(re.match(r"^\[\d+\]", norm)),
                contains_formula=bool(script_spans) or (
                    kind == "paragraph" and bool(FORMULA_HINT.search(norm) and GREEK.search(norm))),
                contains_digit=bool(re.search(r"\d", norm)),
                contains_greek=bool(GREEK.search(norm)),
                contains_compare=bool(re.search(r"[<>≤≥≠]", norm)),
                contains_unit=bool(re.search(r"(mm|m/s|rad/s|%|℃|Hz|kW|W|J|°|s)", norm)))


def main():
    all_index, previews, groups_used = [], {}, {}
    for doc_id in L.DOCS:
        print("== samples for", doc_id, flush=True)
        groups = GROUPS_BY_DOC[doc_id]
        index, preview = build_doc(doc_id, groups)
        all_index += index
        previews[doc_id] = preview
        groups_used[doc_id] = groups

    json.dump(dict(generated=datetime.datetime.now().isoformat(timespec="seconds"),
                   normalization_rules=["join_visual_linebreaks", "map_pua_bullets",
                                        "collapse_whitespace"],
                   normalization_guarantee="规范化只改动空白与 Wingdings 私用区符号；"
                                           "数值、单位、公式、条件表达逐字符保持不变（由逐记录字符合并校验断言）。",
                   samples=all_index),
              open(os.path.join(L.STRUCT, "samples_index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    for doc_id, preview in previews.items():
        lines = ["# %s 结构化样本预览" % doc_id, "",
                 "> 由 `21_samples.py` 生成；完整字段见同名 `.jsonl`。", ""]
        for group in groups_used[doc_id]:
            gname, sec_nos, desc = group[0], group[1], group[2]
            recs = preview.get(gname, [])
            lines += ["## %s — %s" % (gname, desc), "",
                      "章节：" + "、".join(sec_nos), "",
                      "| 物理页 | 类型 | 行数 | 规范化文本（截断） |", "|---|---|---|---|"]
            for r in recs:
                txt = (r.get("norm_text") or r.get("caption") or "").replace("\n", " ").replace("|", "\\|")
                lines.append("| %d | %s | %s | %s |"
                             % (r["physical_page"], r.get("block_kind", r["record_type"]),
                                r.get("line_count", "-"), txt[:100]))
            lines.append("")
        open(os.path.join(L.SAMPLES, "%s_preview.md" % doc_id), "w",
             encoding="utf-8").write("\n".join(lines))
    print("written samples_index.json + previews")


if __name__ == "__main__":
    main()
