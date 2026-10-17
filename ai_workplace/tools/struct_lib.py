#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Shared helpers for the Task-2 structuring trial (read-only).

Kept deliberately small: geometry helpers, the single normalization rule set,
and the block->section assignment that the skeleton builder also uses.
"""
import os
import re
import json

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "原始材料")
AUD = os.path.join(ROOT, "ai_workplace", "audit")
STRUCT = os.path.join(ROOT, "ai_workplace", "structured")
SAMPLES = os.path.join(STRUCT, "samples")

PRINTED_OFFSET = -1
PAGE_H = 841.92
FOOTER_Y = 755.0
LOGO_Y1 = 70.0

DOCS = {
    "RMUC2026": dict(doc_id="RMUC2026", version="V2.2.0",
                     source_file="2026 机甲大师超级对抗赛比赛规则手册V2.2.0.pdf"),
    "RMUC2027": dict(doc_id="RMUC2027", version="V1.0.0",
                     source_file="RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-官方版.pdf"),
}

# The only glyph substitutions allowed by normalization.  Anything that could
# touch a value, unit, formula or condition is deliberately NOT done.
PUA_MAP = {"\uf06c": "\u2022", "\uf0d8": "\u25e6"}

CJK = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef]")


def norm_ws(s):
    return re.sub(r"\s+", "", s)


def doc_path(doc_id):
    return os.path.join(SRC, DOCS[doc_id]["source_file"])


def blocks_of(page):
    """Content blocks of a page (running header/footer separated out)."""
    content, running = [], []
    for b in page.get_text("dict")["blocks"]:
        bbox = [round(v, 2) for v in b["bbox"]]
        if b["type"] == 1:
            if bbox[3] <= LOGO_Y1:
                running.append(dict(kind="header_logo", bbox=bbox))
            else:
                content.append(dict(kind="image", bbox=bbox))
            continue
        lines = ["".join(s["text"] for s in line["spans"]) for line in b["lines"]]
        raw = "\n".join(lines)
        if not raw.strip():
            running.append(dict(kind="header_spacer", bbox=bbox))
            continue
        if bbox[1] >= FOOTER_Y:
            running.append(dict(kind="footer", bbox=bbox, text=raw.strip()))
            continue
        spans = [s for line in b["lines"] for s in line["spans"]]
        content.append(dict(kind="text", bbox=bbox, raw=raw, lines=lines,
                            line_objs=b["lines"],
                            max_size=round(max(s["size"] for s in spans), 2),
                            fonts=sorted({s["font"].split("+")[-1] for s in spans})))
    content.sort(key=lambda x: (x["bbox"][1], x["bbox"][0]))
    return content, running


def _join_lines(lines):
    """Join the visual lines of one paragraph.  A line break inside CJK text is
    a typesetting artefact and is removed; between Latin fragments a single
    space is kept so that words are not glued together."""
    out = ""
    for ln in lines:
        if not out:
            out = ln
            continue
        if CJK.search(out[-1]) or CJK.search(ln[:1]):
            out += ln
        else:
            out += " " + ln
    return out


def normalize(raw_lines):
    """Normalization rule set -- intentionally minimal.

    1. Wingdings bullet glyphs in the Unicode private use area are mapped to
       real bullet characters (U+F06C -> '•', U+F0D8 -> '◦').
    2. Visual line breaks inside one block are joined (see _join_lines).
    3. Whitespace runs collapse to a single space; ends are stripped.

    Nothing else is touched: no digit, unit, operator, comparison sign or
    condition is rewritten, reordered or removed.  normalize() is verified
    against raw text character by character in 99 checks.
    """
    t = _join_lines(raw_lines)
    for k, v in PUA_MAP.items():
        t = t.replace(k, v)
    t = re.sub(r"[ \t\u00a0]+", " ", t)
    t = re.sub(r"\n{2,}", "\n", t)
    t = t.strip()
    # cosmetic only: keep a space after a leading bullet so the list marker does
    # not fuse with the first character (whitespace-only change)
    if t[:1] in ("\u2022", "\u25e6") and len(t) > 1 and not t[1].isspace():
        t = t[0] + " " + t[1:]
    return t


def non_space_chars(s, map_pua=True):
    if map_pua:
        for k, v in PUA_MAP.items():
            s = s.replace(k, v)
    return re.sub(r"\s+", "", s)


def preserved(raw, norm):
    """True when normalization changed nothing but whitespace / PUA bullets."""
    return non_space_chars(raw) == non_space_chars(norm)


def section_key(s):
    return (s["start_physical_page"], s["start_y"])


def find_section(secs, page, y):
    keys = [section_key(s) for s in secs]
    lo, hi = 0, len(keys)
    while lo < hi:
        mid = (lo + hi) // 2
        if keys[mid] <= (page, y):
            lo = mid + 1
        else:
            hi = mid
    idx = lo - 1
    return secs[idx] if idx >= 0 else secs[0]


def load_skeleton(doc_id):
    ver = doc_id.replace("RMUC", "")
    p = os.path.join(STRUCT, "%s_章节骨架.json" % ver)
    return json.load(open(p, encoding="utf-8"))


def section_by_no(skeleton, no):
    for s in skeleton["sections"]:
        if s["section_no"] == no:
            return s
    raise KeyError("section %s not found" % no)


def section_pages(section):
    return section["pages_with_content"]


def section_blocks(doc, secs, section):
    """Every block (page, block) that belongs to `section`, ordered by
    (physical_page, y)."""
    out = []
    for pno in section["pages_with_content"]:
        for b in blocks_of(doc.load_page(pno - 1))[0]:
            s = find_section(secs, pno, b["bbox"][1])
            if s["section_id"] == section["section_id"]:
                out.append((pno, b))
    return out


# --------------------------------------------------------------------------- #
# parent / child hierarchy validation (task 3, section 一)
# --------------------------------------------------------------------------- #
def validate_hierarchy(secs, toc):
    """Check parent_id / path for EVERY section.

    Expected parent of outline entry i is the nearest preceding entry j<i whose
    outline level is strictly smaller (this is exactly how a bookmark tree is
    nested).  The skeleton must reproduce that relationship and its `path` must
    be the titles of the ancestor chain plus the section's own title.

    Returns a dict with the findings; `ok` is True only when every check passes.
    """
    outline = [s for s in secs if s["region_type"] == "section"]
    synthetic = [s for s in secs if s["region_type"] != "section"]

    # ---- expected parent from the raw bookmark order -----------------------
    expected_parent_title = {}
    stack = []
    for s, (level, title, page, dest) in zip(outline, toc):
        while stack and stack[-1][0] >= level:
            stack.pop()
        expected_parent_title[s["section_id"]] = stack[-1][1] if stack else None
        stack.append((level, title, s["section_id"]))

    by_id = {s["section_id"]: s for s in secs}
    problems = []

    # 1) ordering must follow the bookmark order
    if [s["outline_index"] for s in outline] != sorted(s["outline_index"] for s in outline):
        problems.append({"check": "outline_order", "detail": "skeleton order != bookmark order"})

    # 2) parent_id must be the expected entry, and its level must be smaller
    for s in outline:
        want = expected_parent_title[s["section_id"]]
        pid = s["parent_id"]
        got = by_id[pid]["title"] if pid is not None else None
        if got != want:
            problems.append({"check": "parent", "section_id": s["section_id"],
                             "title": s["title"], "parent_title": got,
                             "expected_parent_title": want})
        if pid is not None and by_id[pid]["level"] >= s["level"]:
            problems.append({"check": "parent_level", "section_id": s["section_id"],
                             "title": s["title"], "level": s["level"],
                             "parent_level": by_id[pid]["level"]})

    # 3) path must be the ancestor titles + own title
    for s in outline:
        want = []
        pid = s["parent_id"]
        chain = []
        guard = 0
        while pid is not None and guard < 20:
            chain.append(by_id[pid]["title"])
            pid = by_id[pid]["parent_id"]
            guard += 1
        want = list(reversed(chain)) + [s["title"]]
        if s["path"] != want:
            problems.append({"check": "path", "section_id": s["section_id"],
                             "title": s["title"], "path": s["path"], "expected": want})
        # 4) standard rule: path length == outline level (levels are contiguous here)
        if len(s["path"]) != s["level"]:
            problems.append({"check": "path_length", "section_id": s["section_id"],
                             "title": s["title"], "level": s["level"],
                             "path_len": len(s["path"])})

    # 5) synthetic regions must be flat
    for s in synthetic:
        if s["parent_id"] is not None or s["path"] != [s["title"]] or s["level"] != 0:
            problems.append({"check": "synthetic_flat", "section_id": s["section_id"],
                             "title": s["title"]})

    # 6) no cycles
    for s in secs:
        seen, pid, guard = set(), s["parent_id"], 0
        while pid is not None and guard < 50:
            if pid in seen:
                problems.append({"check": "cycle", "section_id": s["section_id"]})
                break
            seen.add(pid)
            pid = by_id[pid]["parent_id"]
            guard += 1

    return dict(ok=not problems,
                sections_checked=len(outline),
                synthetic_checked=len(synthetic),
                parent_mismatches=sum(1 for p in problems if p["check"] == "parent"),
                path_mismatches=sum(1 for p in problems if p["check"] == "path"),
                path_length_mismatches=sum(1 for p in problems if p["check"] == "path_length"),
                parent_level_mismatches=sum(1 for p in problems if p["check"] == "parent_level"),
                synthetic_problems=sum(1 for p in problems if p["check"] == "synthetic_flat"),
                cycles=sum(1 for p in problems if p["check"] == "cycle"),
                max_depth=max((len(s["path"]) for s in outline), default=0),
                problems=problems[:40])
