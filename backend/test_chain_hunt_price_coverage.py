"""
Regression test for a real reported bug: running Chain Hunt against the same
category at a high target price (Rs 120,000) produced a much worse result
than at a lower target price (Rs 80,000), because GeM's search API returns
only ~12 products per page and the scraper caps at 20 pages sorted
price-ascending (~240 products total, a couple percent of a 10,000+ product
category). For a category flooded with cheap listings, that fixed-size
ascending sample can be entirely consumed by products well below the target
price, leaving the search with almost no genuine "non-blocker" (priced
above target) data to build a real win or an honest achievable-ceiling
estimate from -- confirmed live: one run sampled only 1 product priced
above a Rs 120,000 target out of the entire scraped set.

Fix: if the ascending sample ends up with too few products priced above
the target, fetch a small number of supplemental pages sorted
price-descending (verified live against the real GeM API to be a
supported sort_type value) to guarantee a real sample of higher-priced
products regardless of how skewed the category's cheap end is.

Run: python test_chain_hunt_price_coverage.py
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


TARGET_PRICE = 1000
TOTAL_RESULTS = 300  # large category
PAGE_SIZE = 12  # GeM's real page size


class FakeScraper:
    """
    Simulates a category flooded with cheap listings: every ascending page
    (all 20 of them, the full cap) returns products priced well below
    target_price. Only the price-descending supplement returns anything
    priced above it.
    """

    def __init__(self):
        self.fetched_urls = []

    def _normalize_url(self, url):
        return url, {}

    def _build_product_url(self, cat):
        return f"https://mkp.gem.gov.in/p-{cat['id']}"

    def _extract_inline_specs(self, cat):
        return {}

    def _names_match(self, a, b):
        return a.strip().lower() == b.strip().lower()

    def _to_key(self, name):
        return name.lower().replace(" ", "_")

    def _extract_facet_defs(self, facets):
        return []

    def _enrich_single_product(self, product, name_to_code):
        return product

    def _fetch(self, url, retries=3):
        self.fetched_urls.append(url)
        page = 1
        if "page=" in url:
            page = int(url.split("page=")[1].split("&")[0])
        is_desc = "sort_type=price_in_desc" in url

        if is_desc:
            # Descending supplement: genuinely expensive products.
            catalogs = [
                {
                    "id": f"desc{page}_{i}", "final_price": {"value": 5000 + i},
                    "title": "expensive", "brand": "x",
                    "seller": {"id": f"ds{page}_{i}", "name": "x"}, "oem_id": "",
                }
                for i in range(PAGE_SIZE)
            ]
            return json.dumps({"number_of_results": TOTAL_RESULTS, "facets": {}, "catalogs": catalogs})

        # Ascending pages: cheap products only, every single one of the 20
        # allowed pages -- simulates a category with far more cheap listings
        # than the page cap can ever get past.
        start = (page - 1) * PAGE_SIZE
        catalogs = [
            {
                "id": f"cheap{start + i}", "final_price": {"value": 100 + start + i},
                "title": "cheap", "brand": "x",
                "seller": {"id": f"cs{start + i}", "name": "x"}, "oem_id": "",
            }
            for i in range(PAGE_SIZE)
        ]
        return json.dumps({"number_of_results": TOTAL_RESULTS, "facets": {}, "catalogs": catalogs})

    def _chain_scrape(self, url, extra_params, location=""):
        return {"error": True}


def test_supplements_with_descending_pages_when_no_high_priced_products_found():
    print("\n[1] When the ascending sample is entirely below target_price, "
          "the search must fetch a price-descending supplement instead of "
          "concluding there's almost no achievable ceiling")
    scraper = FakeScraper()

    chain_hunt.smart_l1_discovery(
        scraper,
        category_url="https://mkp.gem.gov.in/some-category/search",
        target_price=TARGET_PRICE,
        golden_filters=[],
    )

    desc_calls = [u for u in scraper.fetched_urls if "sort_type=price_in_desc" in u]
    check(f"fetched at least one price-descending supplemental page (got {len(desc_calls)})",
          len(desc_calls) > 0)
    check(f"did not fetch more than 3 descending pages (got {len(desc_calls)}, "
          "bounded supplement, not unbounded)", len(desc_calls) <= 3)


def test_no_supplement_when_enough_non_blockers_already_found():
    print("\n[2] When the ascending sample already has enough products "
          "above target_price, no descending supplement should be fetched "
          "(avoid wasted API calls)")

    class HealthyFakeScraper(FakeScraper):
        def _fetch(self, url, retries=3):
            self.fetched_urls.append(url)
            page = 1
            if "page=" in url:
                page = int(url.split("page=")[1].split("&")[0])
            # Half the sample (still within the ascending pages) is priced
            # comfortably above target_price -- plenty of non-blockers
            # already, no need for a supplement.
            start = (page - 1) * PAGE_SIZE
            catalogs = [
                {
                    "id": f"p{start + i}",
                    "final_price": {"value": 100 + start + i if i < 6 else 5000 + start + i},
                    "title": "x", "brand": "x",
                    "seller": {"id": f"s{start + i}", "name": "x"}, "oem_id": "",
                }
                for i in range(PAGE_SIZE)
            ]
            return json.dumps({"number_of_results": TOTAL_RESULTS, "facets": {}, "catalogs": catalogs})

    scraper = HealthyFakeScraper()
    chain_hunt.smart_l1_discovery(
        scraper,
        category_url="https://mkp.gem.gov.in/some-category/search",
        target_price=TARGET_PRICE,
        golden_filters=[],
    )

    desc_calls = [u for u in scraper.fetched_urls if "sort_type=price_in_desc" in u]
    check(f"no descending supplement fetched when ascending sample already "
          f"has enough non-blockers (got {len(desc_calls)} descending calls)",
          len(desc_calls) == 0)


if __name__ == "__main__":
    test_supplements_with_descending_pages_when_no_high_priced_products_found()
    test_no_supplement_when_enough_non_blockers_already_found()

    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed\n{'='*60}")
    sys.exit(1 if FAIL else 0)
