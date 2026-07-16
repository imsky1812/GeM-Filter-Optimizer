"""
Regression test for the golden-filter "populated ratio" prune in
smart_l1_discovery (chain_hunt.py), introduced in commit 490d688.

Background: PDP (product detail page) enrichment is deliberately limited
to a small "relevant" subset of products (blockers[:30] + non_blockers[:10],
~40 max) for rate-limiting/performance reasons -- it never touches the
full bulk-scraped product list, which can run into the hundreds or
thousands for a broad category. The prune added in 490d688 computes
`populated_count / len(products)` (the FULL bulk-scraped list) instead of
`populated_count / len(relevant_products)` (the enrichment-eligible pool).
For any category bigger than ~130 products, that ratio can never reach
the 0.3 threshold even if every single PDP enrichment succeeds -- so every
golden filter gets pruned and the chain hunt always reports STUCK with
0 golden filters, regardless of the query. This was confirmed live via
backend/uvicorn.log against a 10,199-product category.

Run: python test_chain_hunt_golden_ratio.py
"""
import sys

sys.path.insert(0, ".")

import json
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


TOTAL_PRODUCTS = 200
PAGE_SIZE = 10
GOLDEN_KEY = "c123"


def make_catalog(i: int, price: int) -> dict:
    return {
        "id": str(i),
        "final_price": {"value": price},
        "title": f"Product {i}",
        "brand": "Acme",
        "seller": {"id": str(i % 5), "name": f"Seller {i % 5}"},
        "oem_id": "",
    }


class FakeScraper:
    """Stands in for GeMScraper: only the methods smart_l1_discovery touches."""

    def _normalize_url(self, url):
        return url, {}

    def _build_product_url(self, cat):
        return f"https://mkp.gem.gov.in/p-{cat['id']}"

    def _extract_inline_specs(self, cat):
        # Real GeM catalog listing items carry no inline spec fields at all.
        return {}

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
        # Simulate every PDP enrichment succeeding for the relevant pool --
        # isolates the ratio-math bug from any live-network flakiness.
        product["specs"][GOLDEN_KEY] = "Red" if int(product["catalogue_id"]) % 2 == 0 else "Blue"
        return product

    def _fetch(self, url, retries=3):
        page = 1
        if "page=" in url:
            page = int(url.split("page=")[1].split("&")[0])
        start = (page - 1) * PAGE_SIZE
        end = min(start + PAGE_SIZE, TOTAL_PRODUCTS)
        catalogs = [make_catalog(i, 100 * (i + 1)) for i in range(start, end)]
        body = {
            "number_of_results": TOTAL_PRODUCTS,
            "facets": {},
            "catalogs": catalogs,
        }
        return json.dumps(body)

    def _chain_scrape(self, url, extra_params, location=""):
        # Live verification isn't under test here; fail it cleanly so
        # smart_l1_discovery finishes without needing real network I/O.
        return {"error": True}


def test_golden_filter_survives_in_a_large_category():
    print("\n[1] A golden filter fully populated across the enriched pool "
          "must survive the reliability gate, regardless of total category size")
    scraper = FakeScraper()
    golden_filters = [{
        "filterKey": GOLDEN_KEY,
        "filterName": "Color",
        "isGolden": True,
        "values": ["Red", "Blue"],
    }]

    result = chain_hunt.smart_l1_discovery(
        scraper,
        category_url="https://mkp.gem.gov.in/some-category/search",
        target_price=15000,
        golden_filters=golden_filters,
    )

    check(
        f"goldenFilterCount > 0 (got {result['goldenFilterCount']}) even though "
        f"the category has {TOTAL_PRODUCTS} products and only ~40 were enriched",
        result["goldenFilterCount"] > 0,
    )


if __name__ == "__main__":
    test_golden_filter_survives_in_a_large_category()

    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed\n{'='*60}")
    sys.exit(1 if FAIL else 0)
