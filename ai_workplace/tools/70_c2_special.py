#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 7 (phase C 补充) -- step 1: re-check the special content.

1. Tables: the B2 pairing favoured the table number.  Here the pairing score is
   driven by the caption (table title, number stripped), then by section context,
   and only last by content similarity.  Parameters, units, row/column structure
   and applicable objects are re-compared on the repaired pairs.
2. Figures: every matched pair with a different pixel hash gets a structural
   classification (aHash distance + colour histogram + caption delta) into
   "纯样式变化 / 信息变化 / 无法判断"; page images are rendered for manual viewing.
3. Formulas: the uncertainty list is carried over explicitly.

Output: ai_workplace/semantic/special_recheck.json (+ compare/*.png)
"""
import os
import re
import sys
import json
import math
import hashlib
from collections import Counter, defaultdict

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b2_lib as L

SEM = os.path.join(L.ROOT, "ai_workplace", "semantic")
CMP = os.path.join(SEM, "compare")
os.makedirs(CMP, exist_ok=True)
NUM = re.compile(r"\d+(?:\.\d+)?")
UNIT_TOK = L.UNIT_TOK
CAPNO = re.compile(r"^表\s*\d+\s*-\s*\d+\s*")
FIGNO = re.compile(r"^图\s*\d+\s*-\s*\d+\s*")


def pdf_path(doc):
    d = os.path.join(L.ROOT, "原始材料")
    for f in os.listdir(d):
        if doc == "RMUC2026" and f.startswith("2026"):
            return os.path.join(d, f)
        if doc == "RMUC2027" and "官方版" in f:
            return os.path.join(d, f)
    raise SystemExit("pdf not found")


# ---------------- table helpers (same logical grouping as B2) ----------------
def norm_cell(c):
    return L.norm(c or "")


def group_tables(recs):
    groups, cur = [], None
    for r in recs:
        if r["record_type"] != "table" or r.get("region_type") != "section":
            cur = None
            continue
        same = (cur is not None and cur["section_index"] == r["section_index"]
                and (r.get("table_no") is None or r.get("table_no") == cur["table_no"])
                and r.get("caption") is None)
        if same:
            cur["recs"].append(r)
        else:
            cur = dict(section_index=r["section_index"], table_no=r.get("table_no"),
                       caption=r.get("caption"), recs=[r])
            groups.append(cur)
    return groups


def tsig(g):
    recs = g["recs"]
    lead = recs[0]
    grid = []
    for i, r in enumerate(recs):
        gg = r.get("grid_raw") or []
        if i and gg and grid and [norm_cell(c) for c in gg[0]] == [norm_cell(c) for c in grid[0]]:
            gg = gg[1:]
        grid.extend(gg)
    txt = "\n".join(c for row in grid for c in row if c)
    return dict(
        id=lead["record_id"], ids=[r["record_id"] for r in recs], record_count=len(recs),
        doc=lead["doc_id"], section_index=lead["section_index"],
        section_no=lead["section"]["section_no"], section_title=lead["section"]["title"],
        physical_page=lead["physical_page"], physical_pages=[r["physical_page"] for r in recs],
        table_no=g["table_no"], caption=g["caption"],
        rows=len(grid), cols=max((len(r) for r in grid), default=0),
        grid=grid, grams=Counter(txt[i:i + 2] for i in range(len(txt) - 1)),
        cells=Counter(n for row in grid for c in row if (n := norm_cell(c))),
        nums=Counter(x for row in grid for c in row if c for x in NUM.findall(L.strip_refs(c))),
        units=Counter(x for row in grid for c in row if c for x in UNIT_TOK.findall(L.strip_refs(c))),
        headers=[norm_cell(c) for c in (grid[0] if grid else []) if norm_cell(c)],
        labels=[norm_cell(row[0]) for row in grid if row and norm_cell(row[0])],
        missing=sum(len((r.get("coverage_check") or {}).get("missing_words") or []) for r in recs),
    )


def cap_core(c):
    return L.norm(CAPNO.sub("", c or ""))


def bigcos(a, b):
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    num = sum(a[k] * b[k] for k in common)
    da = math.sqrt(sum(v * v for v in a.values()))
    db = math.sqrt(sum(v * v for v in b.values()))
    return num / (da * db) if da and db else 0.0


SUBJECT = ("重装机器人", "英雄机器人", "工程机器人", "步兵机器人", "空中机器人",
           "哨兵机器人", "空中系统", "雷达系统", "雷达", "飞镖系统", "机库", "堡垒",
           "补给区", "基地", "前哨站", "能量机关", "科技核心", "装配区", "隧道", "高地")


def subjects(txt):
    t = txt or ""
    out = set()
    for s in SUBJECT:
        if s in t:
            out.add(s)
    # "英雄机器人" already contains "机器人"; keep the specific ones only
    if out & {"重装机器人", "英雄机器人", "工程机器人", "步兵机器人", "空中机器人", "哨兵机器人"}:
        out.discard("机器人")
    return out


def tscore(a, b, unit_a=None, unit_b=None):
    """caption first, then B1 alignment-unit context, then table number, then content.

    The table number is only a tie-breaker: several 2026/2027 tables share an
    identical template (机器人关键特征) and differ only in the robot name, so the
    number alone must not decide and the subject words must not conflict.
    """
    ca, cb = cap_core(a["caption"]), cap_core(b["caption"])
    cap = L.ratio(ca, cb) if ca and cb else 0.0
    same_unit = 1.0 if (unit_a is not None and unit_a == unit_b) else 0.0
    same_no = 1.0 if (a["table_no"] and a["table_no"] == b["table_no"]) else 0.0
    content = bigcos(a["grams"], b["grams"])
    sa, sb = subjects(cap_core(a["caption"])), subjects(cap_core(b["caption"]))
    conflict = bool(sa and sb and not (sa & sb))
    score = 0.45 * cap + 0.30 * same_unit + 0.10 * same_no + 0.15 * content
    if conflict:
        score -= 0.55
    return score, dict(caption=round(cap, 3), same_unit=bool(same_unit),
                       same_table_no=bool(same_no), content=round(content, 3),
                       subject_conflict=conflict,
                       subjects=("/".join(sorted(sa)) or "-", "/".join(sorted(sb)) or "-"))


# ---------------- figure pixel signature ----------------
def _shrink_gray(pix, target=24):
    """C-level shrink to <= target x target greyscale pixels."""
    g = pymupdf.Pixmap(pymupdf.csGRAY, pix) if pix.n != 1 else pix
    while g.width > target * 2 or g.height > target * 2:
        g = pymupdf.Pixmap(g, g.width // 2, g.height // 2, None) if False else g
        # pymupdf exposes shrink via Pixmap.shrink(n)
        try:
            g.shrink(1)
        except Exception:
            break
        if g.width <= target and g.height <= target:
            break
    return g


def _sig_from_pix(pix):
    w, h = pix.width, pix.height
    samples = pix.samples
    stride = pix.stride
    g = pymupdf.Pixmap(pymupdf.csGRAY, pix) if pix.n != 1 else pix
    gs, gstride = g.samples, g.stride
    # aHash on a 16x16 grid by averaging (few reads per cell)
    cells = []
    for by in range(16):
        y0 = by * g.height // 16
        y1 = max(y0 + 1, (by + 1) * g.height // 16)
        for bx in range(16):
            x0 = bx * g.width // 16
            x1 = max(x0 + 1, (bx + 1) * g.width // 16)
            ssum = cnt = 0
            for yy in range(y0, y1, max(1, (y1 - y0) // 3)):
                base = yy * gstride
                for xx in range(x0, x1, max(1, (x1 - x0) // 3)):
                    ssum += gs[base + xx]
                    cnt += 1
            cells.append(ssum / cnt if cnt else 0)
    mean = sum(cells) / len(cells)
    bits = "".join("1" if v >= mean else "0" for v in cells)
    hist = [0] * 16
    n = 0
    step = max(1, min(g.width, g.height) // 48)
    for yy in range(0, g.height, step):
        base = yy * gstride
        for xx in range(0, g.width, step):
            v = gs[base + xx]
            hist[v >> 4] += 1
            n += 1
    return dict(ahash=bits, hist=[round(x / n, 4) for x in hist] if n else None,
                w=w, h=h)


def fig_signatures(doc):
    """lazy: only pixels for the (page,bbox) of figures actually referenced"""
    return dict(path=pdf_path(doc), cache={})


def get_sig(store, page, bbox):
    d = pymupdf.open(store["path"])
    key = (page, tuple(round(v, 1) for v in bbox))
    if key in store["cache"]:
        sig = store["cache"][key]
        d.close()
        return sig
    sig = None
    try:
        info = None
        best, bd = None, 1e9
        cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        for it in d[page - 1].get_image_info(xrefs=True):
            b = it["bbox"]
            dx, dy = (b[0] + b[2]) / 2 - cx, (b[1] + b[3]) / 2 - cy
            dd = (dx * dx + dy * dy) ** 0.5
            if dd < bd:
                best, bd = it, dd
        if best is not None and bd <= 6.0 and best.get("xref"):
            pix = pymupdf.Pixmap(d, best["xref"])
            if pix.colorspace is None or pix.colorspace.n not in (1, 3):
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            sig = _sig_from_pix(pix)
            import hashlib
            sig["pixels"] = hashlib.sha256(pix.samples).hexdigest()
    except Exception:
        sig = None
    d.close()
    store["cache"][key] = sig
    return sig


def hamming(a, b):
    if not a or not b or len(a) != len(b):
        return None
    return sum(1 for x, y in zip(a, b) if x != y) / len(a)


def histdist(a, b):
    if not a or not b or len(a) != len(b):
        return None
    return 0.5 * sum(abs(x - y) for x, y in zip(a, b))


def main():
    recs26 = L.load_jsonl(os.path.join(L.STRUCT, "2026_结构化.jsonl"))
    recs27 = L.load_jsonl(os.path.join(L.STRUCT, "2027_结构化.jsonl"))
    sp = L.load_json(os.path.join(L.OUT, "special_diff.json"))
    align = L.load_json(os.path.join(L.ALIGN, "章节对应关系.json"))
    events = L.load_jsonl(os.path.join(SEM, "规则变更候选.jsonl"))

    sec2unit26, sec2unit27 = {}, {}
    for u in align["alignments"]:
        for s in u["sections_2026"]:
            sec2unit26[s["id"]] = u["align_id"]
        for s in u["sections_2027"]:
            sec2unit27[s["id"]] = u["align_id"]

    g26 = [tsig(g) for g in group_tables(recs26)]
    g27 = [tsig(g) for g in group_tables(recs27)]
    print("logical tables: 2026=%d 2027=%d" % (len(g26), len(g27)))

    # ---------- 1. re-pair tables: caption first ----------
    old_pair = {}
    for r in sp["tables"]["rows"]:
        a, b = r.get("table_2026"), r.get("table_2027")
        if a and b:
            old_pair[a["id"]] = b["id"]
    cand = []
    for a in g26:
        for b in g27:
            sc, detail = tscore(a, b, sec2unit26.get(a["section_index"]),
                                sec2unit27.get(b["section_index"]))
            cand.append((sc, a["id"], b["id"], detail))
    cand.sort(reverse=True)
    by26 = {t["id"]: t for t in g26}
    by27 = {t["id"]: t for t in g27}
    used26, used27, new_pair = set(), set(), {}
    for sc, ia, ib, detail in cand:
        if ia in used26 or ib in used27:
            continue
        # require either a strong caption match or same section with some content
        if detail["subject_conflict"]:
            continue
        ca, cb = cap_core(a["caption"]), cap_core(b["caption"])
        if not ca and not cb:
            # neither side has a caption: only trust the content, never the bare number
            if detail["content"] < 0.60:
                continue
        elif not ca or not cb:
            # one side has no caption: require a strong content match
            if detail["content"] < 0.55:
                continue
        elif not (detail["caption"] >= 0.50
                  or (detail["same_unit"] and detail["content"] >= 0.30)
                  or (detail["same_table_no"] and detail["content"] >= 0.45)):
            continue
        used26.add(ia)
        used27.add(ib)
        new_pair[ia] = (ib, sc, detail)

    changed = [(ia, old_pair.get(ia), new_pair[ia][0]) for ia in new_pair
               if old_pair.get(ia) != new_pair[ia][0]]
    print("repaired pairs: %d (changed vs B2: %d)" % (len(new_pair), len(changed)))

    rows = []
    for ia, (ib, sc, detail) in new_pair.items():
        a, b = by26[ia], by27[ib]
        ev = {}
        if (a["rows"], a["cols"]) != (b["rows"], b["cols"]):
            ev["shape"] = {"2026": [a["rows"], a["cols"]], "2027": [b["rows"], b["cols"]]}
        if a["nums"] != b["nums"]:
            ev["numbers"] = {"added": sorted(set(b["nums"]) - set(a["nums"])),
                             "removed": sorted(set(a["nums"]) - set(b["nums"]))}
        if a["units"] != b["units"]:
            ev["units"] = {"added": sorted(set(b["units"]) - set(a["units"])),
                           "removed": sorted(set(a["units"]) - set(b["units"]))}
        ha, hb = set(a["headers"]), set(b["headers"])
        if ha != hb:
            ev["column_headers"] = {"added": sorted(hb - ha)[:10], "removed": sorted(ha - hb)[:10]}
        la, lb = set(a["labels"]), set(b["labels"])
        if la != lb:
            ev["row_labels"] = {"added": sorted(lb - la)[:10], "removed": sorted(la - lb)[:10]}
        cells_a, cells_b = a["cells"], b["cells"]
        if cells_a != cells_b:
            ev["cells"] = {"added": list((cells_b - cells_a).elements())[:10],
                           "removed": list((cells_a - cells_b).elements())[:10]}
        reliable = (a["missing"] == 0 and b["missing"] == 0)
        # caption-level topic change
        topic_changed = detail["caption"] < 0.60
        if ev.get("numbers") or ev.get("units"):
            verdict = "参数变化候选"
        elif topic_changed:
            verdict = "表主题已变（可能是不同的表）"
        elif ev.get("shape") or ev.get("cells") or ev.get("column_headers") or ev.get("row_labels"):
            verdict = "结构/文字变化候选"
        else:
            verdict = "未发现文本层差异"
        rows.append(dict(
            table_2026=dict(id=a["id"], ids=a["ids"], records=a["record_count"],
                            table_no=a["table_no"], caption=a["caption"],
                            section_no=a["section_no"], section_title=a["section_title"],
                            physical_page=a["physical_page"], rows=a["rows"], cols=a["cols"],
                            headers=a["headers"], missing=a["missing"]),
            table_2027=dict(id=b["id"], ids=b["ids"], records=b["record_count"],
                            table_no=b["table_no"], caption=b["caption"],
                            section_no=b["section_no"], section_title=b["section_title"],
                            physical_page=b["physical_page"], rows=b["rows"], cols=b["cols"],
                            headers=b["headers"], missing=b["missing"]),
            pair_score=round(sc, 3), pair_detail=detail,
            same_as_b2=(old_pair.get(ia) == ib),
            b2_partner=old_pair.get(ia),
            verdict=verdict, evidence=ev, grid_reliable=reliable,
            needs_manual=bool(not reliable or ev.get("numbers") or topic_changed),
        ))
    # unmatched
    unmatched26 = [dict(id=a["id"], table_no=a["table_no"], caption=a["caption"],
                        section_no=a["section_no"], section_title=a["section_title"],
                        physical_page=a["physical_page"]) for a in g26 if a["id"] not in used26]
    unmatched27 = [dict(id=b["id"], table_no=b["table_no"], caption=b["caption"],
                        section_no=b["section_no"], section_title=b["section_title"],
                        physical_page=b["physical_page"]) for b in g27 if b["id"] not in used27]
    print("table rows: %d, unmatched %d / %d" % (len(rows), len(unmatched26), len(unmatched27)))

    # ---------- 2. figures: structural classification ----------
    s26 = fig_signatures("RMUC2026")
    s27 = fig_signatures("RMUC2027")
    fig_bbox = {}
    for r in recs26 + recs27:
        if r.get("block_kind") == "figure":
            fig_bbox[r["record_id"]] = r["bbox"]
    f_rows = []
    for r in sp["figures"]["rows"]:
        a, b = r.get("figure_2026"), r.get("figure_2027")
        if not (a and b):
            f_rows.append(dict(kind="figure", status="单侧（新增/删除）",
                               diff_type=r["diff_type"],
                               f2026=a, f2027=b,
                               verdict="信息变化" if r["diff_type"] in ("删除候选", "新增候选", "迁移或重组候选")
                               else "无法判断",
                               reason="该图只在一侧存在"))
            continue
        sig_a = get_sig(s26, a["physical_page"], fig_bbox.get(a["id"], [0, 0, 0, 0]))
        sig_b = get_sig(s27, b["physical_page"], fig_bbox.get(b["id"], [0, 0, 0, 0]))
        pix_same = bool(sig_a and sig_b and sig_a["pixels"] and sig_a["pixels"] == sig_b["pixels"])
        ham = hamming((sig_a or {}).get("ahash"), (sig_b or {}).get("ahash"))
        hd = histdist((sig_a or {}).get("hist"), (sig_b or {}).get("hist"))
        cap_a, cap_b = a.get("caption") or "", b.get("caption") or ""
        cap_delta = L.ratio(cap_core(cap_a), cap_core(cap_b)) if cap_a and cap_b else 0.0
        if pix_same:
            verdict, reason = "像素完全一致", "解码像素哈希相同，可判定图像未变"
        elif cap_a and cap_b and cap_delta < 0.45:
            verdict, reason = "信息变化", "图注（去掉图号后）已明显不同，图形内容应视为变化"
        elif ham is None:
            verdict, reason = "无法判断", "未能定位嵌入图像"
        elif ham <= 0.10 and (hd is None or hd <= 0.10):
            verdict, reason = "纯样式变化候选", ("结构哈希差异 %.1f%%、色彩分布差异 %.3f，"
                                                 "图像结构高度一致，差异可能仅来自重绘/压缩/配色") % (100 * ham, hd or 0)
        elif ham >= 0.30 or (hd is not None and hd >= 0.25):
            verdict, reason = "信息变化", ("结构哈希差异 %.1f%%、色彩分布差异 %.3f，"
                                            "图形信息很可能已改变") % (100 * ham, hd or 0)
        else:
            verdict, reason = "无法判断", ("结构哈希差异 %.1f%%、色彩分布差异 %.3f，"
                                            "介于纯样式与信息变化之间，需目视") % (100 * ham, hd or 0)
        f_rows.append(dict(kind="figure", status="双侧", diff_type=r["diff_type"],
                           f2026=dict(id=a["id"], physical_page=a["physical_page"],
                                      w=a["w"], h=a["h"], caption=cap_a),
                           f2027=dict(id=b["id"], physical_page=b["physical_page"],
                                      w=b["w"], h=b["h"], caption=cap_b),
                           pixel_identical=pix_same,
                           ahash_distance=(round(ham, 4) if ham is not None else None),
                           hist_distance=(round(hd, 4) if hd is not None else None),
                           caption_similarity=round(cap_delta, 3),
                           verdict=verdict, reason=reason,
                           needs_manual=(verdict == "无法判断")))
    print("figures: %d rows; verdicts %s"
          % (len(f_rows), dict(Counter(r["verdict"] for r in f_rows))))

    # ---------- 3. page comparison images for impact-bearing drawings ----------
    IMPORTANT_SEC = ("4", "5", "6", "7")
    targets = []
    for r in f_rows:
        if r["status"] != "双侧" or r["verdict"] == "像素完全一致":
            continue
        sec = (r["f2026"] or {}).get("physical_page") and None
        targets.append(r)
    # prioritise 信息变化 in chapters 4/5/6/7
    def prio(r):
        a = r["f2026"]["id"]
        return (0 if r["verdict"] == "信息变化" else 1, a)
    targets.sort(key=prio)
    rendered = []
    d26 = pymupdf.open(pdf_path("RMUC2026"))
    d27 = pymupdf.open(pdf_path("RMUC2027"))
    for i, r in enumerate(targets[:14], 1):
        p26 = r["f2026"]["physical_page"]
        p27 = r["f2027"]["physical_page"]
        tag = "C%02d" % i
        n26 = os.path.join(CMP, "%s_2026_p%03d.png" % (tag, p26))
        n27 = os.path.join(CMP, "%s_2027_p%03d.png" % (tag, p27))
        d26[p26 - 1].get_pixmap(dpi=90).save(n26)
        d27[p27 - 1].get_pixmap(dpi=90).save(n27)
        lbl = "%s → %s" % ((r["f2026"].get("caption") or "无图注"),
                             (r["f2027"].get("caption") or "无图注"))
        r["compare"] = dict(tag=tag, page_2026=p26, page_2027=p27,
                            label=lbl,
                            image_2026=os.path.relpath(n26, SEM).replace("\\", "/"),
                            image_2027=os.path.relpath(n27, SEM).replace("\\", "/"))
        rendered.append(r)
    d26.close()
    d27.close()
    print("page comparisons rendered: %d" % len(rendered))

    # ---------- 4. formulas: carry over uncertainty ----------
    frows = sp["formulas"]["rows"]
    form = [dict(kind=r["kind"], diff_type=r["diff_type"],
                 f2026=(r.get("formula_2026") or {}), f2027=(r.get("formula_2027") or {}),
                 evidence=r.get("evidence"), needs_manual=True) for r in frows
            if r["diff_type"] != "内容一致"]

    out = dict(
        generated=__import__("datetime").datetime.now().isoformat(timespec="seconds"),
        method=dict(
            table_pairing="0.55×表题相似度（去掉表号）+ 0.30×同章节 + 0.15×内容二元组余弦；"
                          "不再以表号为主键",
            table_compare="行列数、列标题、行标签、数值集合、单位集合、单元格文本多重集",
            figure_class="对嵌入图像解码后计算 16×16 均值哈希与灰度直方图："
                         "哈希差异 ≤10% 判「纯样式变化候选」，≥30% 判「信息变化」，"
                         "其余判「无法判断」；图注（去图号）相似度 <0.45 直接判「信息变化」",
            limits="哈希与直方图只能反映整体结构与明暗分布，不能替代目视；"
                   "运行环境未做图像识别/OCR，报告中的「信息变化」是候选而非结论",
        ),
        tables=dict(rows=rows, unmatched_2026=unmatched26, unmatched_2027=unmatched27,
                    changed_pairing=[dict(table_2026=by26[ia]["id"],
                                          old_partner=old,
                                          new_partner=new_pair[ia][0],
                                          score=new_pair[ia][1],
                                          detail=new_pair[ia][2])
                                     for ia, old, new in changed]
                    if False else
                    [dict(table_2026=ia, old_partner=old, new_partner=ne, score=sc, detail=de)
                     for ia, old, (ne, sc, de) in [(x[0], x[1], new_pair[x[0]]) for x in changed]],
                    by_verdict=dict(Counter(r["verdict"] for r in rows))),
        figures=dict(rows=f_rows, by_verdict=dict(Counter(r["verdict"] for r in f_rows)),
                     rendered=[r.get("compare") for r in rendered]),
        formulas=form,
    )
    json.dump(out, open(os.path.join(SEM, "special_recheck.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("table verdicts:", out["tables"]["by_verdict"])
    print("figure verdicts:", out["figures"]["by_verdict"])
    print("written special_recheck.json")


if __name__ == "__main__":
    main()
