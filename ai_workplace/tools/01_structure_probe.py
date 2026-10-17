#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase A pre-check -- part 1/3: identity, structure, per-page text quality.

Read-only: opens the official PDFs and writes JSON/TXT under ai_workplace/audit/.
"""
import os
import sys
import json
import hashlib
import re
import unicodedata

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "原始材料")
OUT = os.path.join(ROOT, "ai_workplace", "audit")
os.makedirs(OUT, exist_ok=True)

PUA = lambda ch: 0xE000 <= ord(ch) <= 0xF8FF or 0xF0000 <= ord(ch) <= 0x10FFFD


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def header_version(path):
    with open(path, "rb") as f:
        head = f.read(1024)
    m = re.search(rb"%PDF-(\d\.\d)", head)
    return m.group(1).decode() if m else None


def classify(text):
    st = dict(total=len(text), cjk=0, ascii_=0, digit=0, space=0,
              pua=0, fffd=0, ctrl=0, other=0)
    for ch in text:
        o = ord(ch)
        if ch == "\ufffd":
            st["fffd"] += 1
        elif PUA(ch):
            st["pua"] += 1
        elif o < 0x20 or o == 0x7F:
            st["ctrl"] += 1
        elif ch.isspace():
            st["space"] += 1
        elif 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0x3000 <= o <= 0x303F \
                or 0xFF00 <= o <= 0xFFEF or 0x20000 <= o <= 0x2FA1F:
            st["cjk"] += 1
        elif ch.isdigit():
            st["digit"] += 1
        elif o < 128:
            st["ascii_"] += 1
        else:
            st["other"] += 1
    return st


def page_report(page, pno):
    raw = page.get_text("rawdict")
    text = page.get_text("text")
    words = page.get_text("words")
    natural = page.get_text("text", sort=False)
    ordered = page.get_text("text", sort=True)

    n_lines = n_spans = n_chars = n_img_blocks = 0
    fonts = set()
    sizes = set()
    span_bbox = None
    for blk in raw["blocks"]:
        if blk["type"] == 1:
            n_img_blocks += 1
            continue
        for line in blk["lines"]:
            n_lines += 1
            for span in line["spans"]:
                n_spans += 1
                fonts.add(span["font"])
                sizes.add(round(span["size"], 1))
                n_chars += len(span["chars"])
                b = pymupdf.Rect(span["bbox"])
                span_bbox = b if span_bbox is None else span_bbox | b

    drawings = page.get_drawings()
    images = page.get_images(full=True)
    links = page.get_links()

    st = classify(text)
    return dict(
        page=pno + 1,
        label=page.get_label(),
        rect=[round(v, 1) for v in page.rect],
        rotation=page.rotation,
        chars=st["total"],
        words=len(words),
        lines=n_lines,
        spans=n_spans,
        char_spans=n_chars,
        image_blocks=n_img_blocks,
        images=len(images),
        drawings=len(drawings),
        links=len(links),
        fonts=sorted(fonts),
        sizes=sorted(sizes),
        cls=st,
        sort_differs=(natural.strip() != ordered.strip()),
        text_bbox=[round(v, 1) for v in span_bbox] if span_bbox else None,
        text_head=text.strip()[:120],
    )


def doc_report(path):
    name = os.path.basename(path)
    doc = pymupdf.open(path)
    info = dict(
        file=name,
        bytes=os.path.getsize(path),
        sha256=sha256_of(path),
        mtime=os.path.getmtime(path),
        pdf_header_version=header_version(path),
        page_count=doc.page_count,
        is_encrypted=doc.is_encrypted,
        needs_pass=doc.needs_pass,
        permissions=doc.permissions,
        metadata=dict(doc.metadata),
        catalog_version=doc.xref_get_key(doc.pdf_catalog(), "Version"),
        page_labels=doc.get_page_labels(),
        embfile_count=doc.embfile_count(),
        embfile_names=doc.embfile_names(),
        has_links=doc.has_links(),
        has_annots=doc.has_annots(),
        is_repaired=doc.is_repaired,
    )

    toc = doc.get_toc(simple=False)
    info["toc_count"] = len(toc)
    info["toc_maxdepth"] = max([t[0] for t in toc], default=0)
    info["toc"] = [dict(level=t[0], title=t[1], page=t[2],
                        dest=str(t[3].get("kind")) if isinstance(t[3], dict) else str(t[3]))
                   for t in toc]

    # fonts, embedding state, ToUnicode presence
    seen = {}
    for pno in range(doc.page_count):
        for f in doc.get_page_fonts(pno, full=True):
            xref, ext, ftype, basefont, fname, enc = f[:6]
            if xref in seen:
                continue
            entry = dict(xref=xref, ext=ext, type=ftype, basefont=basefont,
                         name=fname, encoding=enc)
            try:
                got = doc.extract_font(xref)
                buf = got[3]
                entry["embedded"] = bool(buf)
                entry["embedded_bytes"] = len(buf) if buf else 0
                entry["extracted_name"] = got[0]
            except Exception as e:
                entry["embedded"] = None
                entry["font_error"] = repr(e)
            try:
                entry["ToUnicode"] = doc.xref_get_key(xref, "ToUnicode")
            except Exception as e:
                entry["ToUnicode"] = repr(e)
            seen[xref] = entry
    info["fonts"] = list(seen.values())

    pages = [page_report(doc.load_page(p), p) for p in range(doc.page_count)]
    info["pages"] = pages

    # document totals
    tot = dict(total=0, pua=0, fffd=0, ctrl=0, cjk=0, other=0)
    for p in pages:
        for k in tot:
            tot[k] += p["cls"][k]
    info["total_chars"] = tot
    info["empty_pages"] = [p["page"] for p in pages if p["chars"] < 5]
    info["sort_diff_pages"] = [p["page"] for p in pages if p["sort_differs"]]
    info["pua_pages"] = [p["page"] for p in pages if p["cls"]["pua"]]
    info["fffd_pages"] = [p["page"] for p in pages if p["cls"]["fffd"]]
    info["image_only_pages"] = [p["page"] for p in pages
                                if p["chars"] < 5 and p["images"] > 0]

    doc.close()
    return info


def main():
    files = sorted(f for f in os.listdir(SRC) if f.lower().endswith(".pdf"))
    result = dict(generated=__import__("datetime").datetime.now().isoformat(timespec="seconds"),
                  src_dir=SRC, files=[])
    for f in files:
        print("== processing", f, flush=True)
        result["files"].append(doc_report(os.path.join(SRC, f)))
    dst = os.path.join(OUT, "precheck_structure.json")
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    print("written", dst)


if __name__ == "__main__":
    main()
