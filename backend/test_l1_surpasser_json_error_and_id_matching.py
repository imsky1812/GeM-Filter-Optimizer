"""
Regression tests for two remaining findings in l1_surpasser.py from a
targeted bug-hunt review:

1. _fetch_page's `except ValueError as e: if len(e.args) >= 2 and
   isinstance(e.args[1], str):` only recognized the deliberate 2-arg
   ValueError raised for a non-JSON response. A malformed/truncated body
   that still starts with "{" (e.g. a partial WAF block) makes
   json.loads() raise json.JSONDecodeError, which IS a ValueError but with
   only one arg -- so it fails the 2-arg check, falls to `else: raise`,
   and propagates all the way out of scrape() and run() uncaught instead
   of degrading gracefully into the existing HTML-fallback recovery path.

2. Catalogue-id matching used `self._my_catalogue_id in p["catalogue_id"]`
   (substring, not equality) in four places. It's intentional to
   accommodate a caller providing just the product-family id without GeM's
   "-<variant>" suffix (e.g. "5116877" for "5116877-93229099418"), but an
   unanchored substring test can also match a shorter id inside an
   unrelated longer one (e.g. "116877" matching "45116877"),
   misidentifying a competitor as "me".

Run: python test_l1_surpasser_json_error_and_id_matching.py
"""
import sys
import json

sys.path.insert(0, ".")

import l1_surpasser
from l1_surpasser import GeMCategoryScraper, _catalogue_id_matches, _names_match

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


def make_category_scraper():
    return GeMCategoryScraper(
        session=None,  # never touched -- _fetch_with_backoff is monkeypatched
        category_url="https://mkp.gem.gov.in/some-category/search",
        my_catalogue_id="5116877-99999999999",
    )


def test_malformed_json_degrades_gracefully_not_uncaught():
    print("\n[1] A malformed (truncated) JSON body that still starts with "
          "'{' must raise the same 2-arg ValueError shape as a non-JSON "
          "response, not an uncaught json.JSONDecodeError")
    cat_scraper = make_category_scraper()

    original_fetch = l1_surpasser._fetch_with_backoff
    l1_surpasser._fetch_with_backoff = lambda session, url: '{"number_of_results": 5, "catalogs": [tr'
    try:
        raised_value_error = False
        args_shape_ok = False
        try:
            cat_scraper._fetch_page(1)
        except json.JSONDecodeError:
            pass  # this is exactly the bug -- old code lets this escape raw
        except ValueError as e:
            raised_value_error = True
            args_shape_ok = len(e.args) >= 2 and isinstance(e.args[1], str)
    finally:
        l1_surpasser._fetch_with_backoff = original_fetch

    check("raised ValueError (not a raw JSONDecodeError)", raised_value_error)
    check("with the 2-arg shape _execute_full_scrape's fallback handler expects",
          args_shape_ok)


def test_execute_full_scrape_does_not_crash_on_malformed_json():
    print("\n[2] _execute_full_scrape must route a malformed page-1 body "
          "into the HTML-fallback path instead of letting the exception "
          "propagate uncaught out of scrape()/run()")
    cat_scraper = make_category_scraper()

    original_fetch = l1_surpasser._fetch_with_backoff
    l1_surpasser._fetch_with_backoff = lambda session, url: '{"number_of_results": 5, "catalogs": [tr'
    # Stub the HTML fallback itself -- its own parsing correctness isn't
    # what this test is about; we're proving the exception gets routed
    # there instead of escaping uncaught.
    cat_scraper._scrape_html_fallback = lambda html_text, stats: ([], stats)
    try:
        crashed = False
        try:
            products, stats = cat_scraper._execute_full_scrape({"pages_fetched": 0, "restarts": 0})
        except json.JSONDecodeError:
            crashed = True
    finally:
        l1_surpasser._fetch_with_backoff = original_fetch

    check("_execute_full_scrape did not let JSONDecodeError escape uncaught", not crashed)


def test_catalogue_id_matching_prefix_and_exact():
    print("\n[3] _catalogue_id_matches supports exact match and the "
          "intentional product-family-prefix case")
    check("exact match", _catalogue_id_matches("5116877-93229099418", "5116877-93229099418"))
    check("product-family prefix (no variant suffix) matches",
          _catalogue_id_matches("5116877", "5116877-93229099418"))
    check("empty my_id never matches", not _catalogue_id_matches("", "5116877-93229099418"))


def test_catalogue_id_matching_rejects_unrelated_substring_collision():
    print("\n[4] _catalogue_id_matches must NOT match a shorter id that "
          "merely happens to appear as a substring inside an unrelated "
          "longer id")
    check(
        '"116877" must not match unrelated "45116877" (old substring check would)',
        not _catalogue_id_matches("116877", "45116877"),
    )
    check(
        '"116877" must not match unrelated "5116877-9" either (shares a suffix, not the id)',
        not _catalogue_id_matches("116877", "5116877-9"),
    )


def test_l1_names_match_short_golden_filter_name():
    print("\n[5] l1_surpasser.py's own _names_match (a separate copy of the "
          "same helper found in scraper.py) has the identical short-name "
          "false-negative bug, fixed the same way")
    check('BIS matches "B.I.S"', _names_match("BIS", "B.I.S"))
    check("two genuinely different short names do NOT match",
          not _names_match("BIS", "ISO"))


if __name__ == "__main__":
    test_malformed_json_degrades_gracefully_not_uncaught()
    test_execute_full_scrape_does_not_crash_on_malformed_json()
    test_catalogue_id_matching_prefix_and_exact()
    test_catalogue_id_matching_rejects_unrelated_substring_collision()
    test_l1_names_match_short_golden_filter_name()

    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed\n{'='*60}")
    sys.exit(1 if FAIL else 0)
