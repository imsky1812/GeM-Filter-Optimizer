"""
Regression tests for two remaining findings in chain_hunt.py from a targeted
bug-hunt review:

1. Winning-path candidates were capped to 20 (`local_winning_paths[:20]`) in
   raw BFS-discovery order, not sorted by quality first -- unlike the
   partial-path branch a few lines below, which explicitly sorts before
   capping. If BFS discovers more than 20 wins, which 20 get (expensive,
   rate-limited) live verification depended on arbitrary golden_list
   iteration order rather than price gap, so a strictly better win could be
   silently dropped before ever being checked.

2. Per-page scrape failures inside fetch_page's bare `except Exception:
   return []` were swallowed with zero logging, making the outer handler's
   `except Exception as e: logger.error(...)` dead code (fetch_page never
   re-raises) -- a systemic page-fetch failure (e.g. a WAF block after page
   1) would silently truncate the scraped product set with no trace.

Run: python test_chain_hunt_candidate_order_and_logging.py
"""
import sys
import json
import logging

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


GOLDEN_KEY = "color"
LETTERS = [chr(ord("A") + i) for i in range(21)]  # A..U -- 21 distinct single-step wins


class FakeScraper:
    """Stands in for GeMScraper: only the methods smart_l1_discovery touches."""

    def __init__(self, fail_page_2=False):
        self.verify_calls = []
        self.fail_page_2 = fail_page_2

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
            "filterName": "Color",
            "filterKey": GOLDEN_KEY,
            "isGolden": True,
            "type": "",
            "facetValues": [],
        }]

    def _enrich_single_product(self, product, name_to_code):
        return product

    def _all_catalogs(self):
        # One low-priced "blocker" product with an unrelated color value,
        # plus 21 single-letter products -- each letter alone is an
        # immediate win (root has a blocker, so BFS must expand at least
        # one step). "A" is priced far above target; all others are barely
        # above it, so "A" has by far the largest price gap.
        catalogs = [{
            "id": "blocker", "final_price": {"value": 500}, "title": "blocker",
            "brand": "x", "seller": {"id": "s0", "name": "s0"}, "oem_id": "",
            "specs_for_test": {GOLDEN_KEY: "XX"},
        }]
        for i, letter in enumerate(LETTERS):
            price = 5000 if letter == "A" else 1100
            catalogs.append({
                "id": f"p{i}", "final_price": {"value": price}, "title": letter,
                "brand": "x", "seller": {"id": f"s{i + 1}", "name": f"s{i + 1}"}, "oem_id": "",
                "specs_for_test": {GOLDEN_KEY: letter},
            })
        return catalogs

    def _fetch(self, url, retries=3):
        page = 1
        if "page=" in url:
            page = int(url.split("page=")[1].split("&")[0])

        if page == 2 and self.fail_page_2:
            raise RuntimeError("simulated WAF block on page 2")

        # Paginate a fixed 22-item catalog, 10 per page, so a >1-page fetch
        # (needed to exercise the page-2 failure path) is actually required.
        all_catalogs = self._all_catalogs()
        page_size = 10
        start = (page - 1) * page_size
        page_catalogs = all_catalogs[start:start + page_size]
        return json.dumps({
            "number_of_results": len(all_catalogs),
            "facets": {},
            "catalogs": page_catalogs,
        })

    def _chain_scrape(self, url, extra_params, location=""):
        self.verify_calls.append(dict(extra_params))
        return {"error": True}


def test_best_candidate_is_not_dropped_by_the_cap():
    print("\n[1] With more than 20 winning paths discovered, the ONE with by "
          "far the largest price gap must survive the cap to 20 candidates")
    scraper = FakeScraper()
    golden_filters = [{
        "filterKey": GOLDEN_KEY,
        "filterName": "Color",
        "isGolden": True,
        "values": LETTERS,
    }]

    chain_hunt.smart_l1_discovery(
        scraper,
        category_url="https://mkp.gem.gov.in/some-category/search",
        target_price=1000,
        golden_filters=golden_filters,
    )

    check(f"exactly 20 candidates were sent to live verification (got {len(scraper.verify_calls)})",
          len(scraper.verify_calls) == 20)
    check(
        "the best candidate (color=A, ~4000 gap vs ~100 for the rest) was "
        "included, not silently dropped by the raw-discovery-order cap",
        any(call.get(GOLDEN_KEY) == "A" for call in scraper.verify_calls),
    )


def test_page_fetch_failure_is_logged():
    print("\n[2] A per-page scrape failure must be logged, not silently "
          "discarded with zero trace")
    scraper = FakeScraper(fail_page_2=True)
    golden_filters = [{
        "filterKey": GOLDEN_KEY,
        "filterName": "Color",
        "isGolden": True,
        "values": LETTERS[:2],
    }]

    log_records = []

    class CaptureHandler(logging.Handler):
        def emit(self, record):
            log_records.append(record.getMessage())

    handler = CaptureHandler()
    chain_hunt.logger.addHandler(handler)
    chain_hunt.logger.setLevel(logging.WARNING)
    try:
        result = chain_hunt.smart_l1_discovery(
            scraper,
            category_url="https://mkp.gem.gov.in/some-category/search",
            target_price=1000,
            golden_filters=golden_filters,
        )
    finally:
        chain_hunt.logger.removeHandler(handler)

    check("smart_l1_discovery completes without raising despite the page-2 "
          "fetch failing", result is not None)
    check(
        f"a warning about the failed page fetch was logged (got {len(log_records)} warning(s))",
        any("page" in msg.lower() and "fetch" in msg.lower() for msg in log_records),
    )


if __name__ == "__main__":
    test_best_candidate_is_not_dropped_by_the_cap()
    test_page_fetch_failure_is_logged()

    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed\n{'='*60}")
    sys.exit(1 if FAIL else 0)
