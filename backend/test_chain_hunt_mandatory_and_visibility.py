"""
Regression tests for two Critical bugs in chain_hunt.py's smart_l1_discovery:

1. mandatory_filters were computed into `start_filters` and used to build the
   in-memory `start_products` population, but never merged into the params
   sent to live verification (`verify_candidate`) -- so the "verified" price/
   total/seller-count for every path reflected the UNFILTERED category, even
   though the response's `activeFilters` field claimed the mandatory filter
   was applied.

2. PDP-enrichment futures were submitted to a ThreadPoolExecutor and iterated
   via as_completed(), but future.result() was never called -- any exception
   raised during enrichment was silently discarded with zero logging, making
   mass enrichment failure indistinguishable from "the data genuinely isn't
   there" (which directly feeds the populated-ratio reliability gate).

Run: python test_chain_hunt_mandatory_and_visibility.py
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


GOLDEN_KEY = "c123"
MANDATORY_KEY = "c999"
MANDATORY_VALUE = "Red"


def make_catalog(i: int, price: int, mandatory_value: str) -> dict:
    return {
        "id": str(i),
        "final_price": {"value": price},
        "title": f"Product {i}",
        "brand": "Acme",
        "seller": {"id": str(i % 5), "name": f"Seller {i % 5}"},
        "oem_id": "",
        "specs_for_test": {MANDATORY_KEY: mandatory_value},
    }


class FakeScraper:
    """Stands in for GeMScraper: only the methods smart_l1_discovery touches."""

    def __init__(self):
        self.verify_calls = []
        self.enrich_should_raise_for = set()

    def _normalize_url(self, url):
        return url, {}

    def _build_product_url(self, cat):
        return f"https://mkp.gem.gov.in/p-{cat['id']}"

    def _extract_inline_specs(self, cat):
        # Simulate every product already carrying its mandatory-filter spec
        # inline (as GeM would for an administrative-style facet), so BFS's
        # start_products population is correctly restricted without needing
        # PDP enrichment for the mandatory key.
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
        if product["catalogue_id"] in self.enrich_should_raise_for:
            raise RuntimeError(f"simulated enrichment failure for {product['catalogue_id']}")
        product["specs"][GOLDEN_KEY] = "Red" if int(product["catalogue_id"]) % 2 == 0 else "Blue"
        return product

    def _fetch(self, url, retries=3):
        page = 1
        if "page=" in url:
            page = int(url.split("page=")[1].split("&")[0])
        total = 60
        page_size = 10
        start = (page - 1) * page_size
        end = min(start + page_size, total)
        catalogs = [make_catalog(i, 100 * (i + 1), "Red" if i % 2 == 0 else "Blue") for i in range(start, end)]
        body = {
            "number_of_results": total,
            "facets": {},
            "catalogs": catalogs,
        }
        return json.dumps(body)

    def _chain_scrape(self, url, extra_params, location=""):
        self.verify_calls.append(dict(extra_params))
        return {"error": True}


def test_mandatory_filters_are_sent_to_live_verification():
    print("\n[1] mandatory_filters must be included in the params sent to "
          "live verification (_chain_scrape), not silently dropped")
    scraper = FakeScraper()
    golden_filters = [{
        "filterKey": GOLDEN_KEY,
        "filterName": "Color",
        "isGolden": True,
        "values": ["Red", "Blue"],
    }]
    mandatory_filters = [{"filterKey": MANDATORY_KEY, "value": MANDATORY_VALUE}]

    chain_hunt.smart_l1_discovery(
        scraper,
        category_url="https://mkp.gem.gov.in/some-category/search",
        target_price=3000,
        golden_filters=golden_filters,
        mandatory_filters=mandatory_filters,
    )

    check(f"at least one live-verification call was made (got {len(scraper.verify_calls)})",
          len(scraper.verify_calls) > 0)
    check(
        "every live-verification call includes the mandatory filter "
        f"({MANDATORY_KEY}={MANDATORY_VALUE})",
        all(call.get(MANDATORY_KEY) == MANDATORY_VALUE for call in scraper.verify_calls),
    )


def test_enrichment_failures_are_logged_not_silently_discarded():
    print("\n[2] An exception raised during PDP enrichment must be logged, "
          "not silently discarded with zero trace")
    scraper = FakeScraper()
    # Force every enrichment task in the "relevant products" pool to raise.
    scraper.enrich_should_raise_for = {str(i) for i in range(60)}

    golden_filters = [{
        "filterKey": GOLDEN_KEY,
        "filterName": "Color",
        "isGolden": True,
        "values": ["Red", "Blue"],
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
            target_price=3000,
            golden_filters=golden_filters,
        )
    finally:
        chain_hunt.logger.removeHandler(handler)

    check("smart_l1_discovery completes without raising despite every "
          "enrichment task failing", result is not None)
    check(
        f"a warning about the enrichment failures was logged (got {len(log_records)} warning(s))",
        any("enrichment" in msg.lower() for msg in log_records),
    )


if __name__ == "__main__":
    test_mandatory_filters_are_sent_to_live_verification()
    test_enrichment_failures_are_logged_not_silently_discarded()

    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed\n{'='*60}")
    sys.exit(1 if FAIL else 0)
