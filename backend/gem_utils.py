"""
gem_utils.py — pure helpers shared by scraper.py, crawler.py, chain_hunt.py
and l1_surpasser.py.

These used to be copy-pasted into each module, and the copies drifted: a fix
to _names_match's short-name bug landed in two copies but not the third. Keep
a single implementation here instead.
"""
import re
from urllib.parse import parse_qs

# BeautifulSoup parser for every HTML parse in the app (lxml is much faster
# than the stdlib "html.parser" on large product pages).
HTML_PARSER = "lxml"

_INLINE_SPEC_KEYS = ("specifications", "product_specifications", "spec_params",
                     "params", "attributes", "properties", "features")

_FACET_VALUE_KEYS = ("facet_values", "topValues", "top_values", "values",
                     "entries", "options", "items", "terms")


def names_match(name1: str, name2: str) -> bool:
    """Check if two spec/filter names are equivalent."""
    n1 = name1.lower().strip().replace("::", "/")
    n2 = name2.lower().strip().replace("::", "/")
    if n1 == n2:
        return True
    k1 = re.sub(r'[^a-z0-9]', '', n1)
    k2 = re.sub(r'[^a-z0-9]', '', n2)
    # k1 == k2 is already an exact match once punctuation/whitespace is
    # stripped -- there's no ambiguity risk from a short name here (that
    # would be a concern for a substring/prefix test, not equality), so
    # only guard against both sides degenerating to an empty string.
    # Real golden facet names can be short (e.g. "BIS"), and requiring
    # len > 5 made those never match a differently-punctuated rendering
    # of the same name on a product detail page.
    return bool(k1) and k1 == k2


def make_name_resolver(names, match=names_match):
    """
    Return a memoized lookup: spec name -> the first entry of `names` equal
    to it, else the first one `match()` accepts, else None.

    The same spec names repeat on every product, so resolving each distinct
    name once (instead of re-running the fuzzy match for every product x
    spec x filter) removes almost all of the regex work.
    """
    names = list(names)
    exact = set(names)
    cache = {}

    def resolve(spec_name):
        if spec_name not in cache:
            if spec_name in exact:
                cache[spec_name] = spec_name
            else:
                cache[spec_name] = next((n for n in names if match(spec_name, n)), None)
        return cache[spec_name]

    return resolve


def seller_key(seller: dict) -> str:
    """
    Stable identifier for a seller in GeM's catalog JSON.

    GeM's seller object carries no "id" -- it uses "external_ref_id".
    Reading "id" left every seller_id empty, so seller counts came out 0:
    enough to downgrade real chain-hunt wins to PARTIAL and to make every
    L1 candidate look like it had too few sellers. Fall back to the
    display name so a seller is still counted if the ref id is missing.
    """
    if not isinstance(seller, dict):
        return ""
    for key in ("external_ref_id", "id", "seller_id"):
        val = str(seller.get(key) or "").strip()
        if val:
            return val
    return str(seller.get("name") or "").strip()


def parse_price(text: str):
    """Parse a price string into an integer, or None if it isn't a plausible price."""
    cleaned = re.sub(r'[₹,\s]', '', text)
    cleaned = re.sub(r'(?i)INR|Rs\.?', '', cleaned)
    m = re.search(r'(\d+(?:\.\d+)?)', cleaned)
    if m:
        val = float(m.group(1))
        if 10 <= val <= 10_000_000:
            return int(val)
    return None


def to_key(name: str) -> str:
    """Convert a human-readable name to a filter key."""
    key = re.sub(r'[^a-z0-9\s]', '', name.lower().strip())
    return re.sub(r'\s+', '_', key).strip('_')[:40]


def normalize_filter_value(val) -> str:
    """
    Normalize a spec filter value for the GeM search JSON API index.
    E.g. "Brown / Tan" -> "Brown", "Mesh fabrics" -> "Meshfabrics".

    GeM's index only matches multi-word spec values with the spaces removed.
    Measured live against three categories (every other encoding -- "+",
    "%20", a literal space, `key[]=`, quoted, upper/lowercase, hyphen, comma,
    repeated params -- returns 0):

        C6065E=Mesh fabrics   -> 0          C6065E=Meshfabrics       -> 11,112
        C8113E=Monochrome (Black) -> 0      C8113E=Monochrome(Black) -> 168

    The stripped queries select the right products (three sampled product
    pages all listed "Seat upholstery: Mesh fabrics") and partition the
    category exactly: for printers, Monochrome(Black) 168 + Colour 76 = 244,
    the full category.

    An earlier commit removed the stripping, believing it "corrupts the query
    into an unrelated, inflated result count". That inflation is real but has
    a different cause: GeM silently IGNORES a filter parameter whose key it
    doesn't recognise and returns the unfiltered total. Callers guard against
    that by comparing a filtered total against the category's baseline, not
    by leaving the spaces in.
    """
    if not isinstance(val, str):
        return str(val)
    if "/" in val:
        val = val.split("/")[0]
    return val.replace(":", "").replace(" ", "").strip()


def parse_fragment_params(fragment: str) -> dict:
    """Parse query params out of a URL fragment like "/?q=chair&page=1"."""
    if not fragment:
        return {}
    if fragment.startswith("/?"):
        qs = fragment[2:]
    elif fragment.startswith("?"):
        qs = fragment[1:]
    elif "?" in fragment:
        qs = fragment.split("?", 1)[1]
    else:
        qs = fragment
    return {
        k: v_list[0] if len(v_list) == 1 else v_list
        for k, v_list in parse_qs(qs, keep_blank_values=True).items()
    }


def extract_inline_specs(cat: dict) -> dict:
    """
    Extract specs directly from a catalog listing JSON item. GeM embeds specs
    in several possible fields under several naming patterns -- try them all.
    """
    specs = {}
    for key in _INLINE_SPEC_KEYS:
        items = cat.get(key, [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    name = (item.get("name") or item.get("key") or
                            item.get("label") or item.get("param_name") or "")
                    value = (item.get("value") or item.get("val") or
                             item.get("param_value") or "")
                    if name and value and len(str(value)) < 200:
                        specs[str(name).strip()] = str(value).strip()
        elif isinstance(items, dict):
            for name, value in items.items():
                if name and value and len(str(value)) < 200:
                    specs[str(name).strip()] = str(value).strip()
    return specs


def pull_facet_values(facet: dict) -> list:
    """Extract option values from a facet entry of the search JSON."""
    for key in _FACET_VALUE_KEYS:
        raw = facet.get(key, [])
        if not raw:
            continue
        vals = []
        for v in raw:
            if isinstance(v, dict):
                label = (v.get("name") or v.get("value") or
                         v.get("code") or v.get("label") or "")
            else:
                label = str(v)
            label = str(label).strip()
            if label and label.lower() not in ("true", "false", "null", ""):
                vals.append(label)
        if vals:
            return vals
    return []


def build_product_url(cat: dict) -> str:
    """Build a full product URL from a catalog item's url-parts array."""
    url_parts = cat.get("url", [])
    if url_parts and len(url_parts) >= 3:
        return f"https://mkp.gem.gov.in/{'/'.join(url_parts)}"
    return ""


def extract_specs_from_soup(soup) -> dict:
    """
    Extract all specifications from a parsed product detail page.
    Specs are in tables inside #feature_groups, with td key-value pairs,
    plus .param-container rows inside .specifications.
    """
    specs = {}

    feature_groups = soup.select_one("#feature_groups")
    if feature_groups:
        for table in feature_groups.find_all("table"):
            for row in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if len(cells) >= 2 and cells[0] and cells[1] and len(cells[1]) < 200:
                    specs[cells[0]] = cells[1]

    specs_div = soup.select_one(".specifications")
    if specs_div:
        for pc in specs_div.select(".param-container"):
            key_el = pc.select_one(".key_name")
            val_el = pc.select_one(".key_value")
            if key_el and val_el:
                name = key_el.get_text(strip=True)
                value = val_el.get_text(strip=True)
                if name and value and name not in specs:
                    specs[name] = value

    return specs
