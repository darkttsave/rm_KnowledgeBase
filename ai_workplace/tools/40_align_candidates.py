#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 4 (phase B1) -- step 1: generate chapter-alignment CANDIDATES with
explicit, reproducible evidence.

No PDF parsing: everything is derived from the phase-A skeletons and JSONL.

Evidence produced per section pair:
  * name / title character-bigram similarity
  * content character-bigram cosine (paragraphs + table cell text)
  * clause-level routing: every clause of a 2026 section is routed to its best
    2027 section (and vice versa).  The share matrix is what makes merges and
    splits visible instead of guessing from numbering.
  * page position prior (weak, never decisive)

Output: ai_workplace/alignment/align_candidates.json + a console digest.
"""
import os
import re
import json
import math
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STRUCT = os.path.join(ROOT, "ai_workplace", "structured")
OUT = os.path.join(ROOT, "ai_workplace", "alignment")
os.makedirs(OUT, exist_ok=True)

DOCS = {"2026": "RMUC2026", "2027": "RMUC2027"}

PUNCT = re.compile(r"[\s\u3000-\u303f\uff00-\uffef!-/:-@\[-`{-~]+")
CLAUSE_SPLIT = re.compile(r"[。！？；!?;]+")
SUB_SPLIT = re.compile(r"[，、,]+")
CJK = re.compile(r"[\u4e00-\u9fff]")


def norm_text(s):
    return PUNCT.sub("", s or "")


def bigrams(s):
    s = norm_text(s)
    return Counter(s[i:i + 2] for i in range(len(s) - 1))


def bigram_set(s):
    s = norm_text(s)
    return set(s[i:i + 2] for i in range(len(s) - 1))


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cosine(ca, cb):
    if not ca or not cb:
        return 0.0
    common = set(ca) & set(cb)
    num = sum(ca[k] * cb[k] for k in common)
    da = math.sqrt(sum(v * v for v in ca.values()))
    db = math.sqrt(sum(v * v for v in cb.values()))
    return num / (da * db) if da and db else 0.0


def load(doc_key):
    sk = json.load(open(os.path.join(STRUCT, "%s_章节骨架.json" % doc_key), encoding="utf-8"))
    recs = defaultdict(list)
    for line in open(os.path.join(STRUCT, "%s_结构化.jsonl" % doc_key), encoding="utf-8"):
        r = json.loads(line)
        recs[r["section_index"]].append(r)
    return sk, recs


def section_content(recs):
    """Rule-bearing text of a section: paragraphs, table cell text and captions.
    Headings / index entries / labels are excluded (titles are compared
    separately)."""
    parts = []
    for r in recs:
        k = r.get("block_kind")
        if k == "paragraph":
            parts.append(r.get("norm_text") or "")
        elif k == "table":
            if r.get("caption"):
                parts.append(r["caption"])
            for row in r.get("grid_raw") or []:
                for c in row:
                    if c and c.strip():
                        parts.append(c)
        elif k in ("table_caption", "figure_caption"):
            parts.append(r.get("norm_text") or "")
    return "\n".join(parts)


def clauses(text, min_len=10):
    out = []
    for seg in CLAUSE_SPLIT.split(text):
        seg = seg.strip()
        if len(norm_text(seg)) >= 40:
            out.extend(s.strip() for s in SUB_SPLIT.split(seg) if len(norm_text(s)) >= min_len)
        elif len(norm_text(seg)) >= min_len:
            out.append(seg)
    return out


def build_side(doc_key):
    sk, recs = load(doc_key)
    rows = []
    for s in sk["sections"]:
        if s["region_type"] != "section":
            continue
        text = section_content(recs.get(s["section_id"], []))
        rows.append(dict(
            id=s["section_id"], no=s["section_no"], title=s["title"], name=s["name"],
            level=s["level"], path=s["path"],
            pages=s["pages_with_content"],
            printed=[p - 1 for p in s["pages_with_content"]],
            chars=len(norm_text(text)),
            tables=sum(1 for r in recs.get(s["section_id"], []) if r["record_type"] == "table"),
            figures=sum(1 for r in recs.get(s["section_id"], []) if r.get("block_kind") == "figure"),
            text=text,
            name_grams=bigram_set(s["name"]),
            content_grams=bigrams(text),
        ))
    return sk, rows


def main():
    sk26, rows26 = build_side("2026")
    sk27, rows27 = build_side("2027")
    print("sections: 2026=%d 2027=%d" % (len(rows26), len(rows27)))

    # ---------- section-level similarity ----------
    for a in rows26:
        for b in rows27:
            b.setdefault("_", None)
    name_sim = {}
    cont_sim = {}
    for a in rows26:
        for b in rows27:
            name_sim[(a["id"], b["id"])] = jaccard(a["name_grams"], b["name_grams"])
            cont_sim[(a["id"], b["id"])] = cosine(a["content_grams"], b["content_grams"])

    def num_prior(a, b):
        if a["no"] and a["no"] == b["no"]:
            return 1.0
        if a["no"] and b["no"] and a["no"].split(".")[0] == b["no"].split(".")[0]:
            return 0.4
        return 0.0

    def combined(a, b):
        return (0.45 * name_sim[(a["id"], b["id"])]
                + 0.40 * cont_sim[(a["id"], b["id"])]
                + 0.10 * num_prior(a, b)
                + 0.05 * (1.0 if a["level"] == b["level"] else 0.0))

    for a in rows26:
        cand = sorted(rows27, key=lambda b: -combined(a, b))[:5]
        a["candidates"] = [dict(id=b["id"], no=b["no"], title=b["title"],
                                name_sim=round(name_sim[(a["id"], b["id"])], 3),
                                content_sim=round(cont_sim[(a["id"], b["id"])], 3),
                                score=round(combined(a, b), 3)) for b in cand]
    for b in rows27:
        cand = sorted(rows26, key=lambda a: -combined(a, b))[:5]
        b["candidates"] = [dict(id=a["id"], no=a["no"], title=a["title"],
                                name_sim=round(name_sim[(a["id"], b["id"])], 3),
                                content_sim=round(cont_sim[(a["id"], b["id"])], 3),
                                score=round(combined(a, b), 3)) for a in cand]

    # ---------- clause routing 2026 -> 2027 ----------
    sets27 = {b["id"]: bigram_set(b["text"]) for b in rows27}
    sets26 = {a["id"]: bigram_set(a["text"]) for a in rows26}
    route26 = defaultdict(Counter)          # 2026 id -> Counter(2027 id)
    total26 = Counter()
    for a in rows26:
        for cl in clauses(a["text"]):
            g = bigram_set(cl)
            if len(g) < 5:
                continue
            total26[a["id"]] += 1
            best, best_s = None, 0.0
            for b in rows27:
                s = len(g & sets27[b["id"]]) / len(g)
                if s > best_s:
                    best, best_s = b["id"], s
            if best is not None and best_s >= 0.6:
                route26[a["id"]][best] += 1

    route27 = defaultdict(Counter)
    total27 = Counter()
    for b in rows27:
        for cl in clauses(b["text"]):
            g = bigram_set(cl)
            if len(g) < 5:
                continue
            total27[b["id"]] += 1
            best, best_s = None, 0.0
            for a in rows26:
                s = len(g & sets26[a["id"]]) / len(g)
                if s > best_s:
                    best, best_s = a["id"], s
            if best is not None and best_s >= 0.6:
                route27[b["id"]][best] += 1

    by26 = {a["id"]: a for a in rows26}
    by27 = {b["id"]: b for b in rows27}

    def route_view(counter, total, targets):
        if not total:
            return []
        return [dict(id=k, no=targets[k]["no"], title=targets[k]["title"],
                     clauses=counter[k], share=round(counter[k] / total, 2))
                for k in sorted(counter, key=lambda k: -counter[k])[:4]]

    # incoming view: who routes INTO this section
    incoming26 = defaultdict(Counter)
    for b_id, c in route27.items():
        for a_id, n in c.items():
            incoming26[a_id][b_id] += n
    incoming27 = defaultdict(Counter)
    for a_id, c in route26.items():
        for b_id, n in c.items():
            incoming27[b_id][a_id] += n

    for a in rows26:
        a["routes_to"] = route_view(route26[a["id"]], total26[a["id"]], by27)
        a["routed_from"] = route_view(incoming26[a["id"]],
                                      sum(incoming26[a["id"]].values()), by27)
        a["clauses"] = total26[a["id"]]
    for b in rows27:
        b["routes_to"] = route_view(route27[b["id"]], total27[b["id"]], by26)
        b["routed_from"] = route_view(incoming27[b["id"]],
                                      sum(incoming27[b["id"]].values()), by26)
        b["clauses"] = total27[b["id"]]

    # ---------- console digest ----------
    # ---- automatic proposal: exact name (number stripped) is decisive ----
    auto = []
    used27 = set()
    used26 = set()
    for a in rows26:
        exact = [b for b in rows27 if b["id"] not in used27
                 and norm_text(a["name"]) == norm_text(b["name"])]
        if len(exact) == 1:
            b = exact[0]
            auto.append(dict(a=a["id"], b=b["id"],
                             relation="kept" if a["no"] == b["no"] else "renumbered",
                             basis="title without number is identical",
                             name_sim=round(name_sim[(a["id"], b["id"])], 3),
                             content_sim=round(cont_sim[(a["id"], b["id"])], 3)))
            used26.add(a["id"])
            used27.add(b["id"])
    unres_26 = [a for a in rows26 if a["id"] not in used26]
    unres_27 = [b for b in rows27 if b["id"] not in used27]

    print("\n=== auto-matched by identical title-without-number: %d ===" % len(auto))
    print("\n=== still open: 2026 (%d) ===" % len(unres_26))
    for a in unres_26:
        c = a["candidates"]
        print("  2026 %-10s L%d %-24s chars=%-5d top: %s"
              % (a["no"] or a["title"][:10], a["level"], a["title"][:24], a["chars"],
                 " | ".join("%s/%s (n%.2f c%.2f s%.2f)" % (x["no"] or x["title"][:8], x["title"][:10],
                                                          x["name_sim"], x["content_sim"], x["score"])
                            for x in c[:3])))
        if a["routes_to"]:
            print("        routes ->", [(r["no"], r["share"]) for r in a["routes_to"]])
    print("\n=== still open: 2027 (%d) ===" % len(unres_27))
    for b in unres_27:
        c = b["candidates"]
        print("  2027 %-10s L%d %-24s chars=%-5d top: %s"
              % (b["no"] or b["title"][:10], b["level"], b["title"][:24], b["chars"],
                 " | ".join("%s/%s (n%.2f c%.2f s%.2f)" % (x["no"] or x["title"][:8], x["title"][:10],
                                                          x["name_sim"], x["content_sim"], x["score"])
                            for x in c[:3])))
        if b["routes_to"]:
            print("        routes ->", [(r["no"], r["share"]) for r in b["routes_to"]])
        if b["routed_from"]:
            print("        receives <-", [(r["no"], r["share"]) for r in b["routed_from"]])

    print("\n=== sections with NO routed target (potential deletes / new mechanisms) ===")
    for a in rows26:
        if a["chars"] >= 100 and not a["routes_to"]:
            print("  2026 %-10s %-26s clauses=%-3d best=%s"
                  % (a["no"] or a["title"], a["title"][:26], a["clauses"],
                     (a["candidates"][0]["title"][:26], a["candidates"][0]["score"]) if a["candidates"] else None))
    for b in rows27:
        if b["chars"] >= 100 and not b["routes_to"]:
            print("  2027 %-10s %-26s clauses=%-3d best=%s"
                  % (b["no"] or b["title"], b["title"][:26], b["clauses"],
                     (b["candidates"][0]["title"][:26], b["candidates"][0]["score"]) if b["candidates"] else None))

    print("\n=== multi-target routing (split / merge evidence) ===")
    for a in rows26:
        if len([r for r in a["routes_to"] if r["share"] >= 0.2]) >= 2:
            print("  2026 %-10s %-24s -> %s" % (a["no"] or a["title"], a["title"][:24],
                  [(r["no"], r["share"]) for r in a["routes_to"] if r["share"] >= 0.15]))
    for b in rows27:
        if len([r for r in b["routed_from"] if r["share"] >= 0.2]) >= 2:
            print("  2027 %-10s %-24s <- %s" % (b["no"] or b["title"], b["title"][:24],
                  [(r["no"], r["share"]) for r in b["routed_from"] if r["share"] >= 0.15]))

    out = dict(
        generated=__import__("datetime").datetime.now().isoformat(timespec="seconds"),
        method=dict(
            name_sim="character-bigram Jaccard of the title without its number",
            content_sim="character-bigram cosine of paragraph text + table cell text + captions",
            combined="0.45*name + 0.40*content + 0.10*number_prior + 0.05*level_prior",
            routing="each clause (>=10 chars) is routed to the section with the highest "
                    "bigram containment (>=0.6); the share matrix exposes merges/splits",
            notes="candidates only -- final decisions are in 41_align_decide.py with recorded evidence"),
        sections_2026=[{k: v for k, v in a.items()
                        if k not in ("text", "content_grams", "name_grams")} for a in rows26],
        sections_2027=[{k: v for k, v in b.items()
                        if k not in ("text", "content_grams", "name_grams")} for b in rows27],
        auto=auto,
    )
    json.dump(out, open(os.path.join(OUT, "align_candidates.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\nwritten", os.path.join(OUT, "align_candidates.json"))
    print("auto-matched %d pairs; unresolved 2026=%d 2027=%d"
          % (len(auto), len(unres_26), len(unres_27)))


if __name__ == "__main__":
    main()
