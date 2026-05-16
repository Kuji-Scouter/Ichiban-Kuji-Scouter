# scripts/

Helpers for the **on-demand** eBay price refresh workflow.

Prices are not on a schedule — Claude only scrapes when **you ask**.
You decide which figures need a refresh and when (the cadence will
naturally vary: weekly for the SMSP grails, monthly for the long tail,
case-by-case for a figure you're actively negotiating).

```
You: "Claude, refresh eBay prices for these 5 figures…"
        │
        ▼
Claude opens eBay sold-listings per figure, reads + filters the
listings carefully (excludes lots / broken / parts / wrong character),
and pastes accepted sales into data/ebay-prices.json under each
figure's `{set}|{prize}|{character}` key.
        │
        ▼
You commit + push the JSON.
        │
        ▼
GitHub Pages serves it; index.html fetches it on the next page load
and merges fresh prices into the table / sparklines / Top 10.
```

## Files

| File | Role |
| --- | --- |
| `extract_catalog.py` | Stdlib-only Python that reads `index.html`, parses the `RAW_SETS` + `GRAIL_FIGURES` literals, and writes a flat figure list to `data/figures-catalog.json` (388 figures with `set / prize / character / isLOP / isGrail` flags). Re-run it whenever you add or rename a figure in `index.html`. |

## When to ask Claude for a refresh

There's no rule — typical triggers:

- A grail figure you're tracking just had its first sale in a month.
- You spotted a sketchy lot listing in the data and want it scrubbed.
- A new Kuji set's secondary market has finally activated and needs
  initial prices populated.
- A figure's existing data is 3+ months old and you want a refresh.

Tell Claude which figures (by name, set, or "all grails in X set") and
let it work. The footer's freshness badge ("eBay prices last refreshed
X days ago") pulls from whatever `ebayUpdated` values are in the data,
so you always see how stale the feed is across the catalogue.

## Output schema

`data/ebay-prices.json` is keyed by `figureKey` — same string
`index.html` already uses internally (`${set}|${prize}|${character}`):

```json
{
  "Dragon Ball Memories|LOP|Super Saiyan Blue Vegeta": {
    "ebayHistory": [
      {"date":"2026-05-12","price":268.99,"title":"...","url":"..."},
      {"date":"2026-05-13","price":245.00,"title":"...","url":"..."}
    ],
    "ebayUpdated": "2026-05-15"
  }
}
```

`index.html` fetches this file at boot and merges it onto the in-HTML
catalog. If the fetch fails or the file is empty, the site keeps using
its baked-in price history — graceful degradation.

## Quality bar Claude applies when scraping

The whole point of the on-demand model is **precision over volume**.
Standing instructions:

1. Exclude obvious mismatches: lots, multi-figure bundles, broken /
   parts / repair listings, empty-box-only, accessory-only, and any
   title that doesn't pair "ichiban kuji" with the figure's character.
2. Resolve sale dates to YYYY-MM-DD. Drop anything missing a clear date.
3. Dedupe by listing URL on every refresh so a re-run is idempotent.
4. Trim each figure's history to the most recent ~60 sales so the file
   stays small and the sparkline range stays meaningful.
5. Report the diff before writing: how many new sales accepted, how
   many rejected, with the rejected titles listed so you can sanity-
   check the filter.
