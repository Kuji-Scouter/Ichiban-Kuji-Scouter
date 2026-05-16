#!/usr/bin/env python3
"""
migrate_inhtml_history.py — One-time migration.

Walks every figure declared in index.html's RAW_SETS, finds any baked-in
ebayHistory array, and merges those sales into data/ebay-prices.json so
the JSON becomes the single source of truth for the live site.

After this runs, future refreshes can never accidentally erase history
because the JSON already contains every prior sale.

Merge rules (idempotent — safe to re-run):
  - dedup by (date, round(price, 2), title) within each figure
  - preserve all existing JSON entries; only ADD missing in-HTML sales
  - sort each figure's history chronologically
  - cap at 60 most-recent sales per figure
  - if a figure had a baked-in `ebayUpdated` date and the JSON entry
    has none (or older), bump the JSON's `ebayUpdated` to it
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "index.html"
OUT = REPO / "data" / "ebay-prices.json"

sys.path.insert(0, str(REPO / "scripts"))
from extract_catalog import slice_literal, parse_js_literal  # noqa: E402


def main():
    html = INDEX.read_text(encoding="utf-8")
    raw_sets = parse_js_literal(slice_literal(html, "const RAW_SETS"))

    existing: dict = {}
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8")) or {}
        except json.JSONDecodeError:
            existing = {}

    migrated_figures = 0
    migrated_sales = 0
    skipped_dupes = 0

    for s in raw_sets:
        set_name = s["set"]
        for p in s["prizes"]:
            prize, character = p[0], p[1]
            extra = p[-1] if isinstance(p[-1], dict) else None
            if not extra:
                continue
            in_html_history = extra.get("ebayHistory") or []
            in_html_updated = extra.get("ebayUpdated") or ""
            if not in_html_history:
                continue

            key = f"{set_name}|{prize}|{character}"
            entry = existing.setdefault(key, {"ebayHistory": [], "ebayUpdated": in_html_updated})
            seen = {(h["date"], round(float(h["price"]), 2), h.get("title", ""))
                    for h in entry["ebayHistory"]}

            before = len(entry["ebayHistory"])
            for sale in in_html_history:
                k = (sale["date"], round(float(sale["price"]), 2), sale.get("title", ""))
                if k in seen:
                    skipped_dupes += 1
                    continue
                # in-HTML history doesn't carry titles/urls — store the
                # date+price faithfully and a marker so we know it came
                # from the baked-in catalog
                entry["ebayHistory"].append({
                    "date": sale["date"],
                    "price": round(float(sale["price"]), 2),
                    "title": sale.get("title", "(from index.html baseline)"),
                    "url": sale.get("url", ""),
                })
                seen.add(k)
                migrated_sales += 1

            entry["ebayHistory"].sort(key=lambda h: h["date"])
            entry["ebayHistory"] = entry["ebayHistory"][-60:]

            # bump ebayUpdated only if in-HTML one is fresher
            if in_html_updated and in_html_updated > (entry.get("ebayUpdated") or ""):
                entry["ebayUpdated"] = in_html_updated

            if len(entry["ebayHistory"]) > before:
                migrated_figures += 1

    OUT.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    total_figs = len(existing)
    total_sales = sum(len(v["ebayHistory"]) for v in existing.values())
    print(f"Migrated in-HTML history → {OUT.relative_to(REPO)}")
    print(f"  Figures migrated:    {migrated_figures}")
    print(f"  Sales added:         {migrated_sales}")
    print(f"  Duplicates skipped:  {skipped_dupes}")
    print(f"  Final file totals:   {total_figs} figures, {total_sales} sales")


if __name__ == "__main__":
    main()
