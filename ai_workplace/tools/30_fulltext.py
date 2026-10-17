#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 3 -- full-document structuring.

One pass per page; every text line / table / image is assigned to exactly one
region of the skeleton built in task 2, then records are emitted in section
order (never "one page = one section").

The classification and record-building rules are **reused from 21_samples.py**
(the code that passed the task-2 validation) so the JSONL schema is identical.

Read-only on the source PDFs.
"""
import os
import re
import json
import importlib.util
from collections import defaultdict

import pymupdf

import struct_lib as L


def _load_samples_module():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "21_samples.py")
    spec = importlib.util.spec_from_file_location("samples21", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S = _load_samples_module()

HEADING_MIN_SIZE = 14.5


def _line_dict(pno, line):
    text = "".join(sp["text"] for sp in line["spans"])
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
    return dict(page=pno, bbox=[round(v, 2) for v in line["bbox"]],
                baseline=round(max(sp["origin"][1] for sp in line["spans"]), 2),
                text=text, size=round(size, 2),
                fonts=sorted({sp["font"].split("+")[-1] for sp in line["spans"]}),
                script_spans=script_spans)


def scan_document(doc, secs):
    """Single pass: assign every line / table / image to a region."""
    starts_by_page = defaultdict(list)
    region_of = {}
    for s in secs:
        starts_by_page[s["start_physical_page"]].append(s["start_y"])
        region_of[s["section_id"]] = s["region_type"]

    lines_by_sec = defaultdict(list)
    images_by_sec = defaultdict(list)
    table_sections = set()
    pages_with_tables = set()
    stats = dict(pages=doc.page_count, content_blocks=0, running_blocks=0,
                 text_lines=0, lines_in_tables=0, lines_kept=0,
                 image_blocks=0, inline_icons=0, valid_tables=0,
                 rejected_table_boxes=0, fraction_zones=0,
                 multi_line_heading_blocks=0, heading_lines=0,
                 index_entry_lines=0, cover_text_lines=0)

    for pno in range(1, doc.page_count + 1):
        page = doc.load_page(pno - 1)
        content, running = L.blocks_of(page)
        stats["content_blocks"] += len(content)
        stats["running_blocks"] += len(running)

        # the cover is pure artwork: its "tables" are drawing grids, and the text
        # layer is the garbled cover text handled by the pre-check
        cover_page = (L.find_section(secs, pno, 0.0)["region_type"] == "front_matter"
                      and pno == 1)
        raw_tables = [] if cover_page else page.find_tables().tables
        valid = [t for t in raw_tables if S.valid_table(t)]
        stats["rejected_table_boxes"] += len(raw_tables) - len(valid)
        stats["valid_tables"] += len(valid)
        if valid:
            pages_with_tables.add(pno)
        boxes = [(pno, t.bbox) for t in valid]
        for t in valid:
            sid = L.find_section(secs, pno, t.bbox[1])["section_id"]
            table_sections.add(sid)

        zones = S.fraction_zones(page, [t.bbox for t in valid])
        stats["fraction_zones"] += len(zones)

        infos = [dict(bbox=list(i["bbox"]), width=i.get("width"), height=i.get("height"),
                      size=i.get("size"), colorspace=i.get("cs-name"), xres=i.get("xres"),
                      yres=i.get("yres"), bpc=i.get("bpc"), digest=i.get("digest"))
                 for i in page.get_image_info()]

        def match_info(bb):
            best, bestov = None, 0.0
            for inf in infos:
                x0 = max(bb[0], inf["bbox"][0]); y0 = max(bb[1], inf["bbox"][1])
                x1 = min(bb[2], inf["bbox"][2]); y1 = min(bb[3], inf["bbox"][3])
                if x1 <= x0 or y1 <= y0:
                    continue
                ov = (x1 - x0) * (y1 - y0)
                area = max(1.0, (bb[2] - bb[0]) * (bb[3] - bb[1]))
                if ov / area > bestov:
                    best, bestov = inf, ov / area
            return best if bestov >= 0.5 else None

        for b in content:
            if b["kind"] == "image":
                stats["image_blocks"] += 1
                sid = L.find_section(secs, pno, b["bbox"][1])["section_id"]
                w = b["bbox"][2] - b["bbox"][0]
                h = b["bbox"][3] - b["bbox"][1]
                inline = (w * h < 3000) or max(w, h) < 60
                if inline:
                    stats["inline_icons"] += 1
                images_by_sec[sid].append((pno, b, dict(
                    image_class="inline_icon" if inline else "figure",
                    width_px=(match_info(b["bbox"]) or {}).get("width"),
                    height_px=(match_info(b["bbox"]) or {}).get("height"),
                    colorspace=(match_info(b["bbox"]) or {}).get("colorspace"),
                    digest=(match_info(b["bbox"]) or {}).get("digest"),
                    box_pt=[round(w, 1), round(h, 1)])))
                continue

            if len(b["line_objs"]) > 1 and b["max_size"] >= HEADING_MIN_SIZE:
                stats["multi_line_heading_blocks"] += 1

            is_section_start_block = (
                b["max_size"] >= HEADING_MIN_SIZE
                and any(abs(b["bbox"][1] - y) < 1.0 for y in starts_by_page.get(pno, [])))

            for line in b["line_objs"]:
                if not "".join(sp["text"] for sp in line["spans"]).strip():
                    continue
                stats["text_lines"] += 1
                ln = _line_dict(pno, line)
                sec = L.find_section(secs, pno, ln["bbox"][1])
                sid, region = sec["section_id"], sec["region_type"]
                n = L.normalize([ln["text"]])

                if region == "front_matter":
                    kind = "cover_text"
                    stats["cover_text_lines"] += 1
                elif region.startswith("printed_index_"):
                    kind = "index_entry"
                    stats["index_entry_lines"] += 1
                elif is_section_start_block:
                    kind = "heading"
                    stats["heading_lines"] += 1
                elif S.CAP_TABLE.match(n):
                    kind = "table_caption"
                elif S.CAP_FIGURE.match(n):
                    kind = "figure_caption"
                elif re.match(r"^\[\d+\]", n):
                    # "[1] …  [2] …" rows are figure legends, not prose; keeping
                    # them separate keeps them out of the paragraph flow
                    kind = "figure_label_row"
                elif S.in_fraction_zone(ln["bbox"], zones):
                    kind = "formula_fraction_part"
                elif any(tb[1] - 1 <= (ln["bbox"][1] + ln["bbox"][3]) / 2 <= tb[3] + 1
                         and tb[0] - 1 <= (ln["bbox"][0] + ln["bbox"][2]) / 2 <= tb[2] + 1
                         for _, tb in boxes):
                    stats["lines_in_tables"] += 1
                    continue                      # represented by grid_raw
                elif ln["size"] < S.SMALL_TEXT:
                    kind = "diagram_label"
                else:
                    kind = "body"

                stats["lines_kept"] += 1
                lines_by_sec[sid].append(dict(page=pno, ln=ln, kind=kind))

    return dict(lines=lines_by_sec, images=images_by_sec,
                table_sections=table_sections, pages_with_tables=pages_with_tables,
                scan_stats=stats)


def emit_section(doc, secs, section, items, images, table_sections, meta):
    """Records of one section -- same rules as 21_samples.py."""
    recs = []
    body = [it for it in items if it["kind"] == "body"]
    by_page = defaultdict(list)
    for it in body:
        by_page[it["page"]].append(it["ln"])
    marg = S.page_margins(by_page)
    pitch = S.estimate_pitch([it["ln"] for it in body])
    paras = S.assemble_paragraphs([it["ln"] for it in body], marg, pitch) if body else []

    combined = [("line", it["kind"], it["ln"]) for it in items if it["kind"] != "body"]
    combined += [("para", "paragraph", p) for p in paras]
    combined += [("image", "figure", im) for im in images]

    def sort_key(x):
        typ, kind, payload = x
        if typ == "line":
            return (payload["page"], payload["baseline"], payload["bbox"][0])
        if typ == "para":
            f = payload["lines"][0]
            return (f["page"], f["baseline"], f["bbox"][0])
        pno, b, _info = payload
        return (pno, b["bbox"][1], b["bbox"][0])

    combined.sort(key=sort_key)

    for k, it in enumerate(combined):
        kind = it[0]
        if kind == "image":
            pno, b, info = it[2]
            inline = info.get("image_class") == "inline_icon"
            rec = dict(
                record_id="%s:p%03d:i%03d" % (meta["prefix"], pno, k),
                record_type="figure", sample=meta["sample"],
                doc_id=meta["doc_id"], version=meta["version"],
                source_file=meta["source_file"], sha256=meta["sha256"],
                section=meta["section_brief"], region_type=meta["region_type"],
                physical_page=pno, printed_page=pno + L.PRINTED_OFFSET,
                bbox=b["bbox"], block_kind="inline_icon" if inline else "figure",
                raw_text="", norm_text="",
                image_info=info,
                extraction=dict(engine="PyMuPDF %s get_text('dict')" % pymupdf.__version__,
                                block_type="image"),
                flags=dict(semantic_content_extracted=False, inline_candidate=inline),
                needs_review=not inline,
                review_note=("小尺寸内联图标，只记录位置与嵌入对象信息，不做语义提取。" if inline
                             else "图片内容未做任何语义提取；仅记录位置与嵌入对象信息，"
                                  "供人工或后续图像处理使用。"))
            recs.append(rec)
            continue

        if kind == "line":
            ln = it[2]
            raw = ln["text"]
            n = L.normalize([raw])
            rec = dict(
                record_id="%s:p%03d:s%03d" % (meta["prefix"], ln["page"], k),
                record_type="block", sample=meta["sample"],
                doc_id=meta["doc_id"], version=meta["version"],
                source_file=meta["source_file"], sha256=meta["sha256"],
                section=meta["section_brief"], region_type=meta["region_type"],
                physical_page=ln["page"], printed_page=ln["page"] + L.PRINTED_OFFSET,
                bbox=ln["bbox"], block_kind=it[1], raw_text=raw, norm_text=n,
                source_lines=[dict(page=ln["page"], bbox=ln["bbox"], text=raw)],
                line_count=1,
                normalization=dict(rules=["join_visual_linebreaks", "map_pua_bullets",
                                          "collapse_whitespace"],
                                   chars_preserved=L.preserved(raw, n)),
                extraction=dict(engine="PyMuPDF %s get_text('dict')" % pymupdf.__version__,
                                fonts=ln["fonts"], max_font_size=ln["size"]),
                flags=S.line_flags(it[1], n, ln["fonts"], ln["script_spans"]),
            )
            if ln["script_spans"]:
                rec["script_spans"] = ln["script_spans"]
            if rec["flags"]["contains_formula"]:
                rec["formula_span_layout"] = S.formula_span_layout(doc, ln["page"], ln["bbox"])
            if it[1] == "diagram_label":
                rec["needs_review"] = True
                rec["review_note"] = ("图形/图例文字（字号 %.1f pt，小于正文 10.6 pt）："
                                      "未做任何语义推断，仅供人工判断其在流程图中的作用。" % ln["size"])
            elif it[1] == "formula_fraction_part":
                rec["needs_review"] = True
                rec["review_note"] = ("检测到分式横线（stacked fraction）：该文本行是分式的分子/分母/"
                                      "同行片段之一，几何顺序与数学读序不一定一致，需人工按渲染页核对。")
            elif it[1] == "heading":
                rec["record_type"] = "block"
            elif it[1] == "cover_text":
                rec["needs_review"] = True
                rec["review_note"] = ("封面文本层乱码（字体缺 ToUnicode，见预检查 6.1/6.2）："
                                      "已原样保留乱码字符，不可作为规则正文。")
            recs.append(rec)
            continue

        # ---- paragraph ----
        p = it[2]
        first = p["lines"][0]
        n = p["norm"]
        all_scripts = [sp for l in p["lines"] for sp in l["script_spans"]]
        rec = dict(
            record_id="%s:p%03d:p%03d" % (meta["prefix"], first["page"], k),
            record_type="block", sample=meta["sample"],
            doc_id=meta["doc_id"], version=meta["version"],
            source_file=meta["source_file"], sha256=meta["sha256"],
            section=meta["section_brief"], region_type=meta["region_type"],
            physical_page=first["page"], printed_page=first["page"] + L.PRINTED_OFFSET,
            physical_pages=p["pages"],
            bbox=p["bbox"], block_kind="paragraph", raw_text=p["raw"], norm_text=n,
            source_lines=[dict(page=l["page"], bbox=l["bbox"], text=l["text"]) for l in p["lines"]],
            line_count=len(p["lines"]),
            cross_page=len(p["pages"]) > 1,
            normalization=dict(rules=["join_visual_linebreaks", "map_pua_bullets",
                                      "collapse_whitespace"],
                               chars_preserved=L.preserved(p["raw"], n)),
            extraction=dict(engine="PyMuPDF %s get_text('dict')" % pymupdf.__version__,
                            fonts=sorted({f for l in p["lines"] for f in l["fonts"]}),
                            max_font_size=max(l["size"] for l in p["lines"]),
                            assembled_from="visual lines merged by geometry"),
            flags=S.line_flags("paragraph", n, sorted({f for l in p["lines"] for f in l["fonts"]}),
                               all_scripts),
        )
        if all_scripts:
            rec["script_spans"] = all_scripts
        if len(p["pages"]) > 1:
            by_page = {}
            for l in p["lines"]:
                b = by_page.setdefault(l["page"], list(l["bbox"]))
                b[0] = min(b[0], l["bbox"][0]); b[1] = min(b[1], l["bbox"][1])
                b[2] = max(b[2], l["bbox"][2]); b[3] = max(b[3], l["bbox"][3])
            rec["bbox_by_page"] = {str(k): [round(v, 2) for v in b] for k, b in sorted(by_page.items())}
            rec["first_line"] = dict(page=first["page"], bbox=first["bbox"])
        if rec["flags"]["contains_formula"] and len(p["lines"]) <= 4:
            rec["formula_span_layout"] = [
                S.formula_span_layout(doc, l["page"], l["bbox"]) for l in p["lines"]]
        if rec["flags"]["starts_with_figure_marker"]:
            rec["needs_review"] = True
            rec["review_note"] = ("该段落首行以图形标注编号 [n] 开头，可能是图例行被段落合并规则"
                                  "并入正文，需人工确认是否应在图注处断开。")
        recs.append(rec)

    # ---- tables (only for sections that actually own one) ----
    if section["section_id"] in table_sections:
        trecs = S.table_records(doc, secs, section, meta)
        for t in trecs:
            t["caption_status"] = "captioned" if t.get("caption") else "no_caption"
            t["region_type"] = meta["region_type"]
        recs += trecs

    # ---- stacked fractions: one envelope record per detected bar ----
    for pno in sorted({it["page"] for it in items}):
        page = doc.load_page(pno - 1)
        boxes = [(pno, t.bbox) for t in page.find_tables().tables if S.valid_table(t)]
        zones = S.fraction_zones(page, [t.bbox for t in page.find_tables().tables if S.valid_table(t)])
        for j, z in enumerate(zones):
            inside = [r["record_id"] for r in recs
                      if r["physical_page"] == pno
                      and r.get("block_kind") == "formula_fraction_part"
                      and z["y0"] <= (r["bbox"][1] + r["bbox"][3]) / 2 <= z["y1"]]
            if not inside:
                continue
            recs.append(dict(
                record_id="%s:p%d:f%d" % (meta["prefix"], pno, j),
                record_type="formula_fraction", sample=meta["sample"],
                doc_id=meta["doc_id"], version=meta["version"],
                source_file=meta["source_file"], sha256=meta["sha256"],
                section=meta["section_brief"], region_type=meta["region_type"],
                physical_page=pno, printed_page=pno + L.PRINTED_OFFSET,
                bbox=[round(z["x0"], 2), round(z["y0"], 2),
                      round(z["x1"], 2), round(z["y1"], 2)],
                block_kind="formula_fraction",
                fraction_bar=z["bar"],
                numerator_text=z["numerator"], denominator_text=z["denominator"],
                part_record_ids=inside, raw_text="", norm_text="",
                needs_review=True,
                review_note="分式由分子/分母/同行片段多个独立文本对象拼成，横线为矢量绘制；"
                            "本记录的 part_record_ids 保留全部原始片段与坐标，未拼装或改写公式。"))

    recs.sort(key=lambda r: (r["physical_page"], r["bbox"][1], r["record_type"] != "table"))
    return recs


def build(doc_id):
    cfg = L.DOCS[doc_id]
    skel = L.load_skeleton(doc_id)
    secs = skel["sections"]
    doc = pymupdf.open(L.doc_path(doc_id))
    scanned = scan_document(doc, secs)
    print("   scan: pages=%(pages)d content_blocks=%(content_blocks)d text_lines=%(text_lines)d "
          "kept=%(lines_kept)d in_tables=%(lines_in_tables)d images=%(image_blocks)d "
          "tables=%(valid_tables)d rejected_boxes=%(rejected_table_boxes)d "
          "fraction_zones=%(fraction_zones)d multi_line_heading_blocks=%(multi_line_heading_blocks)d"
          % scanned["scan_stats"], flush=True)

    records = []
    for sec in secs:
        sid = sec["section_id"]
        items = scanned["lines"].get(sid, [])
        images = scanned["images"].get(sid, [])
        if not items and not images and sid not in scanned["table_sections"]:
            continue
        brief = dict(section_id=sid, section_no=sec["section_no"], title=sec["title"],
                     name=sec["name"], level=sec["level"], path=sec["path"])
        meta = dict(sample="fulltext", doc_id=doc_id, version=cfg["version"],
                    source_file=cfg["source_file"], sha256=skel["doc"]["sha256"],
                    section_brief=brief, prefix="%s:%s" % (doc_id, sec["section_no"] or sec["title"]),
                    region_type=sec["region_type"])
        recs = emit_section(doc, secs, sec, items, images, scanned["table_sections"], meta)
        for r in recs:
            r["section_index"] = sid
        records += recs

    for i, r in enumerate(records):
        r["record_index"] = i
    doc.close()
    return skel, records, scanned["scan_stats"]


def main():
    summary = {}
    for doc_id in L.DOCS:
        print("== full-text structuring", doc_id, flush=True)
        skel, records, scan_stats = build(doc_id)
        year = doc_id.replace("RMUC", "")
        out = os.path.join(L.STRUCT, "%s_结构化.jsonl" % year)
        with open(out, "w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        kinds = {}
        for r in records:
            k = r.get("block_kind", r["record_type"])
            kinds[k] = kinds.get(k, 0) + 1
        summary[doc_id] = dict(file=os.path.relpath(out, L.ROOT).replace("\\", "/"),
                               records=len(records), bytes=os.path.getsize(out),
                               block_kinds=kinds, scan=scan_stats,
                               chars=sum(len(r.get("raw_text") or "") for r in records),
                               sections_with_content=len({r["section_index"] for r in records}),
                               needs_review=sum(1 for r in records if r.get("needs_review")))
        print("   records %d -> %s (%.1f KB)" % (len(records), out, os.path.getsize(out) / 1024))
        print("   kinds", kinds, flush=True)

    json.dump(dict(generated=__import__("datetime").datetime.now().isoformat(timespec="seconds"),
                   summary=summary),
              open(os.path.join(L.STRUCT, "fulltext_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("written fulltext_summary.json")


if __name__ == "__main__":
    main()
