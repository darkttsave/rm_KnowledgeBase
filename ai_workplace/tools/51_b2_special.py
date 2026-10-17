#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 5 (phase B2) -- step 2: special-content difference discovery.

Covers
  * all 154 extracted tables: coverage list + parameter / header / row-label diffs
  * formulas: fraction layout + sub/superscript spans
  * figures: caption pairing + embedded-image binary hash comparison
  * diagram text is already covered by the body pass; counted here for the report

PyMuPDF is used only to read the embedded image streams (sha256), so that
"identical binary" can be asserted without any visual inspection.  No new PDF
parser is introduced and phase-A artefacts are read-only.
"""
import os
import re
import sys
import json
import hashlib
from collections import Counter, defaultdict

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b2_lib as L

NUM = re.compile(r"\d+(?:\.\d+)?")
UNIT_TOK = L.UNIT_TOK


def pdf_path(doc):
    d = os.path.join(L.ROOT, "原始材料")
    for f in os.listdir(d):
        if doc == "RMUC2026" and f.startswith("2026"):
            return os.path.join(d, f)
        if doc == "RMUC2027" and "官方版" in f:
            return os.path.join(d, f)
    raise SystemExit("pdf not found: " + doc)


def image_hashes(doc):
    """(page, rounded bbox) -> dict(stream, pixels, w, h)

    `stream` is the sha256 of the embedded image file (changes with compression);
    `pixels` is the sha256 of the decoded raster.  Two images with the same
    `pixels` hash are visually identical even if the PDF re-encoded them, which is
    what lets B2 assert "没有变化" without opening the picture by eye.
    """
    path = pdf_path(doc)
    out = {}
    d = pymupdf.open(path)
    cache = {}
    for pno in range(d.page_count):
        page = d[pno]
        for info in page.get_image_info(xrefs=True):
            xref = info.get("xref", 0)
            if not xref:
                continue
            if xref not in cache:
                sig = dict(stream=None, pixels=None, w=None, h=None)
                try:
                    sig["stream"] = hashlib.sha256(d.extract_image(xref)["image"]).hexdigest()
                except Exception:
                    pass
                try:
                    pix = pymupdf.Pixmap(d, xref)
                    if pix.colorspace is None or pix.colorspace.n not in (1, 3):
                        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                    sig["pixels"] = hashlib.sha256(pix.samples).hexdigest()
                    sig["w"], sig["h"] = pix.width, pix.height
                except Exception:
                    pass
                cache[xref] = sig
            bb = tuple(round(v, 1) for v in info["bbox"])
            out[(pno + 1, bb)] = cache[xref]
    d.close()
    return out


def norm_cell(c):
    return L.norm(c or "")


def num_tokens(grid):
    out = Counter()
    for row in grid:
        for c in row:
            if c:
                out.update(NUM.findall(L.strip_refs(c)))
    return out


def unit_tokens(grid):
    out = Counter()
    for row in grid:
        for c in row:
            if c:
                out.update(UNIT_TOK.findall(L.strip_refs(c)))
    return out


def cell_multiset(grid):
    m = Counter()
    for row in grid:
        for c in row:
            n = norm_cell(c)
            if n:
                m[n] += 1
    return m


def col_headers(grid):
    """top row non-empty cells = column titles"""
    if not grid:
        return []
    return [norm_cell(c) for c in grid[0] if norm_cell(c)]


def row_labels(grid):
    return [norm_cell(row[0]) for row in grid if row and norm_cell(row[0])]


def bigram_cos(a, b):
    if not a or not b:
        return 0.0
    import math
    common = set(a) & set(b)
    num = sum(a[k] * b[k] for k in common)
    da = math.sqrt(sum(v * v for v in a.values()))
    db = math.sqrt(sum(v * v for v in b.values()))
    return num / (da * db) if da and db else 0.0


def group_tables(recs):
    """Group page-spanning tables into one logical table.

    Phase A emits one record per detected table box, so a table that continues on
    the next page becomes two records (the continuation has no caption and often no
    table number).  Comparing raw records would turn one edited table into
    "1 delete + 1 add", so continuation records are grouped first.
    """
    groups = []
    cur = None
    for r in recs:
        if r["record_type"] != "table" or r.get("region_type") != "section":
            cur = None
            continue
        same = (cur is not None
                and cur["section_index"] == r["section_index"]
                and (r.get("table_no") is None or r.get("table_no") == cur["table_no"])
                and r.get("caption") is None)
        if same:
            cur["recs"].append(r)
        else:
            cur = dict(section_index=r["section_index"], table_no=r.get("table_no"),
                       caption=r.get("caption"), recs=[r])
            groups.append(cur)
    return groups


def table_signature(group):
    recs = group["recs"]
    lead = recs[0]
    grid = []
    for i, r in enumerate(recs):
        g = r.get("grid_raw") or []
        if i and g and grid and [norm_cell(c) for c in g[0]] == [norm_cell(c) for c in grid[0]]:
            g = g[1:]          # repeated header row on the continuation page
        grid.extend(g)
    txt = "\n".join(c for row in grid for c in row if c)
    cells = sum(len(row) for row in grid)
    blank = sum(1 for row in grid for c in row if not norm_cell(c))
    return dict(
        id=lead["record_id"], ids=[r["record_id"] for r in recs],
        record_count=len(recs),
        doc=lead["doc_id"], section_index=lead["section_index"],
        section_no=lead["section"]["section_no"], section_title=lead["section"]["title"],
        section_path=lead["section"]["path"],
        physical_page=lead["physical_page"], printed_page=lead["printed_page"],
        physical_pages=[r["physical_page"] for r in recs],
        table_no=group["table_no"], caption=group["caption"],
        caption_status=lead.get("caption_status"),
        rows=len(grid), cols=max((len(row) for row in grid), default=0),
        blank_ratio=round(blank / cells, 3) if cells else None,
        grid_missing=sum(len((r.get("coverage_check") or {}).get("missing_words") or []) for r in recs),
        source_lines=sum(len(r.get("source_text_lines") or []) for r in recs),
        grid=grid,
        grams=Counter(txt[i:i + 2] for i in range(len(txt) - 1)),
        nums=num_tokens(grid), units=unit_tokens(grid),
        headers=col_headers(grid), labels=row_labels(grid), cells=cell_multiset(grid),
        bbox=lead["bbox"],
    )


def seclabel(sec):
    return (sec.get("no") or sec.get("title") or "") if sec else ""


def main():
    align = L.load_json(os.path.join(L.ALIGN, "章节对应关系.json"))
    recs26 = L.load_jsonl(os.path.join(L.STRUCT, "2026_结构化.jsonl"))
    recs27 = L.load_jsonl(os.path.join(L.STRUCT, "2027_结构化.jsonl"))

    sec2unit26, sec2unit27, unit_rel = {}, {}, {}
    for u in align["alignments"]:
        for s in u["sections_2026"]:
            sec2unit26[s["id"]] = u["align_id"]
        for s in u["sections_2027"]:
            sec2unit27[s["id"]] = u["align_id"]
    by_unit_t26, by_unit_t27 = defaultdict(list), defaultdict(list)
    for g in group_tables(recs26):
        by_unit_t26[sec2unit26[g["section_index"]]].append(table_signature(g))
    for g in group_tables(recs27):
        by_unit_t27[sec2unit27[g["section_index"]]].append(table_signature(g))

    # ---------------- tables ----------------
    table_rows = []
    used26, used27 = set(), set()

    def pair_score(a, b):
        s = 0.0
        if a["table_no"] and a["table_no"] == b["table_no"]:
            s += 0.55
        ca = L.norm(a["caption"] or "")
        cb = L.norm(b["caption"] or "")
        if ca and cb:
            s += 0.25 * L.ratio(ca, cb)
        s += 0.20 * bigram_cos(a["grams"], b["grams"])
        return s

    pairs = []
    for aid in by_unit_t26:
        for a in by_unit_t26[aid]:
            for b in by_unit_t27.get(aid, []):
                sc = pair_score(a, b)
                if sc >= 0.05:
                    pairs.append((sc, a["id"], b["id"], aid))
    pairs.sort(reverse=True)
    t26 = {t["id"]: t for ts in by_unit_t26.values() for t in ts}
    t27 = {t["id"]: t for ts in by_unit_t27.values() for t in ts}
    t_pairs = []
    for sc, ia, ib, aid in pairs:
        if ia in used26 or ib in used27:
            continue
        used26.add(ia)
        used27.add(ib)
        t_pairs.append((sc, t26[ia], t27[ib], aid))

    def table_diff(a, b):
        ev = {}
        if (a["rows"], a["cols"]) != (b["rows"], b["cols"]):
            ev["shape"] = {"2026": [a["rows"], a["cols"]], "2027": [b["rows"], b["cols"]]}
        if a["nums"] != b["nums"]:
            ev["numbers"] = {"added": dict(b["nums"] - a["nums"]),
                             "removed": dict(a["nums"] - b["nums"])}
        if a["units"] != b["units"]:
            ev["units"] = {"added": dict(b["units"] - a["units"]),
                           "removed": dict(a["units"] - b["units"])}
        ha, hb = set(a["headers"]), set(b["headers"])
        if ha != hb:
            ev["column_headers"] = {"added": sorted(hb - ha)[:12], "removed": sorted(ha - hb)[:12]}
        la, lb = set(a["labels"]), set(b["labels"])
        if la != lb:
            ev["row_labels"] = {"added": sorted(lb - la)[:12], "removed": sorted(la - lb)[:12]}
        ca, cb = a["cells"], b["cells"]
        if ca != cb:
            ev["cells"] = {"added": list((cb - ca).elements())[:12],
                           "removed": list((ca - cb).elements())[:12]}
        return ev

    for sc, a, b, aid in t_pairs:
        ev = table_diff(a, b)
        reliable = (a["grid_missing"] == 0 and b["grid_missing"] == 0
                    and (a["blank_ratio"] or 0) <= 0.80 and (b["blank_ratio"] or 0) <= 0.80)
        if not reliable:
            ev["grid_reliability"] = dict(
                note="至少一侧网格存在丢词或空白率 > 80%，参数比对结果只能作为线索，"
                     "必须回到 source_text_lines 与原 PDF 核验",
                grid_missing={"2026": a["grid_missing"], "2027": b["grid_missing"]},
                blank_ratio={"2026": a["blank_ratio"], "2027": b["blank_ratio"]})
        params_changed = bool(ev.get("numbers") or ev.get("units"))
        textual = bool(ev.get("cells") or ev.get("column_headers") or ev.get("row_labels"))
        if params_changed:
            dtype = "实质修改候选"
        elif ev.get("shape") or textual:
            dtype = "文字调整候选"
        else:
            dtype = "内容一致"
        table_rows.append(dict(
            kind="table", align_id=aid,
            diff_type=dtype,
            counts_as_change=dtype != "内容一致",
            similarity=round(sc, 3),
            table_2026={k: a[k] for k in ("id", "table_no", "caption", "physical_page",
                                          "printed_page", "section_no", "section_title",
                                          "rows", "cols", "blank_ratio", "grid_missing")},
            table_2027={k: b[k] for k in ("id", "table_no", "caption", "physical_page",
                                          "printed_page", "section_no", "section_title",
                                          "rows", "cols", "blank_ratio", "grid_missing")},
            evidence=ev,
            grid_reliable=reliable,
            needs_review=True,
            review_reason=("网格不可靠，需按 source_text_lines 与原 PDF 核验"
                           if not reliable else
                           "表格参数存在变化，需人工核验" if params_changed else
                           "文本层未见参数变化，但表格结构（合并单元格）未还原，不能据此认定完全无变化"),
        ))

    # ---- full-text fallback for tables that found no partner inside their unit ----
    def tscore_global(a, b):
        ca, cb = L.norm(a["caption"] or ""), L.norm(b["caption"] or "")
        s = 0.6 * (L.ratio(ca, cb) if ca and cb else 0.0)
        s += 0.4 * bigram_cos(a["grams"], b["grams"])
        return s

    t_moved = []
    for t in t26.values():
        if t["id"] in used26:
            continue
        best = None
        for u in t27.values():
            if u["id"] in used27:
                continue
            r = tscore_global(t, u)
            if best is None or r > best[0]:
                best = (r, u)
        if best and best[0] >= 0.35:
            used26.add(t["id"])
            used27.add(best[1]["id"])
            t_moved.append((best[0], t, best[1]))

    # ---- tables recovered by the full-text fallback: migration candidates ----
    for sc, a, b in t_moved:
        ev = table_diff(a, b)
        ev["note"] = ("该表在 B1 对应章节内未找到，但在全文其他章节找到相似表，"
                      "疑为跨章节迁移/重排")
        table_rows.append(dict(
            kind="table", align_id=sec2unit26.get(a["section_index"]),
            diff_type="迁移或重组候选", counts_as_change=True, similarity=round(sc, 3),
            table_2026={k: a[k] for k in ("id", "table_no", "caption", "physical_page",
                                          "printed_page", "section_no", "section_title",
                                          "rows", "cols", "blank_ratio", "grid_missing")},
            table_2027={k: b[k] for k in ("id", "table_no", "caption", "physical_page",
                                          "printed_page", "section_no", "section_title",
                                          "rows", "cols", "blank_ratio", "grid_missing")},
            evidence=ev, grid_reliable=False, needs_review=True,
            review_reason="表格疑为跨章节迁移，需人工核验"))

    # unmatched tables
    for t in t26.values():
        if t["id"] in used26:
            continue
        best = None
        for u in t27.values():
            ca, cb = L.norm(t["caption"] or ""), L.norm(u["caption"] or "")
            r = L.ratio(ca, cb) if ca and cb else bigram_cos(t["grams"], u["grams"])
            if best is None or r > best[0]:
                best = (r, u)
        table_rows.append(dict(
            kind="table", align_id=sec2unit26.get(t["section_index"]), diff_type="删除候选",
            counts_as_change=True, similarity=round(best[0], 3) if best else 0.0,
            table_2026={k: t[k] for k in ("id", "table_no", "caption", "physical_page",
                                          "printed_page", "section_no", "section_title",
                                          "rows", "cols", "blank_ratio", "grid_missing")},
            table_2027=({k: best[1][k] for k in ("id", "table_no", "caption", "physical_page",
                                                 "printed_page", "section_no")} if best else None),
            evidence=dict(note="在 B1 对应章节内未找到对应表格",
                          fulltext_best_similarity=round(best[0], 4) if best else 0.0,
                          fulltext_best_section=seclabel({"no": best[1]["section_no"],
                                                          "title": best[1]["section_title"]}) if best else ""),
            grid_reliable=False, needs_review=True,
            review_reason="表格疑似删除，需人工确认"))
    for t in t27.values():
        if t["id"] in used27:
            continue
        best = None
        for a in t26.values():
            ca, cb = L.norm(a["caption"] or ""), L.norm(t["caption"] or "")
            r = L.ratio(ca, cb) if ca and cb else bigram_cos(a["grams"], t["grams"])
            if best is None or r > best[0]:
                best = (r, a)
        table_rows.append(dict(
            kind="table", align_id=sec2unit27.get(t["section_index"]), diff_type="新增候选",
            counts_as_change=True, similarity=round(best[0], 3) if best else 0.0,
            table_2026=None,
            table_2027={k: t[k] for k in ("id", "table_no", "caption", "physical_page",
                                          "printed_page", "section_no", "section_title",
                                          "rows", "cols", "blank_ratio", "grid_missing")},
            evidence=dict(note="在 B1 对应章节内未找到对应表格",
                          fulltext_best_similarity=round(best[0], 4) if best else 0.0,
                          fulltext_best_section=seclabel({"no": best[1]["section_no"],
                                                          "title": best[1]["section_title"]}) if best else ""),
            grid_reliable=False, needs_review=True,
            review_reason="表格疑似新增，需人工确认"))
    n_tables = len(table_rows)
    print("tables: %d, matched pairs %d, rows %d" % (len(t26) + len(t27), len(t_pairs), n_tables))

    # ---------------- figures ----------------
    h26 = image_hashes("RMUC2026")
    h27 = image_hashes("RMUC2027")
    print("image hashes: 2026=%d 2027=%d" % (len(h26), len(h27)))

    def fig_hash(doc, rec, table):
        page = rec["physical_page"]
        bb = rec["bbox"]
        cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        best, bestd = None, 1e9
        for (p, b), h in table.items():
            if p != page or len(b) != 4:
                continue
            dx = (b[0] + b[2]) / 2 - cx
            dy = (b[1] + b[3]) / 2 - cy
            d = (dx * dx + dy * dy) ** 0.5
            if d < bestd:
                best, bestd = h, d
        return (best if bestd <= 6.0 else None)

    def fig_sig(r, hs):
        cap = None
        ii = r.get("image_info") or {}
        return dict(id=r["record_id"], doc=r["doc_id"], section_index=r["section_index"],
                    section_no=r["section"]["section_no"], section_title=r["section"]["title"],
                    physical_page=r["physical_page"], printed_page=r["printed_page"],
                    w=ii.get("width_px"), h=ii.get("height_px"), cs=ii.get("colorspace"),
                    bbox=r["bbox"], hash=fig_hash(r["doc_id"], r, hs),
                    caption=cap)

    figs26 = [fig_sig(r, h26) for r in recs26
              if r.get("block_kind") == "figure" and r.get("region_type") == "section"]
    figs27 = [fig_sig(r, h27) for r in recs27
              if r.get("block_kind") == "figure" and r.get("region_type") == "section"]

    # captions live as separate records; attach by nearest caption after the figure
    def attach_captions(recs, figs):
        caps = [r for r in recs if r.get("block_kind") == "figure_caption"]
        by_page = defaultdict(list)
        for c in caps:
            by_page[c["physical_page"]].append(c)
        for f in figs:
            cand = [c for c in by_page.get(f["physical_page"], [])
                    if c["bbox"][1] >= f["bbox"][3] - 2]
            if cand:
                c = min(cand, key=lambda c: c["bbox"][1] - f["bbox"][3])
                f["caption"] = c.get("norm_text")
                f["caption_id"] = c["record_id"]
        return figs
    figs26 = attach_captions(recs26, figs26)
    figs27 = attach_captions(recs27, figs27)

    fig_rows = []
    fu26, fu27 = set(), set()
    for aid in set(sec2unit26.values()):
        A = [f for f in figs26 if sec2unit26.get(f["section_index"]) == aid]
        B = [f for f in figs27 if sec2unit27.get(f["section_index"]) == aid]
        cand = []
        for a in A:
            for b in B:
                s = 0.0
                if a["caption"] and b["caption"]:
                    s += 0.7 * L.ratio(L.norm(a["caption"]), L.norm(b["caption"]))
                if (a["w"], a["h"]) == (b["w"], b["h"]):
                    s += 0.2
                if a["hash"] and b["hash"] and a["hash"].get("pixels") and a["hash"]["pixels"] == b["hash"]["pixels"]:
                    s += 0.1
                cand.append((s, a["id"], b["id"]))
        cand.sort(reverse=True)
        for s, ia, ib in cand:
            if ia in fu26 or ib in fu27:
                continue
            fu26.add(ia)
            fu27.add(ib)
            a = next(x for x in A if x["id"] == ia)
            b = next(x for x in B if x["id"] == ib)
            same_hash = bool(a["hash"] and b["hash"]
                             and a["hash"].get("pixels") and a["hash"].get("pixels") == b["hash"].get("pixels"))
            ev = dict(
                image_hash_identical=same_hash,
                stream_hash_identical=bool(a["hash"] and b["hash"]
                                           and a["hash"].get("stream") == b["hash"].get("stream")),
                size={"2026": [a["w"], a["h"]], "2027": [b["w"], b["h"]]},
                caption={"2026": a["caption"], "2027": b["caption"]},
            )
            if same_hash:
                dtype = "内容一致"
                ev["note"] = ("嵌入图像解码后的像素 sha256 完全一致，可判定图像本身未变化（与 PDF 重新压缩无关）")
            else:
                dtype = "文字调整候选"
                ev["note"] = "嵌入图像二进制不同或未能定位，文本层无法判断图形内容，需要视觉对照"
            fig_rows.append(dict(kind="figure", align_id=aid, diff_type=dtype,
                                 counts_as_change=(dtype != "内容一致"),
                                 similarity=round(s, 3),
                                 figure_2026={k: a[k] for k in ("id", "section_no", "section_title",
                                                                "physical_page", "printed_page",
                                                                "w", "h", "caption")},
                                 figure_2027={k: b[k] for k in ("id", "section_no", "section_title",
                                                                "physical_page", "printed_page",
                                                                "w", "h", "caption")},
                                 evidence=ev,
                                 needs_review=not same_hash,
                                 review_reason=("图像二进制一致，图注/位置仍在候选清单中供确认"
                                                if same_hash else
                                                "图像内容无法由文本判断，需要视觉对照")))
    # ---- figures: full-text fallback by caption text (figure number stripped) ----
    FIGNO = re.compile(r"^图\s*\d+\s*-\s*\d+\s*")
    def cap_core(c):
        return L.norm(FIGNO.sub("", c or ""))

    f_moved = []
    for a in figs26:
        if a["id"] in fu26:
            continue
        best = None
        for b in figs27:
            if b["id"] in fu27:
                continue
            r = L.ratio(cap_core(a["caption"]), cap_core(b["caption"])) if a["caption"] and b["caption"] else 0.0
            if best is None or r > best[0]:
                best = (r, b)
        if best and best[0] >= 0.6:
            fu26.add(a["id"])
            fu27.add(best[1]["id"])
            f_moved.append((best[0], a, best[1]))

    unmatched_f = []
    for f in figs26:
        if f["id"] not in fu26:
            unmatched_f.append(("删除候选", f))
    for f in figs27:
        if f["id"] not in fu27:
            unmatched_f.append(("新增候选", f))
    for r, a, b in f_moved:
        fig_rows.append(dict(kind="figure", align_id=None, diff_type="迁移或重组候选",
                             counts_as_change=True, similarity=round(r, 3),
                             figure_2026={k: a[k] for k in ("id", "section_no", "section_title",
                                                             "physical_page", "printed_page",
                                                             "w", "h", "caption")},
                             figure_2027={k: b[k] for k in ("id", "section_no", "section_title",
                                                             "physical_page", "printed_page",
                                                             "w", "h", "caption")},
                             evidence=dict(note="图注（去掉图号后）高度相似但所在章节不同，"
                                                "疑为插图跨章节迁移；图像内容仍需视觉对照",
                                           image_hash_identical=bool(a["hash"] and b["hash"] and a["hash"].get("pixels") and a["hash"]["pixels"] == b["hash"].get("pixels"))),
                             needs_review=True, review_reason="插图疑为迁移，需视觉对照"))
    for dtype, f in unmatched_f:
        fig_rows.append(dict(kind="figure", align_id=None, diff_type=dtype, counts_as_change=True,
                             similarity=0.0,
                             figure_2026=({k: f[k] for k in ("id", "section_no", "section_title",
                                                             "physical_page", "printed_page",
                                                             "w", "h", "caption")}
                                          if dtype == "删除候选" else None),
                             figure_2027=({k: f[k] for k in ("id", "section_no", "section_title",
                                                             "physical_page", "printed_page",
                                                             "w", "h", "caption")}
                                          if dtype == "新增候选" else None),
                             evidence=dict(note="所属对齐单元内未找到对应插图，需视觉对照"),
                             needs_review=True, review_reason="插图疑似%s，需视觉对照" % dtype[:2]))
    print("figures: %d + %d, paired %d, unmatched %d"
          % (len(figs26), len(figs27), len(fu26), len(unmatched_f)))

    # ---------------- formulas ----------------
    frac26 = [r for r in recs26 if r.get("block_kind") == "formula_fraction"]
    frac27 = [r for r in recs27 if r.get("block_kind") == "formula_fraction"]
    formula_rows = []

    def frac_sig(r):
        return dict(id=r["record_id"], section_index=r["section_index"],
                    section_no=r["section"]["section_no"], section_title=r["section"]["title"],
                    physical_page=r["physical_page"], printed_page=r["printed_page"],
                    numerator=r.get("numerator_text"), denominator=r.get("denominator_text"),
                    bar=r.get("fraction_bar"), parts=len(r.get("part_record_ids") or []),
                    section_path=r["section"]["path"])

    def frac_ratio(a, b):
        na, da = L.norm(a["numerator"] or ""), L.norm(a["denominator"] or "")
        nb, db = L.norm(b["numerator"] or ""), L.norm(b["denominator"] or "")
        return 0.5 * L.ratio(na, nb) + 0.5 * L.ratio(da, db)

    usedf26, usedf27 = set(), set()
    for aid in set(sec2unit26.values()):
        A = [frac_sig(r) for r in frac26 if sec2unit26.get(r["section_index"]) == aid]
        B = [frac_sig(r) for r in frac27 if sec2unit27.get(r["section_index"]) == aid]
        cand = []
        for a in A:
            for b in B:
                cand.append((frac_ratio(a, b), a["id"], b["id"]))
        cand.sort(reverse=True)
        for r, ia, ib in cand:
            if ia in usedf26 or ib in usedf27:
                continue
            usedf26.add(ia)
            usedf27.add(ib)
            a = next(x for x in A if x["id"] == ia)
            b = next(x for x in B if x["id"] == ib)
            if L.norm(a["numerator"] or "") == L.norm(b["numerator"] or "") and \
               L.norm(a["denominator"] or "") == L.norm(b["denominator"] or ""):
                dtype = "内容一致"
            else:
                dtype = "实质修改候选"
            formula_rows.append(dict(kind="formula_fraction", align_id=aid, diff_type=dtype,
                                     counts_as_change=(dtype != "内容一致"),
                                     similarity=round(r, 3),
                                     formula_2026={k: a[k] for k in ("id", "section_no",
                                                                     "physical_page", "numerator",
                                                                     "denominator", "parts")},
                                     formula_2027={k: b[k] for k in ("id", "section_no",
                                                                     "physical_page", "numerator",
                                                                     "denominator", "parts")},
                                     evidence=dict(
                                         note="分式按分子/分母文本比对；分式由多个文本对象拼成，"
                                              "上下标方向可能失真，需人工核验",
                                         parts_2026=a["parts"], parts_2027=b["parts"]),
                                     needs_review=True,
                                     review_reason="公式上下标/分式布局需人工核验"))
    for r in frac26:
        if r["record_id"] not in usedf26:
            a = frac_sig(r)
            formula_rows.append(dict(kind="formula_fraction", align_id=None, diff_type="删除候选",
                                     counts_as_change=True, similarity=0.0,
                                     formula_2026={k: a[k] for k in ("id", "section_no",
                                                                     "physical_page", "numerator",
                                                                     "denominator", "parts")},
                                     formula_2027=None,
                                     evidence=dict(note="所在对齐单元内未找到对应分式"),
                                     needs_review=True, review_reason="分式疑似删除，需人工核验"))
    for r in frac27:
        if r["record_id"] not in usedf27:
            b = frac_sig(r)
            formula_rows.append(dict(kind="formula_fraction", align_id=None, diff_type="新增候选",
                                     counts_as_change=True, similarity=0.0,
                                     formula_2026=None,
                                     formula_2027={k: b[k] for k in ("id", "section_no",
                                                                     "physical_page", "numerator",
                                                                     "denominator", "parts")},
                                     evidence=dict(note="所在对齐单元内未找到对应分式"),
                                     needs_review=True, review_reason="分式疑似新增，需人工核验"))

    # sub/superscript spans, matched by their parent record's text
    spans26 = [r for r in recs26 if r.get("script_spans")]
    spans27 = [r for r in recs27 if r.get("script_spans")]

    def span_sig(r):
        return dict(id=r["record_id"], section_index=r["section_index"],
                    section_no=r["section"]["section_no"], physical_page=r["physical_page"],
                    text=(r.get("norm_text") or "")[:120],
                    spans=[(s["text"], s["script"], round(s["size"], 2)) for s in r["script_spans"]],
                    kinds=Counter(s["script"] for s in r["script_spans"]))
    us26, us27 = set(), set()
    for aid in set(sec2unit26.values()):
        A = [span_sig(r) for r in spans26 if sec2unit26.get(r["section_index"]) == aid]
        B = [span_sig(r) for r in spans27 if sec2unit27.get(r["section_index"]) == aid]
        cand = []
        for a in A:
            for b in B:
                cand.append((L.ratio(L.norm(a["text"]), L.norm(b["text"])), a["id"], b["id"]))
        cand.sort(reverse=True)
        for r, ia, ib in cand:
            if r < 0.5 or ia in us26 or ib in us27:
                continue
            us26.add(ia)
            us27.add(ib)
            a = next(x for x in A if x["id"] == ia)
            b = next(x for x in B if x["id"] == ib)
            same = [s[0] for s in a["spans"]] == [s[0] for s in b["spans"]]
            formula_rows.append(dict(
                kind="script_spans", align_id=aid,
                diff_type="内容一致" if same else "实质修改候选",
                counts_as_change=not same, similarity=round(r, 3),
                formula_2026={k: a[k] for k in ("id", "section_no", "physical_page", "text")} | {"spans": [list(x) for x in a["spans"]]},
                formula_2027={k: b[k] for k in ("id", "section_no", "physical_page", "text")} | {"spans": [list(x) for x in b["spans"]]},
                evidence=dict(note="上下标片段按文本相似度配对；上下标方向由基线偏移判定，可能失真",
                              kinds_2026=dict(a["kinds"]), kinds_2027=dict(b["kinds"])),
                needs_review=True,
                review_reason="上下标/分式布局需人工核验"))
    for r in spans26:
        if r["record_id"] in us26:
            continue
        a = span_sig(r)
        formula_rows.append(dict(kind="script_spans", align_id=sec2unit26.get(r["section_index"]),
                                 diff_type="删除候选", counts_as_change=True, similarity=0.0,
                                 formula_2026={k: a[k] for k in ("id", "section_no", "physical_page", "text")} | {"spans": [list(x) for x in a["spans"]]},
                                 formula_2027=None,
                                 evidence=dict(note="所在对齐单元内未找到对应上下标记录"),
                                 needs_review=True, review_reason="上下标记录疑似删除，需人工核验"))
    for r in spans27:
        if r["record_id"] in us27:
            continue
        b = span_sig(r)
        formula_rows.append(dict(kind="script_spans", align_id=sec2unit27.get(r["section_index"]),
                                 diff_type="新增候选", counts_as_change=True, similarity=0.0,
                                 formula_2026=None,
                                 formula_2027={k: b[k] for k in ("id", "section_no", "physical_page", "text")} | {"spans": [list(x) for x in b["spans"]]},
                                 evidence=dict(note="所在对齐单元内未找到对应上下标记录"),
                                 needs_review=True, review_reason="上下标记录疑似新增，需人工核验"))

    print("formulas: fractions %d+%d, span records %d+%d, rows %d"
          % (len(frac26), len(frac27), len(spans26), len(spans27), len(formula_rows)))

    # ---------------- diagram text (from the body pass) ----------------
    body = L.load_jsonl(os.path.join(L.OUT, "全文候选差异.jsonl"))
    diag = [r for r in body if ((r.get("a") or {}).get("block_kind") in ("diagram_label", "figure_label_row")
                                or (r.get("b") or {}).get("block_kind") in ("diagram_label", "figure_label_row"))]
    diag_stats = Counter(r["diff_type"] for r in diag)

    # ---------------- raw-record coverage lists (every extracted item) ----------------
    g26 = group_tables(recs26)
    g27 = group_tables(recs27)
    row_by_g26 = {r["table_2026"]["id"]: r for r in table_rows if r.get("table_2026")}
    row_by_g27 = {r["table_2027"]["id"]: r for r in table_rows if r.get("table_2027")}
    table_coverage = []
    for doc, groups, rows in (("RMUC2026", g26, row_by_g26), ("RMUC2027", g27, row_by_g27)):
        for g in groups:
            sig = table_signature(g)
            row = rows.get(sig["id"])
            for i, r in enumerate(g["recs"]):
                table_coverage.append(dict(
                    doc=doc, record_id=r["record_id"], physical_page=r["physical_page"],
                    printed_page=r["printed_page"], section_no=r["section"]["section_no"],
                    section_title=r["section"]["title"], table_no=r.get("table_no"),
                    caption=r.get("caption"),
                    logical_table_id=sig["id"], continuation_of=(sig["id"] if i else None),
                    records_in_logical_table=sig["record_count"],
                    compare_status=(row["diff_type"] if row else "未比对（异常）"),
                    grid_missing=len((r.get("coverage_check") or {}).get("missing_words") or []),
                ))
    figure_coverage = []
    for doc, figs in (("RMUC2026", figs26), ("RMUC2027", figs27)):
        for f in figs:
            row = next((r for r in fig_rows if (r.get("figure_2026") or {}).get("id") == f["id"]
                        or (r.get("figure_2027") or {}).get("id") == f["id"]), None)
            figure_coverage.append(dict(
                doc=doc, record_id=f["id"], physical_page=f["physical_page"],
                printed_page=f["printed_page"], section_no=f["section_no"],
                section_title=f["section_title"], w=f["w"], h=f["h"],
                caption=f["caption"], caption_id=f.get("caption_id"),
                pixel_hash=(f["hash"] or {}).get("pixels"),
                compare_status=(row["diff_type"] if row else "未比对（异常）"),
                image_identical=(row["evidence"].get("image_hash_identical") if row else None),
                needs_visual_check=(row is not None and not row["evidence"].get("image_hash_identical")),
            ))
    formula_coverage = []
    for r in frac26 + frac27:
        row = next((x for x in formula_rows
                    if (x.get("formula_2026") or {}).get("id") == r["record_id"]
                    or (x.get("formula_2027") or {}).get("id") == r["record_id"]), None)
        formula_coverage.append(dict(
            doc=r["doc_id"], record_id=r["record_id"], kind="formula_fraction",
            physical_page=r["physical_page"], section_no=r["section"]["section_no"],
            section_title=r["section"]["title"],
            numerator=r.get("numerator_text"), denominator=r.get("denominator_text"),
            compare_status=(row["diff_type"] if row else "未比对（异常）")))
    for r in spans26 + spans27:
        row = next((x for x in formula_rows if x["kind"] == "script_spans"
                    and ((x.get("formula_2026") or {}).get("id") == r["record_id"]
                         or (x.get("formula_2027") or {}).get("id") == r["record_id"])), None)
        formula_coverage.append(dict(
            doc=r["doc_id"], record_id=r["record_id"], kind="script_spans",
            physical_page=r["physical_page"], section_no=r["section"]["section_no"],
            section_title=r["section"]["title"],
            spans=[(s["text"], s["script"]) for s in r["script_spans"]],
            compare_status=(row["diff_type"] if row else "未比对（异常）")))

    special = dict(
        table_coverage=table_coverage, figure_coverage=figure_coverage,
        formula_coverage=formula_coverage,
        raw_table_records=dict(total_2026=sum(1 for r in recs26 if r["record_type"] == "table"),
                               total_2027=sum(1 for r in recs27 if r["record_type"] == "table"),
                               logical_2026=len(g26), logical_2027=len(g27)),

        generated=__import__("datetime").datetime.now().isoformat(timespec="seconds"),
        tables=dict(total_2026=len(t26), total_2027=len(t27), matched=len(t_pairs),
                    rows=table_rows, by_type=dict(Counter(r["diff_type"] for r in table_rows)),
                    unmatched_2026=len(t26) - len(used26), unmatched_2027=len(t27) - len(used27),
                    grid_unreliable=sum(1 for r in table_rows if not r["grid_reliable"])),
        figures=dict(total_2026=len(figs26), total_2027=len(figs27), matched=len(fu26),
                     rows=fig_rows, by_type=dict(Counter(r["diff_type"] for r in fig_rows)),
                     identical_binary=sum(1 for r in fig_rows if r["evidence"].get("image_hash_identical"))),
        formulas=dict(total_2026_fraction=len(frac26), total_2027_fraction=len(frac27),
                      rows=formula_rows, by_type=dict(Counter(r["diff_type"] for r in formula_rows))),
        diagram_labels=dict(total_rows=len(diag), by_type=dict(diag_stats)),
    )
    with open(os.path.join(L.OUT, "special_diff.json"), "w", encoding="utf-8") as f:
        json.dump(special, f, ensure_ascii=False, indent=1)
    print("written special_diff.json")
    print("table by_type:", special["tables"]["by_type"])
    print("figure by_type:", special["figures"]["by_type"], "identical_binary:",
          special["figures"]["identical_binary"])
    print("formula by_type:", special["formulas"]["by_type"])
    print("diagram by_type:", special["diagram_labels"]["by_type"])


if __name__ == "__main__":
    main()
