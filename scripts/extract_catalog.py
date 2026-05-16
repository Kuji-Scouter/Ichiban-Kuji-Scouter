#!/usr/bin/env python3
"""
extract_catalog.py — Reads index.html, locates the RAW_SETS and
GRAIL_FIGURES JS literals, parses them as JSON-ish (with unquoted keys
quoted via a light preprocessor), and writes a flat figure catalog to
data/figures-catalog.json.

Output schema (one entry per figure, 388 total):
    {
      "key":       "Dragon Ball Memories|Prize A|Super Saiyan Goku",
      "set":       "Dragon Ball Memories",
      "prize":     "Prize A",
      "character": "Super Saiyan Goku",
      "isLOP":     false,
      "isGrail":   true,
      "tier1":     true               # = isGrail or isLOP
    }

Consumers:
    - scrape_ebay.py reads this file, filters to tier1 == True, and
      scrapes eBay for each one.

Dependencies: none (stdlib only — uses a custom JS-literal walker).

Usage:
    python3 scripts/extract_catalog.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO / "index.html"
OUT_PATH = REPO / "data" / "figures-catalog.json"


def slice_literal(src: str, marker: str) -> str:
    """Find `marker` (e.g. 'const RAW_SETS'), seek to its assignment, and
    return the JS literal that follows (including outer [] or {}). Uses
    bracket counting with string-aware traversal so braces inside strings
    don't confuse the walker."""
    start = src.find(marker)
    if start == -1:
        raise ValueError(f"marker not found: {marker}")
    eq = src.find("=", start)
    i = eq + 1
    while i < len(src) and src[i].isspace():
        i += 1
    open_ch = src[i]
    close_ch = {"[": "]", "{": "}"}.get(open_ch)
    if not close_ch:
        raise ValueError(f"expected [ or {{ after {marker}, got {open_ch!r}")
    depth = 0
    in_str: str | None = None
    j = i
    while j < len(src):
        c = src[j]
        if in_str is not None:
            if c == "\\":
                j += 2
                continue
            if c == in_str:
                in_str = None
            j += 1
            continue
        if c in ("'", '"', "`"):
            in_str = c
            j += 1
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return src[i : j + 1]
        j += 1
    raise ValueError(f"unbalanced literal for {marker}")


# ── JS-literal → Python parser ────────────────────────────────────────────
# RAW_SETS uses: double-quoted strings, unquoted identifier keys, null,
# numbers, nested arrays/objects, trailing commas. That's a tiny subset of
# JS — small enough to hand-parse.

class _Parser:
    def __init__(self, text: str):
        self.s = text
        self.i = 0

    def skip(self):
        while self.i < len(self.s):
            c = self.s[self.i]
            if c.isspace() or c == ",":
                self.i += 1
            elif self.s.startswith("//", self.i):
                self.i = self.s.find("\n", self.i)
                if self.i == -1:
                    self.i = len(self.s)
            elif self.s.startswith("/*", self.i):
                self.i = self.s.find("*/", self.i + 2) + 2
            else:
                return

    def parse(self):
        self.skip()
        c = self.s[self.i]
        if c == "[":
            return self._array()
        if c == "{":
            return self._object()
        if c == '"' or c == "'":
            return self._string(c)
        if c == "`":
            return self._template()
        return self._literal()

    def _array(self):
        assert self.s[self.i] == "["
        self.i += 1
        out = []
        self.skip()
        while self.s[self.i] != "]":
            out.append(self.parse())
            self.skip()
        self.i += 1
        return out

    def _object(self):
        assert self.s[self.i] == "{"
        self.i += 1
        out = {}
        self.skip()
        while self.s[self.i] != "}":
            # key: bare identifier OR quoted string
            if self.s[self.i] in ('"', "'"):
                key = self._string(self.s[self.i])
            else:
                m = re.match(r"[A-Za-z_$][\w$]*", self.s[self.i :])
                if not m:
                    raise ValueError(f"bad key near pos {self.i}: {self.s[self.i:self.i+40]!r}")
                key = m.group(0)
                self.i += len(key)
            self.skip()
            if self.s[self.i] != ":":
                raise ValueError(f"expected ':' after key {key!r}")
            self.i += 1
            out[key] = self.parse()
            self.skip()
        self.i += 1
        return out

    def _string(self, quote):
        assert self.s[self.i] == quote
        self.i += 1
        chars = []
        while self.s[self.i] != quote:
            c = self.s[self.i]
            if c == "\\":
                nxt = self.s[self.i + 1]
                # JSON-style escapes only — adequate for our data
                esc = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'",
                       "`": "`", "\\": "\\", "/": "/", "b": "\b", "f": "\f"}.get(nxt)
                if esc is None:
                    if nxt == "u":
                        cp = int(self.s[self.i + 2 : self.i + 6], 16)
                        chars.append(chr(cp))
                        self.i += 6
                        continue
                    esc = nxt
                chars.append(esc)
                self.i += 2
                continue
            chars.append(c)
            self.i += 1
        self.i += 1
        return "".join(chars)

    def _template(self):
        # Treat template-literal as a plain string; no interpolations in our data.
        return self._string("`")

    def _literal(self):
        m = re.match(r"[A-Za-z_$][\w$]*|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", self.s[self.i :])
        if not m:
            raise ValueError(f"bad literal near pos {self.i}: {self.s[self.i:self.i+40]!r}")
        tok = m.group(0)
        self.i += len(tok)
        if tok == "null":
            return None
        if tok == "true":
            return True
        if tok == "false":
            return False
        if re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", tok):
            return float(tok) if ("." in tok or "e" in tok or "E" in tok) else int(tok)
        # bare identifier — shouldn't appear in our value positions
        raise ValueError(f"unexpected bare identifier as value: {tok!r}")


def parse_js_literal(text: str):
    return _Parser(text).parse()


def grail_letter(prize_name: str) -> str | None:
    if prize_name == "LOP":
        return "LOP"
    m = re.match(r"^Prize\s+([A-Z])$", prize_name, flags=re.IGNORECASE)
    return m.group(1).upper() if m else None


def is_grail(set_name: str, prize_name: str, grail_map: dict) -> bool:
    entries = grail_map.get(set_name)
    if not entries:
        return False
    if prize_name in entries:
        return True
    letter = grail_letter(prize_name)
    return letter is not None and letter in entries


def main():
    html = INDEX_PATH.read_text(encoding="utf-8")
    raw_sets_text = slice_literal(html, "const RAW_SETS")
    grails_text = slice_literal(html, "const GRAIL_FIGURES")

    raw_sets = parse_js_literal(raw_sets_text)
    grail_map = parse_js_literal(grails_text)

    figures = []
    for s in raw_sets:
        set_name = s["set"]
        for p in s["prizes"]:
            prize_name = p[0]
            character = p[1]
            is_lop = prize_name == "LOP"
            grail = is_grail(set_name, prize_name, grail_map)
            figures.append({
                "key": f"{set_name}|{prize_name}|{character}",
                "set": set_name,
                "prize": prize_name,
                "character": character,
                "isLOP": is_lop,
                "isGrail": grail,
                "tier1": is_lop or grail,
            })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(figures, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    tier1 = sum(1 for f in figures if f["tier1"])
    print(f"Wrote {len(figures)} figures to {OUT_PATH.relative_to(REPO)}")
    print(f"Tier 1 (grails + LOPs): {tier1}")


if __name__ == "__main__":
    sys.exit(main())
