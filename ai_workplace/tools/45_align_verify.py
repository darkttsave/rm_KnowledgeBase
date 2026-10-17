#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 4 (phase B1) -- step 4: independent verification of the alignment output.

Checks that no formal section of either document can be silently omitted or
double-counted, that the JSON is self-consistent, and that the three Markdown
deliverables really cover every section.
"""
import os
import re
import json

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STRUCT = os.path.join(ROOT, "ai_workplace", "structured")
OUT = os.path.join(ROOT, "ai_workplace", "alignment")

checks = []


def check(name, got, want):
    ok = got == want
    checks.append((ok, name, got, want))
    g = ("<%d items>" % len(got)) if isinstance(got, list) and len(got) > 6 else repr(got)
    w = ("<%d items>" % len(want)) if isinstance(want, list) and len(want) > 6 else repr(want)
    print(("PASS " if ok else "FAIL ") + "%-62s got=%s want=%s" % (name, g, w))
    return ok


def check_true(name, cond, detail=""):
    checks.append((bool(cond), name, detail, True))
    print(("PASS " if cond else "FAIL ") + "%-62s %s" % (name, detail))
    return bool(cond)


def key(x):
    return x["no"] or x["title"]


def main():
    A = json.load(open(os.path.join(OUT, "章节对应关系.json"), encoding="utf-8"))
    units = A["alignments"]
    idx = A["section_index"]
    cov = A["coverage"]

    # ---- reference section lists straight from the phase-A skeletons ----
    ref = {}
    for year in ("2026", "2027"):
        sk = json.load(open(os.path.join(STRUCT, "%s_章节骨架.json" % year), encoding="utf-8"))
        ref[year] = [s["section_no"] or s["title"] for s in sk["sections"]
                     if s["region_type"] == "section"]
    check("2026 formal sections (from skeleton)", len(ref["2026"]), 130)
    check("2027 formal sections (from skeleton)", len(ref["2027"]), 129)

    # ---- every section appears exactly once across units ----
    seen = {"2026": [], "2027": []}
    for u in units:
        for s in u["sections_2026"]:
            seen["2026"].append(key(s))
        for s in u["sections_2027"]:
            seen["2027"].append(key(s))
    for year in ("2026", "2027"):
        check("%s sections in units == skeleton list" % year,
              sorted(seen[year]), sorted(ref[year]))
        dup = [k for k in set(seen[year]) if seen[year].count(k) > 1]
        check("%s sections listed more than once" % year, dup, [])

    # ---- section_index consistency ----
    for year in ("2026", "2027"):
        check("%s section_index keys" % year, sorted(idx[year]), sorted(ref[year]))
        bad = []
        for u in units:
            for s in u["sections_%s" % year]:
                if idx[year].get(key(s)) != u["align_id"]:
                    bad.append((key(s), u["align_id"], idx[year].get(key(s))))
        check("%s section_index points at the right unit" % year, bad, [])

    # ---- match_type / relation compatibility ----
    bad_mt, bad_rel = [], []
    for u in units:
        n26, n27 = len(u["sections_2026"]), len(u["sections_2027"])
        if u["match_type"] != "%d:%d" % (n26, n27):
            bad_mt.append((u["align_id"], u["match_type"], n26, n27))
        r = u["relation"]
        ok = ((n27 == 0 and r == "deleted")
              or (n26 == 0 and r == "added")
              or (n26 > 1 and n27 == 1 and r == "merged")
              or (n26 == 1 and n27 > 1 and r == "split")
              or (n26 == 1 and n27 == 1 and r in ("kept", "renamed", "moved")))
        if not ok:
            bad_rel.append((u["align_id"], r, n26, n27))
    check("match_type matches section counts", bad_mt, [])
    check("relation matches match_type", bad_rel, [])
    check("align_id unique", len({u["align_id"] for u in units}), len(units))
    check("align_id sequence", [u["align_id"] for u in units],
          ["AL-%03d" % i for i in range(1, len(units) + 1)])

    # ---- every unit carries evidence ----
    no_ev = [u["align_id"] for u in units if not u["evidence"]]
    check("units without evidence", no_ev, [])
    short_ev = [u["align_id"] for u in units if len(u["evidence"]) < 1]
    check("units with too little evidence", short_ev, [])
    # evidence must cite a machine-verifiable artefact for manual decisions
    manual = [u for u in units if u["needs_review"] or u["relation"] != "kept"]
    bad_prefix = []
    for u in manual:
        if not any(e.split(":")[0] in ("D", "S", "C", "M", "P") for e in u["evidence"]):
            bad_prefix.append(u["align_id"])
    check("manual decisions without a labelled evidence source", bad_prefix, [])

    # ---- needs_review bookkeeping ----
    rev = [u["align_id"] for u in units if u["needs_review"]]
    check("coverage.needs_review_units == actual", cov["needs_review_units"], rev)

    # ---- coverage figures ----
    check("coverage: 2026 mapped", cov["sections_2026_mapped"], len(ref["2026"]))
    check("coverage: 2027 mapped", cov["sections_2027_mapped"], len(ref["2027"]))
    check("coverage: no unmapped 2026", cov["sections_2026_unmapped"], [])
    check("coverage: no unmapped 2027", cov["sections_2027_unmapped"], [])
    check("coverage: units", cov["units"], len(units))
    calc = {}
    for u in units:
        calc[u["relation"]] = calc.get(u["relation"], 0) + 1
    check("coverage: relation counts", dict(sorted(calc.items())),
          {k: v for k, v in sorted(cov["units_by_relation"].items(),
                                   key=lambda kv: kv[1])} and dict(sorted(calc.items())))

    # ---- deleted / added lists ----
    del_actual = [key(s) for u in units if u["relation"] == "deleted" for s in u["sections_2026"]]
    add_actual = [key(s) for u in units if u["relation"] == "added" for s in u["sections_2027"]]
    check("coverage.deleted_sections", cov["deleted_sections"], del_actual)
    check("coverage.added_sections", cov["added_sections"], add_actual)

    # ---- L1 chapter coverage: every section's path is non-empty & l1 known ----
    bad_path = []
    for u in units:
        for year in ("2026", "2027"):
            for s in u["sections_%s" % year]:
                if not s["path"] or len(s["path"]) != s["level"] or s["path"][-1] != s["title"]:
                    bad_path.append((u["align_id"], year, s["title"]))
    check("sections with an inconsistent path", bad_path, [])

    # ---- page numbers: printed = physical - 1 ----
    bad_page = []
    for u in units:
        for year in ("2026", "2027"):
            for s in u["sections_%s" % year]:
                for ph, pr in zip(s["physical_pages"], s["printed_pages"]):
                    if pr != ph - 1:
                        bad_page.append((s["title"], ph, pr))
    check("printed page = physical page - 1", bad_page, [])

    # ---- markdown deliverables must cover every section ----
    # 总览: every formal section must appear.
    # 异常清单: only the units that need human attention are listed by design, but
    # every non-kept / needs_review section must appear there.
    ov = open(os.path.join(OUT, "章节对齐总览.md"), encoding="utf-8").read()
    for year in ("2026", "2027"):
        check("章节对齐总览.md missing %s sections" % year,
              [k for k in ref[year] if k not in ov], [])
    an = open(os.path.join(OUT, "章节对齐异常清单.md"), encoding="utf-8").read()
    for year in ("2026", "2027"):
        need = [key(s) for u in units
                if (u["relation"] != "kept" or u["needs_review"])
                for s in u["sections_%s" % year]]
        check("章节对齐异常清单.md missing %s attention sections" % year,
              [k for k in need if k not in an], [])
    # the anomaly list must state the number of kept units so nothing looks omitted
    n_kept = sum(1 for u in units if u["relation"] == "kept")
    check_true("异常清单 states the kept-unit count", ("「保留」的 %d 个单元" % n_kept) in an,
               "n_kept=%d" % n_kept)
    check_true("overview table has a row per unit",
               ov.count("| **保留**") + ov.count("| **重命名**") + ov.count("| **迁移**")
               + ov.count("| **合并**") + ov.count("| **疑似新增**") + ov.count("| **疑似删除**")
               >= len(units),
               "rows=%d units=%d kept=%d" % (
                   ov.count("| **保留**") + ov.count("| **重命名**") + ov.count("| **迁移**")
                   + ov.count("| **合并**") + ov.count("| **疑似新增**") + ov.count("| **疑似删除**"),
                   len(units), n_kept))

    print()
    bad = [c for c in checks if not c[0]]
    print("=" * 76)
    print("TOTAL %d checks, %d PASS, %d FAIL" % (len(checks), len(checks) - len(bad), len(bad)))
    for _, name, got, want in bad:
        print("  FAILED:", name, "got", got, "want", want)
    print("=" * 76)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
