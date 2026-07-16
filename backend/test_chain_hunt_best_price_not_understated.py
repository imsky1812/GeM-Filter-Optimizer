"""
Regression test for a real bug reported live: running Chain Hunt on the same
category at two different target prices produced an inconsistent, seemingly
backwards result -- a HARDER target price (Rs 120,000) reported a LOWER
"Best Achievable Floor" (Rs 73,560) than an EASIER target price (Rs 80,000,
Rs 80,899), even though the underlying category and golden filters were the
same.

Root cause: when no full winning path is found, the candidates promoted to
(expensive, rate-limited) live verification are chosen by
sort_local_partial_key, which sorts by `blockers_count` (fewest remaining
blockers) BEFORE price. A state with a genuinely higher achievable price but
more remaining blockers can rank below 15 other, lower-price states and get
silently excluded from the candidate list entirely -- meaning its price is
never live-verified and never considered for bestAchievablePrice, even
though it's real data the search actually found. bestAchievablePrice is
explicitly presented to the user as "the highest price floor achievable
through spec filters," so silently dropping the actual best one is a
correctness bug, not just a heuristic quirk.

This reproduces the mechanism directly: 16 distinct single-filter states are
discovered, 15 of which have 1 remaining blocker at a low price (Rs 100),
and one ("P") has 2 remaining blockers but a much higher price (Rs 850).
Under the old code, "P" never reaches live verification (the cap is 15) and
bestAchievablePrice comes back as Rs 100. The fix guarantees the single
highest local-price partial state is always included among the candidates
sent for live verification.

Run: python test_chain_hunt_best_price_not_understated.py
"""
import sys
import json

sys.path.insert(0, ".")

import chain_hunt

PASS = 0
FAIL = 0


def check(name, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name}")


GOLDEN_KEY = "size"
LETTERS = [chr(ord("A") + i) for i in range(16)]  # A..P -- 16 distinct single-step partial states


class FakeScraper:
    """Stands in for GeMScraper: only the methods smart_l1_discovery touches."""

    def __init__(self):
        self.verify_calls = []

    def _normalize_url(self, url):
        return url, {}

    def _build_product_url(self, cat):
        return f"https://mkp.gem.gov.in/p-{cat['id']}"

    def _extract_inline_specs(self, cat):
        return dict(cat.get("specs_for_test", {}))

    def _names_match(self, a, b):
        return a.strip().lower() == b.strip().lower()

    def _to_key(self, name):
        return name.lower().replace(" ", "_")

    def _extract_facet_defs(self, facets):
        return [{
            "filterName": "Size",
            "filterKey": GOLDEN_KEY,
            "isGolden": True,
            "type": "",
            "facetValues": [],
        }]

    def _enrich_single_product(self, product, name_to_code):
        return product

    def _fetch(self, url, retries=3):
        page = 1
        if "page=" in url:
            page = int(url.split("page=")[1].split("&")[0])

        if page > 1:
            return json.dumps({"number_of_results": 17, "facets": {}, "catalogs": []})

        catalogs = []
        cid = 0
        for letter in LETTERS:
            if letter == "P":
                # More remaining blockers (2), but a much higher price --
                # the state the buggy candidate-selection heuristic drops.
                for price in (850, 900):
                    catalogs.append({
                        "id": f"p{cid}", "final_price": {"value": price}, "title": letter,
                        "brand": "x", "seller": {"id": f"s{cid}", "name": f"s{cid}"}, "oem_id": "",
                        "specs_for_test": {GOLDEN_KEY: letter},
                    })
                    cid += 1
            else:
                # Fewer remaining blockers (1), but a low price.
                catalogs.append({
                    "id": f"p{cid}", "final_price": {"value": 100}, "title": letter,
                    "brand": "x", "seller": {"id": f"s{cid}", "name": f"s{cid}"}, "oem_id": "",
                    "specs_for_test": {GOLDEN_KEY: letter},
                })
                cid += 1
        return json.dumps({"number_of_results": len(catalogs), "facets": {}, "catalogs": catalogs})

    def _chain_scrape(self, url, extra_params, location=""):
        self.verify_calls.append(dict(extra_params))
        letter = extra_params.get(GOLDEN_KEY)
        if letter == "P":
            return {"min_price": 850, "total": 2, "seller_count": 2, "products": [], "error": False}
        return {"min_price": 100, "total": 1, "seller_count": 1, "products": [], "error": False}


def test_best_achievable_price_reflects_the_true_best_partial_state():
    print("\n[1] bestAchievablePrice must reflect the highest price the "
          "search actually found, not just the price among states with "
          "the fewest remaining blockers")
    scraper = FakeScraper()
    golden_filters = [{
        "filterKey": GOLDEN_KEY,
        "filterName": "Size",
        "isGolden": True,
        "values": LETTERS,
    }]

    result = chain_hunt.smart_l1_discovery(
        scraper,
        category_url="https://mkp.gem.gov.in/some-category/search",
        target_price=1000,
        golden_filters=golden_filters,
    )

    check(
        "the higher-price, more-blockers state ('P') was included in live "
        "verification, not silently excluded",
        any(call.get(GOLDEN_KEY) == "P" for call in scraper.verify_calls),
    )
    check(
        f"bestAchievablePrice reflects the true best (850), not the "
        f"low-price/fewest-blockers states (100) (got {result['bestAchievablePrice']})",
        result["bestAchievablePrice"] == 850,
    )


if __name__ == "__main__":
    test_best_achievable_price_reflects_the_true_best_partial_state()

    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed\n{'='*60}")
    sys.exit(1 if FAIL else 0)
