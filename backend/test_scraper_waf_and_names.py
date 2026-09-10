"""
Regression test for the shared names_match helper (exposed on GeMScraper as
_names_match).

A `len(k1) > 5` guard made two short but identical (post-normalization)
spec names -- e.g. a real golden facet "BIS" vs a differently-punctuated
"B.I.S" rendering on a product page -- never match, silently dropping that
filter's data.

Run: python test_scraper_waf_and_names.py
"""
import sys

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
    assert condition, name


def test_names_match_short_golden_filter_name():
    print("\n[1] _names_match must match a short real golden-filter name "
          "against a differently-punctuated rendering of the same name")
    scraper = GeMScraper()
    check('BIS matches "B.I.S" (short name, differs only in punctuation)',
          scraper._names_match("BIS", "B.I.S"))
    check('BIS matches "bis" (case only)', scraper._names_match("BIS", "bis"))
    check("two genuinely different short names still do NOT match",
          not scraper._names_match("BIS", "ISO"))
    check("two empty/punctuation-only names do NOT match",
          not scraper._names_match("...", "-"))


if __name__ == "__main__":
    test_names_match_short_golden_filter_name()

    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed\n{'='*60}")
    sys.exit(1 if FAIL else 0)
