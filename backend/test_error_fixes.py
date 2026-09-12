"""
Regression tests for the error fixes:

1. JSON read through page.content() came back HTML-escaped ("A &amp; B"),
   corrupting product names and filter values. Fetches now read the raw
   response body, and only real HTML pages wait for rendered content.
2. chain_hunt compared spec values exactly when scoring but case-insensitively
   when expanding, so "MESH" vs "Mesh" counted a real competitor as gone.
3. A failed surgical-strike price check was reported as an untapped niche.
4. /l1-surpass crashed with HTTP 500 when a page fetch exhausted its retries.
5. Endpoints other than /scrape opened any URL in the server's browser.

Run: python test_error_fixes.py
"""
import json
import sys
import threading
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, ".")

import chain_hunt
import crawler as crawler_mod
import l1_surpasser
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


# ───────────────────────────────────────────────────────────────────────────
# 1. Raw JSON bodies, no HTML escaping
# ───────────────────────────────────────────────────────────────────────────

def test_extract_json_text():
    print("\n[1] _extract_json_text returns real JSON and rejects HTML pages")
    extract = crawler_mod._extract_json_text
    check("raw JSON body is returned as-is", extract('{"t": "A & B"}') == '{"t": "A & B"}')
    viewer = '<html><body><pre style="x">{"t": "A &amp; B &lt;C&gt;"}</pre></body></html>'
    check("Chromium's JSON viewer is unescaped back to the real text",
          json.loads(extract(viewer))["t"] == "A & B <C>")
    check("an HTML page with braces in inline JS is not mistaken for JSON",
          extract("<html><script>var x = {a: 1};</script></html>") is None)


def make_bm():
    bm = crawler_mod.BrowserManager.__new__(crawler_mod.BrowserManager)
    bm._loop = None
    bm._loop_thread = None
    bm._loop_ready = threading.Event()
    bm._playwright = None
    bm._browser = MagicMock()
    bm._browser.is_connected.return_value = True
    bm._context = MagicMock()
    bm._initialized = True
    bm._crash_detected = False
    bm._init_lock = None
    bm._pool_lock = None
    bm._page_slots = None
    bm._page_pool = []
    bm._cookie_refresh_lock = None
    return bm


def make_page(body, rendered, url):
    response = MagicMock()
    response.text = AsyncMock(return_value=body)
    page = MagicMock()
    page.goto = AsyncMock(return_value=response)
    page.content = AsyncMock(return_value=rendered)
    page.url = url
    page.is_closed.return_value = False
    page.close = AsyncMock(return_value=None)
    page.wait_for_selector = AsyncMock(return_value=None)
    return page


def test_fetch_returns_raw_json_body():
    print("\n[2] BrowserManager.fetch returns the raw JSON body, not the escaped DOM")
    bm = make_bm()
    raw = '{"catalogs": [{"title": "Steel & Aluminium <Heavy> Chair"}]}'
    page = make_page(
        body=raw,
        rendered='<html><body><pre>{"catalogs": [{"title": "Steel &amp; Aluminium &lt;Heavy&gt; Chair"}]}</pre></body></html>',
        url="https://mkp.gem.gov.in/x/search?format=json",
    )
    bm._context.new_page = AsyncMock(return_value=page)
    result = bm.fetch("https://mkp.gem.gov.in/x/search?page=1&format=json")
    check(f"title keeps its & and < > characters (got {json.loads(result)['catalogs'][0]['title']!r})",
          json.loads(result)["catalogs"][0]["title"] == "Steel & Aluminium <Heavy> Chair")


def test_fetch_waits_for_real_html_pages():
    print("\n[3] An HTML page with inline JS braces still waits for rendered content")
    bm = make_bm()
    page = make_page(
        body="<html><script>var cfg = {a: 1};</script></html>",
        rendered="<html><div id='feature_groups'>rendered</div></html>",
        url="https://mkp.gem.gov.in/p-1-2-cat.html",
    )
    bm._context.new_page = AsyncMock(return_value=page)
    result = bm.fetch("https://mkp.gem.gov.in/p-1-2-cat.html")
    check("wait_for_selector ran for the HTML page", page.wait_for_selector.call_count == 1)
    check("the rendered DOM is returned", "rendered" in result)


# ───────────────────────────────────────────────────────────────────────────
# 2. Case-insensitive spec matching in chain hunt
# ───────────────────────────────────────────────────────────────────────────

class CaseFakeScraper:
    def _normalize_url(self, url):
        return url, {}

    def _build_product_url(self, cat):
        return f"https://mkp.gem.gov.in/p-{cat['id']}"

    def _extract_inline_specs(self, cat):
        return dict(cat["specs_for_test"])

    def _names_match(self, a, b):
        return a.strip().lower() == b.strip().lower()

    def _to_key(self, name):
        return name.lower()

    def _extract_facet_defs(self, facets):
        return [{"filterName": "Color", "filterKey": "color", "isGolden": True, "type": "", "facetValues": []}]

    def _enrich_single_product(self, product, name_to_code):
        return product

    def _fetch(self, url, retries=3):
        catalogs = [
            # The only cheaper competitor lists its spec in upper case.
            {"id": "blocker", "final_price": {"value": 500}, "title": "b", "brand": "x",
             "seller": {"id": "s1", "name": "s1"}, "oem_id": "", "specs_for_test": {"Color": "MESH"}},
            {"id": "other", "final_price": {"value": 2000}, "title": "o", "brand": "x",
             "seller": {"id": "s2", "name": "s2"}, "oem_id": "", "specs_for_test": {"Color": "Fabric"}},
        ]
        return json.dumps({"number_of_results": 2, "facets": {}, "catalogs": catalogs})

    def _chain_scrape(self, url, extra_params, location=""):
        # Live check returns nothing, so a path is only reported as an
        # untapped WIN if local data (wrongly) says nobody matches it.
        return {"min_price": None, "total": 0, "seller_count": 0, "products": [], "error": False}


def test_chain_hunt_spec_match_ignores_case():
    print('\n[4] chain_hunt treats a "MESH" product as matching the "Mesh" filter value')
    result = chain_hunt.smart_l1_discovery(
        CaseFakeScraper(),
        category_url="https://mkp.gem.gov.in/some-category/search",
        target_price=1000,
        golden_filters=[{"filterKey": "color", "filterName": "Color", "isGolden": True,
                         "values": ["Mesh", "Fabric"]}],
    )
    check("Color=Mesh is not reported as a win (its competitor is still there)",
          not any(p["activeFilters"].get("color") == "Mesh" for p in result["winningPaths"]))
    check("Color=Mesh is kept as an unconfirmed lead with its local match counted",
          any(p["activeFilters"].get("color") == "Mesh" and p["totalProducts"] == 1
              for p in result["unconfirmedPaths"]))


# ───────────────────────────────────────────────────────────────────────────
# 3. Surgical strike failures are not "untapped"
# ───────────────────────────────────────────────────────────────────────────

def test_surgical_strike_failed_check_is_not_untapped():
    print("\n[5] A failed counter-filter price check isn't reported as an untapped niche")

    class FailingPriceScraper(GeMScraper):
        def _fetch(self, url, retries=3):
            if "format=json" in url:
                raise RuntimeError("Fetch failed after 3 attempts: blocked")
            return ('<html><body><h1>Competitor</h1><div id="feature_groups">'
                    '<table><tr><td>Color</td><td>Red</td></tr></table></div></body></html>')

    result = FailingPriceScraper().surgical_strike(
        product_url="https://mkp.gem.gov.in/p-competitor",
        category_url="https://mkp.gem.gov.in/some-category/search",
        target_price=5000,
        golden_filters=[{"filterKey": "c_color", "filterName": "Color", "isGolden": True,
                         "values": ["Red", "Blue"]}],
    )
    check("the failed check produced no counter-filter", result["counterFilters"] == [])
    check(f"nothing is claimed as verified (got unverified={result['unverified']})", result["unverified"] == 0)
    check(f"the failure is counted (got failedChecks={result.get('failedChecks')})", result.get("failedChecks") == 1)


def make_strike_scraper(total, catalog_min_price=6000, baseline_total=40):
    """GeMScraper whose competitor page is fixed, whose filtered category query
    returns `total` results, and whose unfiltered baseline is `baseline_total`."""
    class FakeStrikeScraper(GeMScraper):
        def _fetch(self, url, retries=3):
            if "c_color=" in url:
                catalogs = ([{"final_price": {"value": catalog_min_price}}] if total else [])
                return json.dumps({"number_of_results": total, "catalogs": catalogs})
            if "format=json" in url:
                return json.dumps({"number_of_results": baseline_total,
                                   "catalogs": [{"final_price": {"value": 3000}}]})
            return ('<html><body><h1>Competitor</h1><div id="feature_groups">'
                    '<table><tr><td>Color</td><td>Red</td></tr></table></div></body></html>')
    return FakeStrikeScraper()


GOLDEN_COLOR = [{"filterKey": "c_color", "filterName": "Color", "isGolden": True,
                 "values": ["Red", "Blue"]}]


def run_strike(scraper, location=""):
    return scraper.surgical_strike(
        product_url="https://mkp.gem.gov.in/p-competitor",
        category_url="https://mkp.gem.gov.in/some-category/search",
        target_price=5000,
        golden_filters=GOLDEN_COLOR,
        location=location,
    )


def test_zero_results_is_not_an_untapped_niche():
    print("\n[6] A counter-filter GeM returns 0 results for is flagged unrecognized, not untapped")
    result = run_strike(make_strike_scraper(total=0))
    cf = result["counterFilters"][0]
    check(f"verification says unrecognized (got {cf['verification']!r})", cf["verification"] == "unrecognized")
    check("it is not presented as a win", cf["wouldWin"] is False)
    check("the old untapped claim is gone", "isUntapped" not in cf)
    check(f"it counts as unverified (got {result['unverified']})", result["unverified"] == 1)
    check("no untapped tally is reported at all", "untapped" not in result)


def test_zero_results_with_a_location_is_only_unverified():
    print("\n[7] With a location applied, an empty result is 'unverified' -- it could be genuine")
    result = run_strike(make_strike_scraper(total=0), location="Kerala")
    check(f"verification says unverified (got {result['counterFilters'][0]['verification']!r})",
          result["counterFilters"][0]["verification"] == "unverified")


def test_filter_ignored_by_gem_is_not_a_result():
    print("\n[8] A filter GeM ignored (result == the whole category) verifies nothing")
    # Filtered query returns exactly the unfiltered baseline: GeM dropped the key.
    result = run_strike(make_strike_scraper(total=40, baseline_total=40))
    cf = result["counterFilters"][0]
    check(f"verification says ignored (got {cf['verification']!r})", cf["verification"] == "ignored")
    check("it is not presented as a win", cf["wouldWin"] is False)
    check(f"it counts as unverified (got {result['unverified']})", result["unverified"] == 1)


def test_real_results_are_confirmed_and_can_win():
    print("\n[8] A counter-filter with real results is confirmed, and wins when it beats the target")
    result = run_strike(make_strike_scraper(total=12, catalog_min_price=6000))
    cf = result["counterFilters"][0]
    check(f"verification says confirmed (got {cf['verification']!r})", cf["verification"] == "confirmed")
    check("min price 6000 beats the 5000 target, so it's a win", cf["wouldWin"] is True)
    check(f"win is tallied (got wins={result['wins']})", result["wins"] == 1)
    check(f"nothing is left unverified (got {result['unverified']})", result["unverified"] == 0)


# ───────────────────────────────────────────────────────────────────────────
# 4. L1 surpasser reports fetch failures instead of crashing
# ───────────────────────────────────────────────────────────────────────────

def test_l1_run_reports_fetch_failure():
    print("\n[6] L1ChainSurpasser.run() returns scrape_failed when a fetch exhausts its retries")

    class ExhaustedScraper:
        def __init__(self, *args, **kwargs):
            pass

        def scrape(self):
            raise RuntimeError("Fetch failed after 5 attempts: timeout")

    original = l1_surpasser.GeMCategoryScraper
    l1_surpasser.GeMCategoryScraper = ExhaustedScraper
    try:
        result = l1_surpasser.L1ChainSurpasser(
            "https://mkp.gem.gov.in/some-category/search", "123-456", 5000
        ).run()
    finally:
        l1_surpasser.GeMCategoryScraper = original
    check(f"status is scrape_failed (got {result['status']!r})", result["status"] == "scrape_failed")


# ───────────────────────────────────────────────────────────────────────────
# 5. URL validation
# ───────────────────────────────────────────────────────────────────────────

def test_require_gem_url():
    print("\n[7] _require_gem_url accepts GeM URLs and rejects everything else")
    from fastapi import HTTPException
    import main

    def rejected(url):
        try:
            main._require_gem_url(url, "url")
            return False
        except HTTPException as e:
            return e.status_code == 400

    check("GeM URL without a scheme is accepted and normalized",
          main._require_gem_url("mkp.gem.gov.in/chairs/search", "url") == "https://mkp.gem.gov.in/chairs/search")
    check("cloud metadata address is rejected", rejected("http://169.254.169.254/latest/meta-data"))
    check("localhost is rejected", rejected("http://localhost:8000/api/cache"))
    check("userinfo trick (gem host before @) is rejected", rejected("https://mkp.gem.gov.in@evil.com/"))
    check("look-alike suffix domain is rejected", rejected("https://gem.gov.in.evil.com/"))
    check("GeM host only in the query string is rejected", rejected("https://evil.com/?u=mkp.gem.gov.in"))
    check("empty URL is rejected", rejected(""))


# ───────────────────────────────────────────────────────────────────────────
# 6. Seller ids
# ───────────────────────────────────────────────────────────────────────────

def test_seller_key_uses_external_ref_id():
    print("\n[9] seller ids come from GeM's external_ref_id, not the absent id field")
    from gem_utils import seller_key
    # Shape taken from a real GeM catalog response: no "id" anywhere.
    real = {"name": "KRISHNA ENTERPRISES", "external_ref_id": "Comp9eb0c8aa",
            "display_sold_as": "OEM", "rating": "4.5"}
    check("real GeM seller object yields its external_ref_id", seller_key(real) == "Comp9eb0c8aa")
    check("falls back to the seller name when no ref id is present",
          seller_key({"name": "L & P INTERNATIONAL"}) == "L & P INTERNATIONAL")
    check("an empty seller object yields an empty id", seller_key({}) == "")

    cat = {"id": "1-2", "final_price": {"value": 100}, "title": "t", "seller": real}
    gc = crawler_mod.GeMCrawler.__new__(crawler_mod.GeMCrawler)
    check("crawler product carries a non-empty seller_id",
          gc._parse_catalog_item(cat)["seller_id"] == "Comp9eb0c8aa")
    check("l1 surpasser product carries a non-empty seller_id",
          l1_surpasser.GeMCategoryScraper._parse_product(cat)["seller_id"] == "Comp9eb0c8aa")


# ───────────────────────────────────────────────────────────────────────────
# 7. Multi-word filter values
# ───────────────────────────────────────────────────────────────────────────

def test_multi_word_values_have_spaces_stripped():
    print("\n[11] Multi-word filter values are sent with spaces stripped, the only form GeM matches")
    from gem_utils import normalize_filter_value as norm
    check("'Mesh fabrics' -> 'Meshfabrics'", norm("Mesh fabrics") == "Meshfabrics")
    check("'Monochrome (Black)' keeps its brackets", norm("Monochrome (Black)") == "Monochrome(Black)")
    check("single words are unchanged", norm("Leatherette") == "Leatherette")
    check("a slashed value still takes the first option", norm("Brown / Tan") == "Brown")
    check("non-strings survive", norm(12) == "12")


class IgnoredLiveCheckScraper(CaseFakeScraper):
    """Live verification comes back flagged as ignored by GeM."""

    def _chain_scrape(self, url, extra_params, location=""):
        return {"min_price": 500, "total": 2, "seller_count": 2,
                "products": [], "error": False, "ignored": True}


def test_chain_hunt_treats_an_ignored_live_check_as_unconfirmed():
    print("\n[12] A live check GeM ignored becomes an unconfirmed lead, never a verified path")
    result = chain_hunt.smart_l1_discovery(
        IgnoredLiveCheckScraper(),
        category_url="https://mkp.gem.gov.in/some-category/search",
        target_price=1000,
        golden_filters=[{"filterKey": "color", "filterName": "Color", "isGolden": True,
                         "values": ["Mesh", "Fabric"]}],
    )
    check("no path is reported as verified", result["winningPaths"] == [])
    check(f"the leads are surfaced as unconfirmed (got {len(result['unconfirmedPaths'])})",
          len(result["unconfirmedPaths"]) > 0)


def test_and_facet_values_are_queried_by_component():
    print("\n[14] On an 'and' facet, a composite value is tried one component at a time")
    from gem_utils import query_values_for
    check("and-facet value splits into components",
          query_values_for("USB Port,Wi-Fi", "MultiselectAnd") == ["USB Port", "Wi-Fi"])
    check("or-facet value stays whole",
          query_values_for("Monochrome (Black)", "MultiselectOr") == ["Monochrome (Black)"])

    queried = []

    class AndFacetScraper(GeMScraper):
        def _fetch(self, url, retries=3):
            if "c_conn=" in url:
                queried.append(url.split("c_conn=")[1].split("&")[0])
                return json.dumps({"number_of_results": 12,
                                   "catalogs": [{"final_price": {"value": 9000}}]})
            if "format=json" in url:
                return json.dumps({"number_of_results": 90,
                                   "catalogs": [{"final_price": {"value": 3000}}]})
            return ('<html><body><h1>P</h1><div id="feature_groups">'
                    '<table><tr><td>Connectivity</td><td>USB Port</td></tr></table></div></body></html>')

    result = AndFacetScraper().surgical_strike(
        product_url="https://mkp.gem.gov.in/p-x",
        category_url="https://mkp.gem.gov.in/some-category/search",
        target_price=5000,
        golden_filters=[{"filterKey": "c_conn", "filterName": "Connectivity", "isGolden": True,
                         "type": "MultiselectAnd", "values": ["USB Port", "USB Port,Wi-Fi"]}],
    )
    vals = [cf["counterValue"] for cf in result["counterFilters"]]
    check(f"only the component the competitor lacks is suggested (got {vals})", vals == ["Wi-Fi"])
    check(f"the joined value was never sent to GeM (sent: {queried})",
          queried and all("," not in q and "%2C" not in q for q in queried))
    check("the component check is a real, confirmed result",
          result["counterFilters"][0]["verification"] == "confirmed")


def test_l1_page_url_normalizes_filter_values():
    print("\n[13] The L1 surpasser sends normalized filter values too")
    scraper = l1_surpasser.GeMCategoryScraper(
        category_url="https://mkp.gem.gov.in/some-category/search",
        active_filters={"C6065E": "Mesh fabrics"},
    )
    url = scraper._build_page_url(1)
    check(f"value is space-stripped in the query (got {url.split('C6065E=')[-1]!r})",
          "C6065E=Meshfabrics" in url)


if __name__ == "__main__":
    test_extract_json_text()
    test_fetch_returns_raw_json_body()
    test_fetch_waits_for_real_html_pages()
    test_chain_hunt_spec_match_ignores_case()
    test_surgical_strike_failed_check_is_not_untapped()
    test_zero_results_is_not_an_untapped_niche()
    test_zero_results_with_a_location_is_only_unverified()
    test_filter_ignored_by_gem_is_not_a_result()
    test_multi_word_values_have_spaces_stripped()
    test_chain_hunt_treats_an_ignored_live_check_as_unconfirmed()
    test_and_facet_values_are_queried_by_component()
    test_l1_page_url_normalizes_filter_values()
    test_real_results_are_confirmed_and_can_win()
    test_l1_run_reports_fetch_failure()
    test_require_gem_url()
    test_seller_key_uses_external_ref_id()

    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed\n{'='*60}")
    sys.exit(1 if FAIL else 0)
