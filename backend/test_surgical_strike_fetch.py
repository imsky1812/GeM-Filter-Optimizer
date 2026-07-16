"""
Regression test for surgical_strike calling a nonexistent method.

Background: scraper.py's surgical_strike() called self._fetch_json_page(...)
for every counter-filter candidate -- a method that does not exist anywhere
in the codebase. Every call raised AttributeError, silently swallowed by a
bare `except: continue`, so counterFilters was always [] and the endpoint
returned a confident "no counter filters found" (HTTP 200) for every single
request. This test drives surgical_strike() with a real competitor page and
a real category-listing JSON response (via a fake _fetch) and asserts a
genuine counter-filter recommendation comes back.

Run: python test_surgical_strike_fetch.py
"""
import sys
import json

sys.path.insert(0, ".")

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


PRODUCT_HTML = """
<html><body>
<h1>Competitor Display Panel</h1>
<div class="price">Rs. 5,000</div>
<div id="feature_groups">
  <table><tr><td>Color</td><td>Red</td></tr></table>
</div>
</body></html>
"""


class FakeFetchScraper(GeMScraper):
    """Real GeMScraper with only the network boundary (_fetch) stubbed."""

    def __init__(self):
        # Skip the real __init__ (no live session/browser needed for this test)
        self._product_specs_cache = {}

    def _fetch(self, url, retries=3):
        if "format=json" in url:
            # Category listing page: one competitor at 6000, above target_price
            body = {"number_of_results": 1, "catalogs": [{"final_price": {"value": 6000}}]}
            return json.dumps(body)
        # Product detail page
        return PRODUCT_HTML


def test_surgical_strike_produces_a_real_counter_filter():
    print("\n[1] surgical_strike() returns a real counter-filter recommendation "
          "instead of silently swallowing every candidate")
    scraper = FakeFetchScraper()
    golden_filters = [{
        "filterKey": "c_color",
        "filterName": "Color",
        "isGolden": True,
        "values": ["Red", "Blue"],
    }]

    result = scraper.surgical_strike(
        product_url="https://mkp.gem.gov.in/p-competitor",
        category_url="https://mkp.gem.gov.in/some-category/search",
        target_price=5500,
        golden_filters=golden_filters,
        location="",
    )

    check("no top-level error", "error" not in result)
    check("matched the Color golden filter from the competitor's page",
          len(result.get("goldenMatches", [])) == 1)
    check(f"produced at least one counter filter (got {len(result.get('counterFilters', []))})",
          len(result.get("counterFilters", [])) > 0)

    if result.get("counterFilters"):
        cf = result["counterFilters"][0]
        check("counter filter recommends switching to Blue", cf["counterValue"] == "Blue")
        check(f"correctly resolved resultMinPrice from the fake category response (got {cf['resultMinPrice']})",
              cf["resultMinPrice"] == 6000)
        check("correctly flags this as a win (6000 > target_price 5500)", cf["wouldWin"] is True)


if __name__ == "__main__":
    test_surgical_strike_produces_a_real_counter_filter()

    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed\n{'='*60}")
    sys.exit(1 if FAIL else 0)
