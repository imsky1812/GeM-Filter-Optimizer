"""
Tests for niche_search.find_l1_niches against an in-memory stand-in for GeM.

The fake answers a filtered query the way GeM does -- exact count and the
cheapest listings over the whole category -- so the search logic can be
checked without the network: combination discovery, the blocker pruning,
broadest-win selection, and the product-page price check.
"""
import sys

import crawler
import niche_search

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def listing(i, price, page_price=None, **specs):
    return {"url": f"https://mkp.gem.gov.in/x/p-1-{i}-cat.html", "price": price,
            "page": page_price if page_price is not None else price,
            "seller": f"s{i}", "specs": specs}


class FakeGeM:
    """Stands in for GeMCrawler: answers filtered queries from `CATALOG`."""
    CATALOG = []
    queries = []

    def __init__(self):
        pass

    def _normalize_url(self, url):
        return url, {}

    def _resolve_canonical_category(self, url):
        return None

    def crawl_filtered_prices(self, url, filters, location="", seller_price=None, max_pages=2):
        FakeGeM.queries.append(dict(filters))
        hits = [l for l in self.CATALOG if all(l["specs"].get(k) == v for k, v in filters.items())]
        hits.sort(key=lambda l: l["price"])
        shown = hits[:12 * max_pages]
        return {
            "min_price": hits[0]["price"] if hits else None,
            "total": len(hits),
            "seller_count": len({l["seller"] for l in shown}),
            "products": [{"url": l["url"], "price": l["price"], "name": l["url"],
                          "brand": l["seller"], "seller": l["seller"], "seller_id": l["seller"]}
                         for l in shown],
            "error": False,
            "ignored": False,
        }

    def live_prices(self, urls):
        by_url = {l["url"]: l["page"] for l in self.CATALOG}
        return {u: by_url.get(u) for u in urls}


def run(catalog, target, golden):
    FakeGeM.CATALOG = catalog
    FakeGeM.queries = []
    return niche_search.find_l1_niches("https://mkp.gem.gov.in/x/search", target, golden)


def golden(key, *values):
    return {"filterKey": key, "filterName": key, "isGolden": True,
            "type": "MultiselectOr", "values": list(values)}


crawler.GeMCrawler = FakeGeM
niche_search._discover_values = lambda *a, **k: {}

# ── 1. A win that only exists as a combination ───────────────────────────────
print("\nA combination wins where neither filter wins alone")
cat = [
    listing(1, 100, colour="red", size="L"),     # blocks red
    listing(2, 100, colour="blue", size="M"),    # blocks M
    listing(3, 300, colour="red", size="M"),     # the red+M niche: 300 and up
    listing(4, 350, colour="red", size="M"),
    listing(5, 400, colour="blue", size="L"),
]
res = run(cat, 200, [golden("colour", "red", "blue"), golden("size", "L", "M")])
wins = [p for p in res["winningPaths"] if p["status"] == "WIN"]
check("finds red + M", any(p["activeFilters"] == {"colour": "red", "size": "M"} for p in wins),
      [p["activeFilters"] for p in wins])
check("its floor is the niche's cheapest listing", any(p["nicheMinPrice"] == 300 for p in wins))
check("reports GeM's count, not a sample", res["searchedListings"] == 5)
steps = next(p for p in wins if p["activeFilters"] == {"colour": "red", "size": "M"})["iterations"]
check("each step is GeM's live count, never growing",
      all(b["newTotal"] <= a["newTotal"] for a, b in zip(steps, steps[1:])) and steps[-1]["newTotal"] == 2,
      [s["newTotal"] for s in steps])

# ── 2. Broadest win only ─────────────────────────────────────────────────────
print("\nA narrower win is dropped when a broader one already wins")
cat = [
    listing(1, 100, colour="blue", size="L"),
    listing(2, 300, colour="red", size="M"),
    listing(3, 320, colour="red", size="L"),
]
res = run(cat, 200, [golden("colour", "red", "blue"), golden("size", "L", "M")])
filters = [p["activeFilters"] for p in res["winningPaths"] if p["status"] == "WIN"]
check("red alone wins", {"colour": "red"} in filters, filters)
check("red + M is not also reported", {"colour": "red", "size": "M"} not in filters, filters)

# ── 3. Exact pruning ─────────────────────────────────────────────────────────
print("\nA combination a blocker survives is never queried")
cat = [
    listing(1, 100, colour="red", size="M"),     # blocks red, M, and red+M
    listing(2, 400, colour="blue", size="L"),
    listing(3, 150, colour="blue", size="M"),
]
res = run(cat, 200, [golden("colour", "red", "blue"), golden("size", "L", "M")])
check("red + M was never asked of GeM", {"colour": "red", "size": "M"} not in FakeGeM.queries,
      FakeGeM.queries)

# ── 4. The page price decides ────────────────────────────────────────────────
print("\nA stale search price can't make a win")
cat = [
    listing(1, 100, colour="blue"),
    listing(2, 500, page_price=150, colour="red"),   # search 500, page sells at 150
    listing(3, 600, colour="red"),
]
res = run(cat, 200, [golden("colour", "red", "blue")])
red = next(p for p in res["winningPaths"] if p["activeFilters"] == {"colour": "red"})
check("red is not a win once page-priced", red["status"] != "WIN", red["status"])
check("its floor is the page price", red["nicheMinPrice"] == 150, red["nicheMinPrice"])
check("the correction is counted", (red["priceCheck"] or {}).get("corrected") == 1, red["priceCheck"])
check("overall status is not WIN", res["status"] != "WIN", res["status"])

# ── 5. Values GeM doesn't recognise, and coverage ────────────────────────────
print("\nValues GeM returns nothing for, and how much of the category is covered")
cat = [listing(1, 300, colour="red"), listing(2, 350, colour="blue"), listing(3, 380, colour="green")]
res = run(cat, 200, [golden("colour", "red", "purple")])
check("purple is reported unrecognised",
      any(u["value"] == "purple" for u in res["unrecognizedValues"]), res["unrecognizedValues"])
cov = {c["filterKey"]: c["share"] for c in res["filterCoverage"]}
check("known values cover 1 of 3 listings", abs(cov.get("colour", 0) - 0.333) < 0.01, cov)

# ── 6. Already L1 with no filter ─────────────────────────────────────────────
print("\nA price under the whole market wins without any filter")
cat = [listing(1, 300, colour="red"), listing(2, 400, colour="blue")]
res = run(cat, 200, [golden("colour", "red", "blue")])
check("status WIN", res["status"] == "WIN", res["status"])
check("the win is the whole category, no filters",
      res["winningPaths"] and res["winningPaths"][0]["activeFilters"] == {},
      [p["activeFilters"] for p in res["winningPaths"]])

print(f"\n{'=' * 60}\n{passed} passed, {failed} failed\n{'=' * 60}")
sys.exit(1 if failed else 0)
