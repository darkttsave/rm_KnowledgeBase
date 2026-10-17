#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 2 -- step 1: build the complete section skeleton from the built-in
outline and verify boundaries against the actual heading text blocks.

The skeleton is NOT page-based.  Every text/image block is assigned to exactly
one region by (physical_page, y) ordering, so:
  * pages that contain several section starts (e.g. 5 chapters on one page) split
    correctly between those sections, and
  * sections that run over several pages collect blocks from all of them.
Regions the official outline does not cover (cover page, printed 目录/表目录/
图目录) are added explicitly as synthetic regions instead of being silently
absorbed by the neighbouring section.

Read-only.  Identity is reused from the pre-check artefacts, but re-hashed to
prove the source files are unchanged.
"""
import os
import re
import json
import hashlib
import datetime

import pymupdf

import struct_lib as L

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "原始材料")
AUD = os.path.join(ROOT, "ai_workplace", "audit")
OUT = os.path.join(ROOT, "ai_workplace", "structured")
os.makedirs(OUT, exist_ok=True)

DOCS = [
    dict(doc_id="RMUC2026", version="V2.2.0",
         source_file="2026 机甲大师超级对抗赛比赛规则手册V2.2.0.pdf"),
    dict(doc_id="RMUC2027", version="V1.0.0",
         source_file="RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-官方版.pdf"),
]

LEVEL_SIZE = {1: 22.0, 2: 18.0, 3: 16.0, 4: 15.0}
PAGE_H = 841.92
FOOTER_Y = 755.0
LOGO_Y1 = 70.0
PRINTED_OFFSET = -1
INDEX_TITLES = {"目录": "printed_index_toc",
                "表目录": "printed_index_tables",
                "图目录": "printed_index_figures"}


def norm_ws(s):
    return re.sub(r"\s+", "", s)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest().upper()


def load_precheck():
    data = json.load(open(os.path.join(AUD, "precheck_structure.json"), encoding="utf-8"))
    return {d["file"]: d for d in data["files"]}


def blocks_of(page):
    content, running = [], []
    for b in page.get_text("dict")["blocks"]:
        bbox = [round(v, 2) for v in b["bbox"]]
        if b["type"] == 1:
            (running if bbox[3] <= LOGO_Y1 else content).append(
                dict(kind="header_logo" if bbox[3] <= LOGO_Y1 else "image", bbox=bbox))
            continue
        text = "".join(s["text"] for line in b["lines"] for s in line["spans"])
        if not text.strip():
            running.append(dict(kind="header_spacer", bbox=bbox))
            continue
        if bbox[1] >= FOOTER_Y:
            running.append(dict(kind="footer", bbox=bbox, text=text.strip()))
            continue
        spans = [s for line in b["lines"] for s in line["spans"]]
        content.append(dict(kind="text", bbox=bbox, text=text,
                            max_size=round(max(s["size"] for s in spans), 2),
                            fonts=sorted({s["font"].split("+")[-1] for s in spans})))
    content.sort(key=lambda x: (x["bbox"][1], x["bbox"][0]))
    return content, running


def build(doc_cfg, precheck):
    path = os.path.join(SRC, doc_cfg["source_file"])
    rec = precheck[doc_cfg["source_file"]]
    doc = pymupdf.open(path)
    digest = sha256_of(path)
    assert digest == rec["sha256"], "source file changed since the pre-check"
    assert os.path.getsize(path) == rec["bytes"]
    npages = doc.page_count

    # ---------------- collect blocks + heading candidates -------------------
    page_blocks, page_running, heading_blocks = {}, {}, []
    for pno in range(npages):
        content, running = blocks_of(doc.load_page(pno))
        page_blocks[pno + 1], page_running[pno + 1] = content, running
        for b in content:
            if b["kind"] == "text" and b["max_size"] >= 15.0:
                heading_blocks.append(dict(page=pno + 1, y0=b["bbox"][1], size=b["max_size"],
                                           text=b["text"], bbox=b["bbox"]))

    toc = doc.get_toc(simple=False)

    # ---------------- outline section + heading block matching -------------
    by_norm = {}
    for h in heading_blocks:
        by_norm.setdefault(norm_ws(h["text"]), []).append(h)

    outline_secs, used = [], set()
    for idx, (level, title, page, dest) in enumerate(toc):
        dest_y = round(dest["to"].y, 2) if isinstance(dest, dict) and dest.get("to") else None
        match, how = None, ""
        cands = [h for h in by_norm.get(norm_ws(title), []) if abs(h["page"] - page) <= 1]
        if cands:
            cands.sort(key=lambda h: (abs(h["page"] - page), abs(h["y0"] - (dest_y or 0))))
            match, how = cands[0], "exact_text"
        if match is None:
            near = [h for h in heading_blocks
                    if h["page"] == page and abs(h["size"] - LEVEL_SIZE[level]) < 0.6]
            if near and dest_y is not None:
                near.sort(key=lambda h: abs(h["y0"] - dest_y))
                if abs(near[0]["y0"] - dest_y) <= 25:
                    match, how = near[0], "nearest_size"
        if match:
            used.add((match["page"], match["bbox"][1]))
        outline_secs.append(dict(
            outline_index=idx, region_type="section", level=level, title=title,
            start_physical_page=match["page"] if match else page,
            start_y=round(match["y0"] if match else (dest_y or 0) - 10, 2),
            start_bbox=match["bbox"] if match else None,
            heading_match=how or "dest_only",
            heading_block_size=match["size"] if match else None,
            expected_level_size=LEVEL_SIZE[level],
            dest_physical_page=page, dest_y=dest_y,
        ))

    # ---------------- synthetic regions the outline does not cover ----------
    synthetic = [dict(outline_index=None, region_type="front_matter", level=0,
                      title="封面", start_physical_page=1, start_y=0.0,
                      start_bbox=[0.0, 0.0, 595.32, 841.92], heading_match="synthetic",
                      heading_block_size=None, expected_level_size=None,
                      dest_physical_page=1, dest_y=0.0,
                      synthetic_reason="物理 P1 封面：内置书签未收录；文本层乱码，仅作图片引用")]
    for h in heading_blocks:
        if (h["page"], h["bbox"][1]) in used:
            continue
        key = norm_ws(h["text"])
        if key in INDEX_TITLES:
            synthetic.append(dict(
                outline_index=None, region_type=INDEX_TITLES[key], level=0,
                title=key, start_physical_page=h["page"], start_y=h["y0"],
                start_bbox=h["bbox"], heading_match="synthetic",
                heading_block_size=h["size"], expected_level_size=None,
                dest_physical_page=h["page"], dest_y=h["y0"],
                synthetic_reason="印刷目录页：内置书签未收录，不属于规则正文"))
            used.add((h["page"], h["bbox"][1]))

    # ---------------- merge, sort, derive hierarchy -------------------------
    secs = sorted(outline_secs + synthetic,
                  key=lambda s: (s["start_physical_page"], s["start_y"]))
    for i, s in enumerate(secs):
        s["section_id"] = i
        s["start_printed_page"] = s["start_physical_page"] + PRINTED_OFFSET
        s["dest_printed_page"] = s["dest_physical_page"] + PRINTED_OFFSET
        m = re.match(r"^(\d+(?:\.\d+)*)\s+", s["title"])
        s["section_no"] = m.group(1) if m else ""
        s["name"] = s["title"][m.end():].strip() if m else s["title"]

    # parent/path only over outline (level>=1) entries
    stack = []
    for s in secs:
        if s["region_type"] != "section":
            s["parent_id"] = None
            s["path"] = [s["title"]]
            continue
        while stack and secs[stack[-1]]["level"] >= s["level"]:
            stack.pop()
        s["parent_id"] = stack[-1] if stack else None
        s["path"] = [secs[i]["title"] for i in stack] + [s["title"]]
        stack.append(s["section_id"])

    # ---------------- end positions ----------------------------------------
    for i, s in enumerate(secs):
        if i + 1 < len(secs):
            s["end_physical_page"] = secs[i + 1]["start_physical_page"]
            s["end_y"] = secs[i + 1]["start_y"]
        else:
            s["end_physical_page"], s["end_y"] = npages, PAGE_H
    for s in secs:
        s["page_span"] = s["end_physical_page"] - s["start_physical_page"] + 1
        s["spans_multiple_pages"] = s["page_span"] > 1

    # ---------------- assign every block to exactly one region --------------
    breaks = [(s["start_physical_page"], s["start_y"]) for s in secs]

    def find_section(page, y):
        lo, hi = 0, len(breaks)
        while lo < hi:
            mid = (lo + hi) // 2
            if breaks[mid] <= (page, y):
                lo = mid + 1
            else:
                hi = mid
        return lo - 1

    assigned = {s["section_id"]: [] for s in secs}
    page_map = []
    for pno in range(1, npages + 1):
        runs = {}
        for b in page_blocks[pno]:
            sid = find_section(pno, b["bbox"][1])
            if sid < 0:                      # only possible on page 1 above y=0
                sid = 0
            assigned[sid].append((pno, b))
            r = runs.setdefault(sid, dict(section_id=sid, y_from=b["bbox"][1],
                                          y_to=b["bbox"][3], blocks=0, chars=0))
            r["blocks"] += 1
            r["y_to"] = max(r["y_to"], b["bbox"][3])
            if b["kind"] == "text":
                r["chars"] += len(b["text"])
        if runs:
            page_map.append(dict(physical_page=pno, printed_page=pno + PRINTED_OFFSET,
                                 sections=sorted(runs.values(), key=lambda r: r["y_from"])))

    for s in secs:
        got = assigned[s["section_id"]]
        s["block_count"] = len(got)
        s["text_block_count"] = sum(1 for _, b in got if b["kind"] == "text")
        s["image_block_count"] = sum(1 for _, b in got if b["kind"] == "image")
        s["char_count"] = sum(len(b["text"]) for _, b in got if b["kind"] == "text")
        s["pages_with_content"] = sorted({p for p, _ in got})
        s["actual_first_page"] = s["pages_with_content"][0] if s["pages_with_content"] else None
        s["actual_last_page"] = s["pages_with_content"][-1] if s["pages_with_content"] else None
        s["start_matches_first_content_page"] = (s["actual_first_page"] == s["start_physical_page"])
        s["continues_from_previous_page"] = bool(
            s["pages_with_content"] and s["pages_with_content"][0] < s["start_physical_page"])
        s["continues_to_next_page"] = (s["actual_last_page"] is not None
                                       and s["actual_last_page"] > s["end_physical_page"])

    # ---------------- validation -------------------------------------------
    unmatched = [dict(page=h["page"], printed_page=h["page"] + PRINTED_OFFSET, y0=h["y0"],
                      size=h["size"], text=h["text"].strip()[:60])
                 for h in heading_blocks if (h["page"], h["bbox"][1]) not in used]
    same_page_multi = {}
    for p in range(1, npages + 1):
        n = sum(1 for s in secs if s["start_physical_page"] == p)
        if n > 1:
            same_page_multi[p] = n
    matched = sum(1 for s in outline_secs
                  if s["heading_match"] in ("exact_text", "nearest_size"))
    level_size_ok = sum(1 for s in outline_secs
                        if s["heading_block_size"] is not None
                        and abs(s["heading_block_size"] - s["expected_level_size"]) < 0.6)
    total_blocks = sum(len(page_blocks[p]) for p in page_blocks)
    running_blocks = sum(len(page_running[p]) for p in page_running)
    hierarchy = L.validate_hierarchy(secs, toc)

    result = dict(
        doc=dict(doc_id=doc_cfg["doc_id"], version=doc_cfg["version"],
                 source_file=doc_cfg["source_file"],
                 source_path=os.path.join("原始材料", doc_cfg["source_file"]),
                 sha256=digest, bytes=rec["bytes"], page_count=npages,
                 page_size=[595.32, PAGE_H], printed_page_offset=PRINTED_OFFSET,
                 printed_page_rule="印刷页 = 物理页 − 1（预检查已逐页验证）",
                 outline_entries=len(outline_secs),
                 outline_level_counts={str(l): sum(1 for s in outline_secs if s["level"] == l)
                                       for l in (1, 2, 3, 4)},
                 regions_total=len(secs),
                 synthetic_regions=[dict(section_id=s["section_id"], title=s["title"],
                                         region_type=s["region_type"],
                                         physical_page=s["start_physical_page"],
                                         page_span=s["page_span"],
                                         reason=s["synthetic_reason"])
                                    for s in secs if s["region_type"] != "section"],
                 built_at=datetime.datetime.now().isoformat(timespec="seconds"),
                 tool="PyMuPDF %s" % pymupdf.__version__,
                 notes_version_used=False,
                 numbering_rule=dict(
                     level_1="22.0 pt", level_2="18.0 pt", level_3="16.0 pt", level_4="15.0 pt",
                     body_text="10.6 pt", footer_band="y >= 755 pt", header_logo_band="y <= 70 pt")),
        sections=secs,
        page_map=page_map,
        validation=dict(
            sections_total=len(secs),
            outline_sections=len(outline_secs),
            synthetic_regions=len(secs) - len(outline_secs),
            heading_matched=matched,
            heading_match_rate=round(matched / len(outline_secs), 4),
            heading_matched_exact=sum(1 for s in outline_secs
                                      if s["heading_match"] == "exact_text"),
            dest_only=[s["outline_index"] for s in outline_secs
                       if s["heading_match"] == "dest_only"],
            level_size_confirmed=level_size_ok,
            unmatched_block_headings=unmatched,
            unmatched_block_heading_count=len(unmatched),
            pages_with_multiple_section_starts=len(same_page_multi),
            max_sections_starting_on_one_page=max(same_page_multi.values()) if same_page_multi else 1,
            sections_spanning_pages=sum(1 for s in secs if s["spans_multiple_pages"]),
            sections_spanning_pages_outline=sum(1 for s in outline_secs
                                                if s["spans_multiple_pages"]),
            blocks_total=total_blocks,
            blocks_assigned=sum(s["block_count"] for s in secs),
            blocks_lost=total_blocks - sum(s["block_count"] for s in secs),
            running_header_footer_blocks=running_blocks,
            hierarchy_check=hierarchy,
            sections_with_zero_content=[s["section_id"] for s in outline_secs
                                        if s["block_count"] == 0],
            sections_start_not_on_first_content_page=[s["section_id"] for s in secs
                                                      if not s["start_matches_first_content_page"]],
        ),
        same_page_multi_section_starts=same_page_multi,
    )
    doc.close()
    return result


def main():
    precheck = load_precheck()
    for cfg in DOCS:
        print("== building skeleton for", cfg["doc_id"], flush=True)
        res = build(cfg, precheck)
        out = os.path.join(OUT, "%s_章节骨架.json" % cfg["doc_id"].replace("RMUC", ""))
        json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        v = res["validation"]
        print("   regions            ", v["sections_total"],
              "(outline %d + synthetic %d)" % (v["outline_sections"], v["synthetic_regions"]))
        print("   heading matched    ", v["heading_matched"], "/", v["outline_sections"],
              "exact:", v["heading_matched_exact"], " dest_only:", v["dest_only"])
        print("   level size ok      ", v["level_size_confirmed"], "/", v["outline_sections"])
        print("   unmatched headings ", v["unmatched_block_heading_count"],
              [u["text"] for u in v["unmatched_block_headings"]])
        print("   pages w/ >1 start  ", v["pages_with_multiple_section_starts"],
              " max on one page", v["max_sections_starting_on_one_page"])
        print("   spanning pages     ", v["sections_spanning_pages"])
        print("   blocks assigned    ", v["blocks_assigned"], "/", v["blocks_total"],
              " lost:", v["blocks_lost"], " running hdr/ftr:", v["running_header_footer_blocks"])
        print("   zero-content secs  ", v["sections_with_zero_content"])
        print("   start!=first page  ", v["sections_start_not_on_first_content_page"])
        h = v["hierarchy_check"]
        print("   hierarchy check    ", "OK" if h["ok"] else "FAILED",
              "sections=%d synth=%d depth=%d problems=%d" % (
                  h["sections_checked"], h["synthetic_checked"], h["max_depth"], len(h["problems"])))
        print("   written", out, flush=True)


if __name__ == "__main__":
    main()
