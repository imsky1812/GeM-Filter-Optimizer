"""
Regression tests for two Critical bugs in l1_surpasser.py's L1ChainSurpasser:

1. `_verify_filter_candidate` treated a filter that returns ZERO results for
   the whole category (including the seller's own listing) as a winning
   "l1_eliminated" -- because the empty-products special case fired before
   the "is my product still present" check ever got a chance to run. A
   filter that shows nobody, including you, is not a win.

2. A transient scrape error while verifying one candidate ("scrape_error")
   was logged and treated identically to "I checked and this filter
   genuinely doesn't eliminate the L1" (not_eliminated). If every candidate
   in an iteration happened to hit a scrape error, the algorithm declared a
   confident "STUCK / unbypassable" verdict caused purely by infrastructure
   failure, not because no real path exists.

Run: python test_l1_surpasser_stuck_verdicts.py
"""
import sys

sys.path.insert(0, ".")

import l1_surpasser
from l1_surpasser import L1ChainSurpasser

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


def make_surpasser():
    return L1ChainSurpasser(
        category_url="https://mkp.gem.gov.in/some-category/search",
        my_catalogue_id="5116877-99999999999",
        my_price=5000,
    )


CURRENT_L1 = {"catalogue_id": "5116877-11111111111", "price": 3000, "name": "Cheap Competitor"}


class FakeCategoryScraperEmpty:
    """Every candidate filter wipes the category to zero results."""

    def __init__(self, *args, **kwargs):
        pass

    def scrape(self):
        return {
            "products": [],
            "scrape_stats": {"pages_fetched": 1},
            "my_product": None,
            "my_product_rank": None,
        }


class FakeCategoryScraperAlwaysErrors:
    """Every scrape attempt raises, simulating a transient infra failure."""

    def __init__(self, *args, **kwargs):
        pass

    def scrape(self):
        raise RuntimeError("simulated transient scrape failure")


def test_empty_result_is_not_treated_as_a_win():
    print("\n[1] A filter that returns zero products (including my own) must "
          "NOT be reported as l1_eliminated")
    surpasser = make_surpasser()
    original_scraper_cls = l1_surpasser.GeMCategoryScraper
    l1_surpasser.GeMCategoryScraper = FakeCategoryScraperEmpty
    try:
        result = surpasser._verify_filter_candidate({"c1": "SomeValue"}, CURRENT_L1)
    finally:
        l1_surpasser.GeMCategoryScraper = original_scraper_cls

    check(f"status is NOT l1_eliminated (got {result['status']!r})",
          result["status"] != "l1_eliminated")
    check(f"status correctly identifies my product as missing (got {result['status']!r})",
          result["status"] == "my_product_missing")


def test_scrape_error_does_not_count_as_verified_not_eliminated():
    print("\n[2] A transient scrape error during candidate verification must "
          "not be logged/counted the same as a real 'not eliminated' result")
    import time
    surpasser = make_surpasser()
    surpasser._t_start = time.time()  # normally set by run(), which we bypass here
    original_scraper_cls = l1_surpasser.GeMCategoryScraper
    l1_surpasser.GeMCategoryScraper = FakeCategoryScraperAlwaysErrors
    try:
        filter_options = {
            "c1": {"name": "Color", "values": ["Red", "Blue"]},
        }
        committed = surpasser._try_single_filters(
            iteration=1,
            current_L1=CURRENT_L1,
            filter_options=filter_options,
            my_golden={},
        )
    finally:
        l1_surpasser.GeMCategoryScraper = original_scraper_cls

    check("no filter was committed (every candidate hit a scrape error)", committed is False)
    check(f"scrape_error_count was tracked (got {surpasser._scrape_error_count})",
          surpasser._scrape_error_count == 2)
    check(
        "iteration log records these as scrape_error, not not_eliminated",
        all(entry["result"] == "scrape_error" for entry in surpasser._iteration_log),
    )


if __name__ == "__main__":
    test_empty_result_is_not_treated_as_a_win()
    test_scrape_error_does_not_count_as_verified_not_eliminated()

    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed\n{'='*60}")
    sys.exit(1 if FAIL else 0)
