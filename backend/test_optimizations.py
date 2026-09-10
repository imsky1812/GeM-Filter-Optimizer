"""
Tests for the fetch/CPU optimizations:

1. GeMCategoryScraper walks pages 2..N in concurrent batches (fetch_many)
   instead of one request at a time, while keeping the max_price early stop.
2. GeMScraper._fast_price_scrape asks for a price-ascending listing and reads
   only page 1, instead of walking every page of the category.
3. GeMCrawler._rebuild_filter_values uses the shared (fixed) name matcher, so
   short names like "BIS" match, and resolves each spec name only once.
4. main.py's scrape cache evicts expired and excess entries.

Run: python test_optimizations.py
"""
import json
import sys
import time

sys.path.insert(0, ".")

import l1_surpasser
import crawler as crawler_mod
from gem_utils import make_name_resolver
from scraper import GeMScraper

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
    assert condition, name


PAGE_SIZE = 10


def fake_page_body(url: str, total: int) -> str:
    page = int(url.split("page=")[1].split("&")[0])
    start = (page - 1) * PAGE_SIZE
    catalogs = [
        {"id": f"p{i}", "final_price": {"value": 100 * (i + 1)}, "seller": {"id": f"s{i}"}}
        for i in range(start, min(start + PAGE_SIZE, total))
    ]
    return json.dumps({"number_of_results": total, "catalogs": catalogs})


def run_category_scrape(total: int, max_price):
    batches = []
    original_fetch = l1_surpasser._fetch_with_backoff
    original_fetch_many = l1_surpasser._fetch_many_with_backoff
    l1_surpasser._fetch_with_backoff = lambda url: fake_page_body(url, total)

    def fake_fetch_many(urls):
        batches.append(len(urls))
        return [fake_page_body(u, total) for u in urls]

    l1_surpasser._fetch_many_with_backoff = fake_fetch_many
    try:
        scraper = l1_surpasser.GeMCategoryScraper(
            category_url="https://mkp.gem.gov.in/some-category/search",
            max_price=max_price,
        )
        products, stats = scraper._execute_full_scrape({"pages_fetched": 0, "restarts": 0})
    finally:
        l1_surpasser._fetch_with_backoff = original_fetch
        l1_surpasser._fetch_many_with_backoff = original_fetch_many
    return products, stats, batches


def test_category_scrape_fetches_pages_in_batches():
    print("\n[1] GeMCategoryScraper fetches remaining pages concurrently in batches")
    products, stats, batches = run_category_scrape(total=30, max_price=None)
    check(f"collected all 30 products (got {len(products)})", len(products) == 30)
    check(f"pages 2-3 were fetched in one concurrent batch (batches: {batches})", batches == [2])
    check(f"pages_fetched counts all 3 pages (got {stats['pages_fetched']})", stats["pages_fetched"] == 3)


def test_category_scrape_still_stops_early_on_max_price():
    print("\n[2] Batched pagination still stops once a page is entirely above max_price")
    # 10 pages; page 3's cheapest product is 2100 > 1500, so the scrape stops there.
    products, stats, batches = run_category_scrape(total=100, max_price=1500)
    check(f"stopped after page 3 (got {len(products)} products)", len(products) == 30)
    check(f"no further batch was requested after the stop (batches: {batches})", batches == [4])


def test_fast_price_scrape_uses_one_sorted_request():
    print("\n[3] _fast_price_scrape reads one price-ascending page instead of every page")

    class FakeScraper(GeMScraper):
        def __init__(self):
            super().__init__()
            self.urls = []

        def _fetch(self, url, retries=3):
            self.urls.append(url)
            return json.dumps({
                "number_of_results": 500,
                "catalogs": [{"final_price": {"value": 900}}, {"final_price": {"value": 700}}],
            })

    scraper = FakeScraper()
    result = scraper._fast_price_scrape(
        "https://mkp.gem.gov.in/some-category/search", {"c1": "Brown / Tan"}, "Delhi"
    )
    check(f"exactly one request for a 500-product category (got {len(scraper.urls)})", len(scraper.urls) == 1)
    check("request is sorted price-ascending", "sort_type=price_in_asc" in scraper.urls[0])
    check("filter value is normalized into the query", "c1=Brown" in scraper.urls[0])
    check("location is sent", "localized_search=Delhi" in scraper.urls[0])
    check(f"min_price and total come from page 1 (got {result})",
          result["min_price"] == 700 and result["total"] == 500)


def test_rebuild_filter_values_matches_short_names():
    print("\n[4] GeMCrawler._rebuild_filter_values matches short names and dedupes values")
    gc = crawler_mod.GeMCrawler.__new__(crawler_mod.GeMCrawler)
    filters = [
        {"filterName": "BIS", "values": []},
        {"filterName": "Color", "values": ["Red"]},
        {"filterName": "Unused", "values": []},
    ]
    products = [
        {"specs": {"B.I.S": "Yes", "Color": "Red"}},
        {"specs": {"color": "Blue", "B.I.S": "Yes"}},
    ]
    out = gc._rebuild_filter_values(products, filters)
    by_name = {f["filterName"]: f["values"] for f in out}
    check(f'"B.I.S" spec filled the short "BIS" filter (got {by_name.get("BIS")})', by_name.get("BIS") == ["Yes"])
    check(f"Color gained Blue without duplicating Red (got {by_name.get('Color')})", by_name.get("Color") == ["Red", "Blue"])
    check("filters with no values are dropped", "Unused" not in by_name)


def test_name_resolver_memoizes():
    print("\n[5] make_name_resolver runs the fuzzy match once per distinct spec name")
    calls = [0]

    def counting_match(a, b):
        calls[0] += 1
        return a.lower() == b.lower()

    resolve = make_name_resolver(["Color", "Size"], match=counting_match)
    results = [resolve("color") for _ in range(50)]
    check("resolved to the right name", all(r == "Color" for r in results))
    check(f"fuzzy match ran once, not 50 times (got {calls[0]} calls)", calls[0] == 1)
    check("exact names skip the fuzzy match", resolve("Size") == "Size" and calls[0] == 1)


def test_cache_evicts_expired_and_excess_entries():
    print("\n[6] main.py's scrape cache evicts expired entries and caps its size")
    import main

    main._cache.clear()
    original_max = main.CACHE_MAX_ENTRIES
    main.CACHE_MAX_ENTRIES = 3
    try:
        main._cache["stale"] = {"data": {}, "ts": time.time() - main.CACHE_TTL - 1}
        for i in range(4):
            main._cache_set(f"k{i}", {"i": i})
        check("expired entry was evicted", "stale" not in main._cache)
        check(f"cache is capped at 3 entries (got {len(main._cache)})", len(main._cache) == 3)
        check("the oldest entry was the one dropped", "k0" not in main._cache and "k3" in main._cache)
        check("a live entry is returned", main._cache_get("k3") == {"i": 3})
    finally:
        main.CACHE_MAX_ENTRIES = original_max
        main._cache.clear()


if __name__ == "__main__":
    test_category_scrape_fetches_pages_in_batches()
    test_category_scrape_still_stops_early_on_max_price()
    test_fast_price_scrape_uses_one_sorted_request()
    test_rebuild_filter_values_matches_short_names()
    test_name_resolver_memoizes()
    test_cache_evicts_expired_and_excess_entries()

    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed\n{'='*60}")
    sys.exit(1 if FAIL else 0)
