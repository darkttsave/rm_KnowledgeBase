#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 5 (phase B2) -- shared helpers for full-text difference discovery.

Only derived from phase-A artefacts; no PDF is opened here.
"""
import os
import re
import json
import math
import difflib
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STRUCT = os.path.join(ROOT, "ai_workplace", "structured")
ALIGN = os.path.join(ROOT, "ai_workplace", "alignment")
OUT = os.path.join(ROOT, "ai_workplace", "diff")
os.makedirs(OUT, exist_ok=True)

PUA_MAP = {"\uf06c": "•", "\uf0d8": "◦"}

# text-bearing body records that go through the body diff
BODY_KINDS = {"paragraph", "diagram_label", "figure_label_row", "formula_fraction_part"}
# records deliberately excluded from the body diff (each gets an explicit status)
EXCLUDED_KINDS = {
    "heading": "章节标题已由阶段 B1 处理（标题对应关系见 章节对应关系.json）",
    "table_caption": "表题随表格走「特殊内容」流程（见 特殊内容差异清单.md）",
    "figure_caption": "图题随插图走「特殊内容」流程（见 特殊内容差异清单.md）",
    "index_entry": "印刷版目录条目，不参与规则正文比对",
    "cover_text": "封面文本层（预检查判定为乱码/缺失），不作为规则正文",
    "inline_icon": "内联小图标，无文本语义",
    "table": "表格主体走「特殊内容」流程",
    "figure": "插图走「特殊内容」流程",
    "formula_fraction": "上下分式走「特殊内容」公式流程",
}

MARKER = re.compile(
    r"^\s*(?:[•◦▪■●○◆◇►▸]"
    r"|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]"
    r"|[（(]\d{1,2}[）)]"
    r"|\d{1,2}[.、．](?!\d)"
    r"|[Rr]\d{1,3}(?=[\s、.．])"
    r"|\[\d{1,2}\]"
    r")+\s*")

# cross-reference tokens: renumbering here is NOT a content change
REF_PATTERNS = [
    re.compile(r"(?:详见|参见|见|参考|依照|按照|根据)[\s“\"']*"
               r"(?:第\s*\d+\s*(?:章|节|条)|[表图]\s*\d+\s*-\s*\d+|\d+(?:\.\d+)+)"),
    re.compile(r"[表图]\s*\d+\s*-\s*\d+"),
    re.compile(r"第\s*\d+\s*(?:章|节|条)"),
    # URLs and book/manual titles are references, not rule parameters
    re.compile(r"https?://[^\s，。；、）)]+"),
    re.compile(r"《[^》]{0,80}》"),
    # multi-level numbering such as 5.5.3.1 is a section reference, never a parameter
    re.compile(r"\d+(?:\.\d+){2,}"),
    # [1] [2] ... are legend / list indices, not parameters
    re.compile(r"\[\d{1,2}\]"),
]
REF_TOKEN = re.compile(r"<\s*REF\s*>")

NUM = re.compile(r"\d+(?:\.\d+)?")
UNIT_TOK = re.compile(
    r"(?:mm/s|mm/s²|m/s|rad/s|°/s|°/s²|kW|kHz|Hz|ms|min|mm|cm|dm|km|kg|g|℃|%|W|J|V|A|s|°|倍|发|台|个|人|秒|分钟|毫秒)(?![A-Za-z])")

SENT_SPLIT = re.compile(r"(?<=[。！？；!?;])")


def load_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_json(path):
    return json.load(open(path, encoding="utf-8"))


def norm(s):
    """comparison normalisation: PUA bullets mapped, all whitespace removed."""
    if not s:
        return ""
    for k, v in PUA_MAP.items():
        s = s.replace(k, v)
    return re.sub(r"\s+", "", s)


def split_marker(s):
    """return (marker, core) where marker is a leading bullet / list number /
    rule id.  Only for comparison."""
    m = MARKER.match(s or "")
    if not m:
        return "", (s or "")
    return m.group(0).strip(), (s or "")[m.end():]


def strip_refs(s):
    """replace cross-reference tokens so that renumbering is not a diff."""
    out = s
    for p in REF_PATTERNS:
        out = p.sub("<REF>", out)
    return out


def ref_tokens(s):
    found = []
    for p in REF_PATTERNS:
        found.extend(p.findall(s))
    return found


def numbers(s):
    return Counter(NUM.findall(strip_refs(s)))


def units(s):
    return Counter(UNIT_TOK.findall(s))


def bigrams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)}


def ratio(a, b):
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def split_sentences(text, max_len=150, min_len=6):
    """Split a paragraph into sentence-ish fragments, keeping punctuation."""
    parts = []
    for seg in SENT_SPLIT.split(text or ""):
        seg = seg.strip()
        if not seg:
            continue
        if len(norm(seg)) > max_len:
            cur = ""
            for piece in re.split(r"(?<=[，、,：:])", seg):
                if cur and len(norm(cur) + norm(piece)) > max_len:
                    parts.append(cur.strip())
                    cur = piece
                else:
                    cur += piece
            if cur.strip():
                parts.append(cur.strip())
        else:
            parts.append(seg)
    merged = []
    for p in parts:
        if merged and len(norm(p)) < min_len:
            merged[-1] = merged[-1] + p
        else:
            merged.append(p)
    return [p for p in merged if norm(p)]


def jaccid(a_set, b_set):
    if not a_set or not b_set:
        return 0.0
    return len(a_set & b_set) / min(len(a_set), len(b_set))


class SentIndex:
    """inverted bigram index with idf weighting, for fast candidate retrieval."""

    def __init__(self, sents):
        self.sents = sents
        self.post = defaultdict(list)
        for i, s in enumerate(sents):
            for g in bigrams(s["core"]):
                self.post[g].append(i)
        n = max(1, len(sents))
        self.idf = {g: math.log(1.0 + n / (1.0 + len(v))) for g, v in self.post.items()}
        self._big = set()

    def top(self, core, k=8, max_post=350):
        """return up to k (idx, approx_score) candidates."""
        bags = bigrams(core)
        if not bags:
            return []
        counts = defaultdict(float)
        for g in bags:
            plist = self.post.get(g)
            if not plist or len(plist) > max_post:
                continue
            w = self.idf.get(g, 1.0)
            for i in plist:
                counts[i] += w
        if not counts:
            return []
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:k]
        return [(i, sc) for i, sc in ranked]


def best_match(index, core, exclude=None, k=12):
    """best (idx, ratio) in the index for a core string."""
    best = (None, 0.0)
    for i, _approx in index.top(core, k=k):
        if exclude and i in exclude:
            continue
        r = ratio(core, index.sents[i]["core"])
        if r > best[1]:
            best = (i, r)
    return best


TERMINATOR = tuple("。！？；：:;!?…")
# records that must not break a paragraph chain (they sit inline)
INLINE_SKIP = {"inline_icon"}


def _stitch(records):
    """Rebuild logical paragraphs.

    Phase A assembles visual lines into paragraphs, but a few paragraphs were
    split into several records (the continuation heuristic missed them).  Left
    as-is, a single rewritten rule turns into "1 delete + 1 add", i.e. exactly the
    kind of formatting-induced false difference B2 must avoid.  So consecutive
    body records inside one section are re-joined when the previous fragment does
    not end with a terminator and the next one does not start a new list item.
    """
    logical = []
    cur = None
    for r in records:
        kind = r.get("block_kind", r.get("record_type"))
        if kind in INLINE_SKIP:
            continue
        if kind not in BODY_KINDS:
            cur = None          # heading / table / figure / caption break the chain
            continue
        text = r.get("norm_text") or ""
        if not text.strip():
            continue
        if cur is not None:
            prev = cur["text"]
            marker_next, _ = split_marker(text)
            if (not prev.rstrip().endswith(TERMINATOR)) and not marker_next:
                cur["text"] = prev + text      # direct concatenation: the wrap only
                cur["recs"].append(r)
                continue
        cur = dict(text=text, recs=[r], lead=r)
        logical.append(cur)
    return logical


def build_sentences(recs, doc_id):
    """turn body records into sentence entries with full provenance."""
    groups = {}
    order = []
    for r in recs:
        if r.get("region_type") != "section":
            continue
        sidx = r["section_index"]
        if sidx not in groups:
            groups[sidx] = []
            order.append(sidx)
        groups[sidx].append(r)

    sents = []
    for sidx in order:
        for para in _stitch(groups[sidx]):
            lead = para["lead"]
            rec_ids = [x["record_id"] for x in para["recs"]]
            kinds = sorted({x.get("block_kind", x.get("record_type")) for x in para["recs"]})
            for j, piece in enumerate(split_sentences(para["text"])):
                marker, core = split_marker(piece)
                cn = norm(core)
                if not cn:
                    continue
                sents.append(dict(
                    idx=len(sents), doc=doc_id,
                    record_id=lead["record_id"], record_ids=rec_ids,
                    record_count=len(rec_ids), block_kind=lead.get("block_kind", lead["record_type"]),
                    block_kinds=kinds, stitched=len(rec_ids) > 1,
                    section_index=sidx,
                    section_no=lead["section"]["section_no"],
                    section_title=lead["section"]["title"],
                    section_path=lead["section"]["path"],
                    physical_page=lead["physical_page"], printed_page=lead["printed_page"],
                    bbox=lead["bbox"],
                    para_text=para["text"],
                    sent_index=j, marker=marker, raw=piece,
                    core=cn, refs=ref_tokens(piece),
                    nums=numbers(piece), units=units(piece),
                ))
    for i, s in enumerate(sents):
        s["idx"] = i
    return sents


def classify_pair(a, b):
    """returns (diff_type, evidence dict) for a matched sentence pair."""
    ev = {}
    if a["core"] == b["core"]:
        if a["marker"] != b["marker"]:
            ev["marker_change"] = {"2026": a["marker"], "2027": b["marker"]}
            return "编号变化（不计内容变化）", ev
        return "内容一致", ev

    # reference renumbering only?
    ra = a["raw"] if not a["refs"] else None
    refs_a, refs_b = a["refs"], b["refs"]
    if refs_a or refs_b:
        ev["refs"] = {"2026": refs_a, "2027": refs_b}
    core_wo_a = norm(strip_refs(a["raw"]))
    core_wo_b = norm(strip_refs(b["raw"]))
    if core_wo_a == core_wo_b and refs_a != refs_b:
        ev["ref_renumber"] = True
        return "引用编号更新（不计内容变化）", ev

    # compare the *presence* of numbers/units, not their occurrence counts: a
    # sentence that merely repeats "2mm" twice must not look like a param change
    na, nb = dict(a["nums"]), dict(b["nums"])
    if set(na) != set(nb):
        ev["numbers"] = {"added": sorted(set(nb) - set(na)),
                          "removed": sorted(set(na) - set(nb)),
                          "occurrence_delta": {k: nb.get(k, 0) - na.get(k, 0)
                                                for k in set(na) | set(nb)
                                                if nb.get(k, 0) != na.get(k, 0)}}
    ua, ub = dict(a["units"]), dict(b["units"])
    if set(ua) != set(ub):
        ev["units"] = {"added": sorted(set(ub) - set(ua)),
                        "removed": sorted(set(ua) - set(ub))}

    r = ratio(a["core"], b["core"])
    ev["char_ratio"] = round(r, 4)
    ev["len"] = {"2026": len(a["core"]), "2027": len(b["core"])}

    if ev.get("numbers") or ev.get("units"):
        return "实质修改候选", ev
    if r >= 0.90:
        return "文字调整候选", ev
    return "实质修改候选", ev


DIFF_TYPES = ["内容一致", "编号变化（不计内容变化）", "引用编号更新（不计内容变化）",
              "文字调整候选", "实质修改候选", "新增候选", "删除候选", "迁移或重组候选"]

# priority used for the human-review list
REVIEW_PRIORITY = {
    "实质修改候选": "high",
    "新增候选": "high",
    "删除候选": "high",
    "迁移或重组候选": "medium",
    "文字调整候选": "low",
}
