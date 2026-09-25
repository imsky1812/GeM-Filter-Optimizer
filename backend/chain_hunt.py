"""
chain_hunt.py — In-Memory Complete Dataset Search (IMCDS) with Live Verification

Provides highly-efficient in-memory search for golden filter paths:
1. Paginated scraping of all products in the category (up to 20 pages).
   Stops early when prices exceed target_price * 1.5.
2. Extract and build clean filter definitions and mapping.
3. Run BFS Set-Cover search over combinations of golden filters in-memory.
4. Verify the top candidates with a live API request to GeM in parallel.
5. Format and return optimal, verified L1 paths.
"""

import collections
import json
import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urlencode

from gem_utils import (
    is_multi_value,
    make_name_resolver,
    query_values_for,
    seller_key,
    split_composite_value,
)

logger = logging.getLogger("chain-hunt")


# ── Live Category Scraper for Verification ───────────────────────────────────

def _chain_scrape(self, url: str, extra_params: dict, location: str = "") -> dict:
    """
    Scrape page 1 & 2 of the category with filters applied using Playwright crawler.
    Returns {min_price, products, facets, total, seller_count, error}
    """
    from crawler import GeMCrawler
    crawler = GeMCrawler()
    res = crawler.crawl_filtered_prices(url, extra_params, location)
    res["facets"] = {}
    return res


def _sort_spec_values(values):
    """Sort filter values by their leading number (descending), then text."""
    def parse_value(v):
        m = re.search(r'[-+]?\d*\.\d+|\d+', str(v))
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                pass
        return -1.0
    return sorted(values, key=lambda x: (parse_value(x), str(x)), reverse=True)


def _stuck_result(api_calls: int, golden_filter_count: int, t_start: float, target_price: int) -> dict:
    return {
        "winningPaths": [],
        "totalPaths": 0,
        "totalApiCalls": api_calls,
        "status": "STUCK",
        "goldenFilterCount": golden_filter_count,
        "elapsed": round(time.time() - t_start, 1),
        "bestAchievablePrice": None,
        "marketMinPrice": None,
        "targetPrice": target_price,
        "sampleSize": 0,
    }


# How many of each path's cheapest listings get priced from their own page.
LIVE_PRICE_DEPTH = 24


def _reprice_from_pages(live_res: dict, page_prices: dict) -> None:
    """
    Swap search prices for product-page prices where we have them, and
    recompute the path's floor from the result.

    Listings we couldn't page-price keep their search price. The floor is
    the lowest price across both, so a single stale listing that is really
    under the seller's price is enough to take the win away.
    """
    products = live_res.get("products") or []
    checked = corrected = 0
    for p in products:
        p.setdefault("searchPrice", p["price"])
        live = page_prices.get(p.get("url"))
        if live is None:
            continue
        checked += 1
        p["pricePageChecked"] = True
        p["price"] = live
        if live != p["searchPrice"]:
            corrected += 1
    products.sort(key=lambda p: p["price"])
    if products:
        floor = products[0]["price"]
        if live_res.get("min_price") is None or floor < live_res["min_price"]:
            live_res["min_price"] = floor
    live_res["priceCheck"] = {"checked": checked, "corrected": corrected,
                              "fetched": len(products),
                              "listings": live_res.get("total", 0)}


def _unreachable_result(api_calls: int, golden_filter_count: int, t_start: float,
                        target_price: int, reason: str) -> dict:
    """
    We never got a readable answer out of GeM. This is NOT the same as
    searching the category and finding no winning path: callers must not
    report it as "no combination makes you L1".
    """
    out = _stuck_result(api_calls, golden_filter_count, t_start, target_price)
    out["status"] = "UNREACHABLE"
    out["error"] = True
    out["errorReason"] = reason
    return out


# ── Main Algorithm: In-Memory Complete Dataset Search (IMCDS) ───────────────

def smart_l1_discovery(self, category_url: str, target_price: int,
                       golden_filters: list, location: str = "",
                       excluded_filter_keys: list = None,
                       mandatory_filters: list = None) -> dict:
    """
    In-Memory Complete Dataset Search (IMCDS) with Live Verification.

    1. Paginated scraping of all products in the category (up to 20 pages).
       Stops early when prices exceed target_price * 1.5.
    2. Extract and build clean filter definitions and mapping.
    3. Run BFS Set-Cover search over combinations of golden filters in-memory.
    4. Verify the top candidates with a live API request to GeM in parallel.
    5. Format and return optimal, verified L1 paths.
    """
    t_start = time.time()
    api_calls = [0]

    # Parse URL
    category_url, base_extra = self._normalize_url(category_url)

    # ── STEP 1: BULK PAGINATED SCRAPING ──
    base_url = category_url.split("#")[0].split("?")[0]
    if not base_url.endswith("/search"):
        base_url = base_url.rstrip("/")

    extra_qs = ""
    if base_extra:
        filtered = {k: v for k, v in base_extra.items() if k.lower() not in ("page", "format")}
        if filtered:
            extra_qs = "&" + urlencode(filtered)
    if location and location.lower() not in ("", "all india", "all"):
        extra_qs += "&localized_search=" + quote(location)

    # Force price ascending sort so we get the cheapest products on early pages
    extra_qs += "&sort_type=price_in_asc"

    # Fetch Page 1 to get total results count and facets
    page1_url = f"{base_url}?page=1&format=json{extra_qs}"
    logger.info(f"[IMCDS] Fetching Page 1: {page1_url}")

    def _fetch_page1(url_for_page1):
        """Page 1 carries the totals and facets the whole search is built on."""
        body = self._fetch(url_for_page1).strip()
        api_calls[0] += 1
        if not body.startswith("{"):
            raise ValueError(f"response was not JSON: {body[:120]}")
        return json.loads(body)

    try:
        data1 = _fetch_page1(page1_url)
    except Exception as e:
        # A short GeM category link (the kind its own homepage uses) serves the
        # single-page app instead of JSON. The scan already follows these to the
        # real category; the hunt has to do the same or it reports "no path" for
        # a category it never actually read.
        logger.info(f"[IMCDS] Page 1 unreadable ({e}); checking for a category alias")
        from crawler import GeMCrawler
        canonical = GeMCrawler()._resolve_canonical_category(base_url)
        if not canonical:
            logger.error(f"[IMCDS] Could not read Page 1 for {base_url}: {e}")
            return _unreachable_result(api_calls[0], len(golden_filters), t_start,
                                       target_price, str(e))
        logger.info(f"[IMCDS] Following canonical category {canonical}")
        base_url = canonical
        page1_url = f"{base_url}?page=1&format=json{extra_qs}"
        try:
            data1 = _fetch_page1(page1_url)
        except Exception as e2:
            logger.error(f"[IMCDS] Could not read Page 1 for {canonical}: {e2}")
            return _unreachable_result(api_calls[0], len(golden_filters), t_start,
                                       target_price, str(e2))

    total_results = data1.get("number_of_results", 0)
    facets = data1.get("facets", {})
    catalogs1 = data1.get("catalogs", [])
    per_page = max(len(catalogs1), 10)
    total_pages = max(1, math.ceil(total_results / per_page))

    # Cap total pages to 20 for rate limiting safety
    total_pages = min(total_pages, 20)

    logger.info(f"[IMCDS] Total products: {total_results}, Pages to scrape: {total_pages}")

    def parse_catalog(cat: dict) -> dict | None:
        price = int(cat.get("final_price", {}).get("value", 0))
        if price <= 0:
            return None
        return {
            "catalogue_id": str(cat.get("id", "")),
            "price": price,
            "name": cat.get("title", ""),
            "brand": cat.get("brand", ""),
            "seller_id": seller_key(cat.get("seller", {})),
            "seller_name": cat.get("seller", {}).get("name", ""),
            "oem_id": str(cat.get("oem_id", "")),
            "productUrl": self._build_product_url(cat),
            "specs": self._extract_inline_specs(cat),
        }

    def parse_catalogs(data: dict) -> list:
        return [p for cat in data.get("catalogs", []) if (p := parse_catalog(cat))]

    all_products = parse_catalogs(data1)
    page1_prices = [p["price"] for p in all_products]

    # Fetch subsequent pages in parallel
    def fetch_page(page: int) -> list:
        purl = f"{base_url}?page={page}&format=json{extra_qs}"
        try:
            t = self._fetch(purl, retries=2).strip()
            if not t.startswith("{"):
                logger.warning(f"[IMCDS] Page {page} response is not JSON: {t[:200]}")
                return []
            return parse_catalogs(json.loads(t))
        except Exception as e:
            logger.warning(f"[IMCDS] Failed to fetch page {page}: {e}")
            return []

    if total_pages > 1 and not (page1_prices and min(page1_prices) > target_price * 1.5):
        pages_to_fetch = list(range(2, total_pages + 1))
        # Keep concurrency low to protect session from WAF block
        with ThreadPoolExecutor(max_workers=min(6, len(pages_to_fetch))) as executor:
            future_to_page = {executor.submit(fetch_page, p): p for p in pages_to_fetch}
            for future in as_completed(future_to_page):
                api_calls[0] += 1
                page = future_to_page[future]
                try:
                    all_products.extend(future.result())
                except Exception as e:
                    logger.error(f"[IMCDS] Error on page {page}: {e}")

    def dedupe_and_sort(raw_products: list) -> list:
        seen = {}
        for p in raw_products:
            cid = p["catalogue_id"]
            if cid not in seen or p["price"] < seen[cid]["price"]:
                seen[cid] = p
        return sorted(seen.values(), key=lambda p: p["price"])

    products = dedupe_and_sort(all_products)

    # If very few (or zero) sampled products are priced above target_price,
    # the ascending-sorted page cap left us blind to the part of the market
    # we actually care about -- common for a large category flooded with
    # cheap listings, where 20 pages * ~12/page (GeM's real page size) can be
    # entirely consumed by products well below the target price, leaving
    # almost no genuine non-blocker data for the search to work with.
    # Supplement with a few price-descending pages so there's a real sample
    # of higher-priced products to build a genuine win or an honest
    # achievable-ceiling estimate from.
    MIN_NON_BLOCKERS_WANTED = 10
    SUPPLEMENT_PAGES = 3
    non_blocker_count = sum(1 for p in products if p["price"] > target_price)
    if non_blocker_count < MIN_NON_BLOCKERS_WANTED and total_results > len(products):
        logger.info(
            f"[IMCDS] Only {non_blocker_count} products above target price in the "
            f"ascending sample -- fetching {SUPPLEMENT_PAGES} price-descending "
            "pages to fill in the high end."
        )
        desc_qs = extra_qs.replace("sort_type=price_in_asc", "sort_type=price_in_desc")
        for page in range(1, SUPPLEMENT_PAGES + 1):
            purl = f"{base_url}?page={page}&format=json{desc_qs}"
            try:
                t = self._fetch(purl, retries=2).strip()
                api_calls[0] += 1
                if not t.startswith("{"):
                    continue
                all_products.extend(parse_catalogs(json.loads(t)))
            except Exception as e:
                logger.warning(f"[IMCDS] Failed to fetch descending page {page}: {e}")

        products = dedupe_and_sort(all_products)
        logger.info(
            f"[IMCDS] After descending supplement: "
            f"{sum(1 for p in products if p['price'] > target_price)} products above target price."
        )

    # ── STEP 2: ENRICH ONLY RELEVANT PRODUCTS ──
    # Extract facet definitions from page 1 to get name_to_code mapping
    facet_defs = self._extract_facet_defs(facets)
    name_to_code = {fd["filterName"]: fd["filterKey"] for fd in facet_defs}

    # In-memory mapping of inline specs for all scraped products. Spec names
    # repeat on every product, so each distinct name is resolved once.
    resolve_name = make_name_resolver(name_to_code, match=self._names_match)
    for p in products:
        matched_specs = {}
        for spec_name, spec_value in (p.get("specs") or {}).items():
            if not spec_value or len(spec_value) > 150:
                continue
            facet_name = resolve_name(spec_name)
            key = name_to_code[facet_name] if facet_name else self._to_key(spec_name)
            matched_specs[key] = spec_value
        p["specs"] = matched_specs

    # Filter relevant products (cap blockers to 30 to stay within rate limits)
    blockers = [p for p in products if p["price"] <= target_price]
    non_blockers = [p for p in products if p["price"] > target_price]
    relevant_products = blockers[:30] + non_blockers[:10]

    # Optimize PDP page visits: only fetch PDP specs for relevant products missing golden keys
    golden_keys = {fd["filterKey"] for fd in facet_defs if fd.get("isGolden")}
    to_enrich = [p for p in relevant_products if golden_keys - set(p["specs"].keys())]

    logger.info(f"[IMCDS] Relevant products count: {len(relevant_products)}. Fetching PDP specs for {len(to_enrich)} products missing golden keys (max 10 parallel).")

    # Enrich in parallel
    if to_enrich:
        enrich_failures = 0
        with ThreadPoolExecutor(max_workers=min(10, len(to_enrich))) as executor:
            futures = [executor.submit(self._enrich_single_product, p, name_to_code) for p in to_enrich]
            for future in as_completed(futures):
                api_calls[0] += 1
                try:
                    future.result()  # _enrich_single_product modifies product in place
                except Exception as e:
                    enrich_failures += 1
                    logger.warning(f"[IMCDS] PDP enrichment task raised unexpectedly: {e}")
        if enrich_failures:
            logger.warning(
                f"[IMCDS] {enrich_failures}/{len(to_enrich)} PDP enrichment tasks raised an "
                "unexpected exception -- populated_ratio pruning below may be based on "
                "incomplete data."
            )

    # ── STEP 3: BFS SET-COVER SEARCH ──
    excluded = set(excluded_filter_keys or [])
    excluded.add("mse_applicable")

    golden_list = []
    for f in golden_filters:
        if f.get("isGolden") and f["filterKey"] not in excluded:
            # Skip filter keys where < 30% of the *enrichment-eligible* products have
            # that spec populated (unreliable data). PDP enrichment only ever runs
            # against relevant_products (the capped blockers/non-blockers pool), never
            # the full bulk-scraped category, so the ratio must use that same
            # denominator -- comparing against `products` would make the gate
            # unpassable for any category bigger than ~130 products.
            key = f["filterKey"]
            populated_count = sum(1 for p in relevant_products if p.get("specs", {}).get(key))
            populated_ratio = populated_count / len(relevant_products) if relevant_products else 0
            if populated_ratio < 0.3:
                logger.info(f"[BFS Prune] Skipping filter {f.get('filterName')} ({key}) because only {populated_ratio:.0%} of enriched products have it populated.")
                continue

            # Composite values on an "and" facet are explored one component at
            # a time -- the whole joined string never matches GeM's index.
            values = []
            for v in f.get("values", []):
                for qv in query_values_for(v, f.get("type", "")):
                    if qv not in values:
                        values.append(qv)

            golden_list.append({
                "filterKey": f["filterKey"],
                "filterName": f["filterName"],
                "values": _sort_spec_values(values),
            })

    # Pre-apply mandatory filters
    start_filters = {}
    for mf in mandatory_filters or []:
        k = mf.get("filterKey")
        v = mf.get("value")
        if k and v:
            start_filters[k] = v

    # Compare spec values the same way BFS expansion picks them: trimmed and
    # case-insensitive. An exact comparison here disagreed with expansion --
    # a product listing "MESH" was dropped under the filter value "Mesh",
    # counting a real competitor as eliminated.
    def norm_value(v):
        return str(v).strip().lower()

    def normalize_active(active_dict):
        return {k: norm_value(v) for k, v in active_dict.items()}

    # "MultiselectAnd" facets store each component of a composite value
    # separately, and GeM only matches components, so a product's spec is held
    # as the set of its components for those keys and as a single value for
    # the rest.
    facet_types = {fd["filterKey"]: fd.get("type", "") for fd in facet_defs}

    def spec_components(key, value):
        if is_multi_value(value, facet_types.get(key, "")):
            return frozenset(norm_value(c) for c in split_composite_value(value))
        return frozenset([norm_value(value)])

    for p in products:
        p["norm_specs"] = {k: spec_components(k, v) for k, v in p["specs"].items()}

    # Filter products matching active conditions (both sides normalized)
    def matches_filters(norm_specs, active_norm):
        for k, v in active_norm.items():
            val = norm_specs.get(k)
            if val is None:
                # Spec data is missing - treat as matching (conservative)
                continue
            if v not in val:
                return False
        return True

    start_norm = normalize_active(start_filters)
    start_products = [p for p in products if matches_filters(p["norm_specs"], start_norm)]

    # Establish original min price and seller count
    market_min_price = min((p["price"] for p in start_products), default=None)
    orig_sellers = len({p["seller_id"] for p in start_products})
    min_sellers_limit = min(3, orig_sellers)

    # Helper to evaluate filter state locally
    def evaluate_state(active_dict):
        active_norm = normalize_active(active_dict)
        matched = [p for p in start_products if matches_filters(p["norm_specs"], active_norm)]
        prices = [p["price"] for p in matched]
        return {
            "products": matched,
            "min_price": min(prices) if prices else None,
            "blockers": [p for p in matched if p["price"] <= target_price],
            "sellers": len({p["seller_id"] for p in matched}),
            "total": len(matched),
        }

    # BFS Queue: stores (active_filters_dict, path_steps_list)
    # where path_steps_list is a list of tuples (gf_dict, value)
    queue = collections.deque([({}, [])])
    visited = {frozenset()}

    local_winning_paths = []
    local_partial_paths = []

    max_states = 5000
    states_checked = 0

    while queue and states_checked < max_states:
        curr_active, path_steps = queue.popleft()
        states_checked += 1

        eval_res = evaluate_state(curr_active)

        if not eval_res["blockers"]:
            local_winning_paths.append((curr_active, path_steps, eval_res))
            if len(local_winning_paths) >= 30:
                break
            continue

        local_partial_paths.append((curr_active, path_steps, eval_res))

        # Max search depth
        if len(path_steps) >= 4:
            continue

        # Expand
        for gf in golden_list:
            key = gf["filterKey"]
            if key in curr_active:
                continue

            # Restrict expansion to only values present in the matching products
            allowed_values = {v for p in eval_res["products"] for v in p["norm_specs"].get(key, ())}

            for val in gf.get("values", []):
                if norm_value(val) not in allowed_values:
                    continue

                next_active = dict(curr_active)
                next_active[key] = val

                sig = frozenset(next_active.items())
                if sig not in visited:
                    visited.add(sig)
                    queue.append((next_active, path_steps + [(gf, val)]))

    # ── STEP 4: PARALLEL LIVE PATH VERIFICATION ──
    # Sort winning paths by quality before capping to 20 -- otherwise which
    # candidates get (expensive, rate-limited) live verification depends on
    # arbitrary BFS discovery order, and a strictly better win can be
    # dropped before ever being checked.
    def sort_local_winning_key(item):
        active_dict, steps_list, eval_res = item
        is_untapped = eval_res["total"] == 0
        gap = (eval_res["min_price"] - target_price) if eval_res["min_price"] else 0
        return (
            0 if not is_untapped else 1,  # a real (non-untapped) win is preferred
            len(steps_list),              # shorter chain is better
            -gap,                          # larger price gap is better
        )
    local_winning_paths.sort(key=sort_local_winning_key)
    candidates = local_winning_paths[:20]
    if len(candidates) < 15:
        # Filter out empty path and sort partial paths so that those eliminating the most blockers (in-memory) are preferred,
        # then higher min price, then fewer products, then shorter chains.
        filtered_partials = [item for item in local_partial_paths if item[1]]

        def sort_local_partial_key(item):
            active_dict, steps_list, eval_res = item
            return (
                len(eval_res["blockers"]),    # Fewer blockers left is better
                -(eval_res["min_price"] or 0),  # Higher min price is better
                eval_res["total"],            # Fewer products is better
                len(steps_list),              # Shorter chain is better
            )
        filtered_partials.sort(key=sort_local_partial_key)

        # Add the best partial paths up to a cap of 15 candidates
        needed = 15 - len(candidates)
        top_by_blockers = filtered_partials[:needed]

        # "Fewest blockers remaining" is the right heuristic for suggesting
        # the next step of an elimination chain, but it can silently exclude
        # a state with a genuinely higher achievable price just because it
        # happens to have more blockers left -- understating
        # bestAchievablePrice below what the search actually found. Make
        # sure the single highest-price partial state always gets a chance
        # at live verification too, even if its blocker count would
        # otherwise have ranked it out of the top `needed`.
        best_by_price = max(
            filtered_partials,
            key=lambda item: item[2]["min_price"] or 0,
            default=None,
        )

        candidates += top_by_blockers
        if best_by_price is not None and best_by_price not in top_by_blockers:
            candidates.append(best_by_price)

    verified_paths = []

    def verify_candidate(item):
        active_dict, steps_list, local_eval = item
        # Build query parameters. Mandatory filters must be included here too --
        # they were already folded into start_products for in-memory evaluation,
        # but the live GeM query needs them explicitly or it verifies against
        # the unfiltered category while activeFilters claims they were applied.
        params = dict(base_extra) if base_extra else {}
        params.update(start_filters)
        params.update(active_dict)
        # Live scrape page 1 & 2
        live_res = self._chain_scrape(category_url, params, location)
        return active_dict, steps_list, local_eval, live_res

    logger.info(f"[IMCDS] Verifying {len(candidates)} candidate paths live...")

    # A burst of near-simultaneous filtered-price requests reliably trips GeM's
    # WAF (confirmed via logged "Request Rejected" responses -- every candidate
    # in a batch gets blocked, not genuinely answered). Keep true concurrency
    # low and stagger submissions so requests land spread out in time instead
    # of landing on GeM within the same second.
    VERIFY_MAX_WORKERS = 2
    VERIFY_STAGGER_SECONDS = 0.6

    if candidates:
        with ThreadPoolExecutor(max_workers=min(VERIFY_MAX_WORKERS, len(candidates))) as executor:
            futures = []
            for c in candidates:
                futures.append(executor.submit(verify_candidate, c))
                time.sleep(VERIFY_STAGGER_SECONDS)
            for future in as_completed(futures):
                api_calls[0] += 1
                try:
                    active_dict, steps_list, local_eval, live_res = future.result()
                    if not live_res.get("error"):
                        verified_paths.append((active_dict, steps_list, local_eval, live_res))
                except Exception as e:
                    logger.error(f"[IMCDS] Verification failed: {e}")

    # Competitor insights helper
    def format_competitor(p):
        if not p:
            return None
        return {
            "id": p.get("catalogue_id") or p.get("id", ""),
            "name": p.get("name", ""),
            "price": p.get("price", 0),
            "searchPrice": p.get("searchPrice", p.get("price", 0)),
            "pricePageChecked": bool(p.get("pricePageChecked")),
            "seller": p.get("seller_name") or p.get("seller", ""),
            "seller_id": p.get("seller_id", ""),
            "brand": p.get("brand", ""),
            "url": p.get("product_url") or p.get("url", ""),
        }

    def extract_competitor_insights(matched_products, t_price):
        if not matched_products:
            return {"message": "no L2 and L3 on this path", "l2": None, "l3": None}
        valid_products = sorted((p for p in matched_products if p["price"] > t_price), key=lambda x: x["price"])
        if not valid_products:
            return {"message": "no L2 and L3 on this path", "l2": None, "l3": None}

        l2 = format_competitor(valid_products[0])
        l2_brand = l2.get("brand", "").strip().lower()

        if len(valid_products) == 1:
            return {"message": "no L2 and L3 on this path", "l2": l2, "l3": None}

        l3 = None
        for p in valid_products[1:]:
            p_brand = p.get("brand", "").strip().lower()
            if p_brand != l2_brand and p_brand != "":
                l3 = format_competitor(p)
                break

        if l3:
            return {
                "message": f"L2 and L3 found with their product names: {l2['name']} and {l3['name']}",
                "l2": l2,
                "l3": l3
            }
        return {
            "message": "found L2 and L3 but of same brands",
            "l2": l2,
            "l3": format_competitor(valid_products[1])
        }

    def build_iterations(steps_list, can_win=False):
        """
        Per-step breakdown of a filter path, measured entirely against the
        scanned sample so the columns stay comparable from row to row. The
        live-verified numbers for the finished path live on the path itself
        (nicheMinPrice / totalProducts / sellerCount). Only `can_win` paths
        may label a step L1_WIN.
        """
        iterations = []
        curr_act = {}
        prev_min = market_min_price
        for idx, (gf, val) in enumerate(steps_list):
            curr_act[gf["filterKey"]] = val

            # Every step is measured against the same scanned sample. Mixing in
            # the live totals on the last step only (as this used to do) made a
            # narrowing step look like it GREW the niche -- 240 sampled products
            # followed by 2,527 live ones -- because the denominator changed
            # under the reader. The live-verified figures for the finished path
            # are reported separately, on the path itself.
            step_eval = evaluate_state(curr_act)
            new_min = step_eval["min_price"]
            new_total = step_eval["total"]
            sellers_count = step_eval["sellers"]

            if new_min is not None and prev_min is not None and new_min <= prev_min:
                result = "LATERAL"
            elif not can_win or (new_min is not None and new_min <= target_price):
                result = "ELIMINATED"
            else:
                result = "L1_WIN"

            iterations.append({
                "iteration": idx + 1,
                "prevMinPrice": prev_min,
                "filterApplied": {
                    "filterKey": gf["filterKey"],
                    "filterName": gf["filterName"],
                    "value": val,
                },
                "result": result,
                "newMinPrice": new_min,
                "newTotal": new_total,
                "sellerCount": sellers_count,
                "scope": "sample",
            })
            prev_min = new_min
        return iterations

    def format_verified_path(active_dict, steps_list, live_res, status, is_untapped):
        return {
            "iterations": build_iterations(steps_list, can_win=(status == "WIN")),
            "activeFilters": {**start_filters, **active_dict},
            "status": status,
            "isUntapped": is_untapped,
            "nicheMinPrice": live_res["min_price"],
            "totalProducts": live_res["total"],
            "sellerCount": live_res["seller_count"],
            "priceCheck": live_res.get("priceCheck"),
            "chainLength": len(active_dict) + len(start_filters),
            "competitorInsights": extract_competitor_insights(live_res["products"], target_price),
        }

    # ── STEP 4b: PRICE THE DECIDING LISTINGS FROM THEIR OWN PAGES ──
    # GeM's search index lags behind price cuts. A listing cut from 6,990 to
    # 2,500 can sit at 6,990 in search while its page already charges 2,500,
    # and this search is drawn to exactly those listings: a stale high price
    # looks like a rival the seller can sit under. Every verdict below is
    # therefore made on product-page prices for the cheapest listings of each
    # path, not on the index.
    if verified_paths:
        from crawler import GeMCrawler
        wanted = []
        for _, _, _, live_res in verified_paths:
            cheapest = sorted(live_res.get("products") or [], key=lambda p: p["price"])
            wanted.extend(p["url"] for p in cheapest[:LIVE_PRICE_DEPTH] if p.get("url"))
        page_prices = GeMCrawler().live_prices(wanted)
        api_calls[0] += len(page_prices)
        stale = sum(1 for _, _, _, lr in verified_paths for p in lr.get("products") or []
                    if page_prices.get(p.get("url")) not in (None, p["price"]))
        logger.info(f"[IMCDS] Page-priced {len(page_prices)} listings; "
                    f"{sum(v is not None for v in page_prices.values())} readable, "
                    f"{stale} path entries were stale in search")
        for _, _, _, live_res in verified_paths:
            _reprice_from_pages(live_res, page_prices)

        # A WIN is the claim a seller acts on, so it has to hold for every
        # listing we fetched, not just the cheapest few. Page-check the rest
        # of any path still standing as a win.
        still_winning = [lr for _, _, _, lr in verified_paths
                         if lr.get("min_price") is not None and lr["min_price"] > target_price]
        rest = [p["url"] for lr in still_winning for p in lr.get("products") or []
                if p.get("url") and p["url"] not in page_prices]
        if rest:
            more = GeMCrawler().live_prices(rest)
            api_calls[0] += len(more)
            page_prices.update(more)
            for lr in still_winning:
                _reprice_from_pages(lr, page_prices)
            logger.info(f"[IMCDS] Page-priced {len(more)} more listings on {len(still_winning)} winning paths")

    # ── STEP 5: RECONSTRUCT AND SORT VERIFIED RESULTS ──
    winning_candidates = []
    partial_candidates = []
    unconfirmed_candidates = []

    for active_dict, steps_list, local_eval, live_res in verified_paths:
        total = live_res["total"]
        min_price = live_res["min_price"]
        sellers = live_res["seller_count"]

        is_untapped = (total == 0)

        # Mismatch guard: if the live API returns 0 results, but our in-memory database has matching
        # products, the live query for this specific combo isn't corroborating our local data -- most
        # often because GeM's search index doesn't accept the literal spec text we're sending for some
        # facet types (confirmed live: multi-word text facets like "Seat upholstery material" or
        # "Ports" return 0 live even with correct encoding, while local data -- scraped from real
        # product pages -- shows genuine matches). We can't tell "real GeM 0" apart from "GeM doesn't
        # recognize this filter value" per-facet, so rather than silently discarding a strong local
        # candidate as fake, surface it as unconfirmed instead of throwing it away.
        # GeM ignored the filter parameters and answered for the whole
        # category, so this tells us nothing about the niche.
        if live_res.get("ignored"):
            logger.warning(f"[IMCDS] Live check for path {steps_list} was ignored by GeM. Marking unconfirmed.")
            unconfirmed_candidates.append((active_dict, steps_list, local_eval))
            continue

        if is_untapped and local_eval["total"] > 0:
            logger.warning(f"[IMCDS] Mismatch detected: live total=0 but local total={local_eval['total']} for path {steps_list}. Marking unconfirmed instead of discarding.")
            unconfirmed_candidates.append((active_dict, steps_list, local_eval))
            continue

        is_l1_win = (total > 0 and (min_price is None or min_price > target_price) and sellers >= min_sellers_limit)

        if is_untapped or is_l1_win:
            winning_candidates.append((active_dict, steps_list, local_eval, live_res, is_untapped))
        else:
            partial_candidates.append((active_dict, steps_list, local_eval, live_res))

    # Sort verified wins: real L1 win > untapped, shorter path, higher price gap
    def sort_winning_key(item):
        active_dict, steps_list, local_eval, live_res, is_untapped = item
        min_price = live_res["min_price"]
        gap = (min_price - target_price) if (min_price and not is_untapped) else 0
        return (
            0 if not is_untapped else 1,   # Real L1 win preferred
            len(steps_list),               # Shorter path preferred
            -gap                           # Larger gap preferred
        )

    winning_candidates.sort(key=sort_winning_key)

    formatted_winning = [
        format_verified_path(active_dict, steps_list, live_res, "WIN", is_untapped)
        for active_dict, steps_list, local_eval, live_res, is_untapped in winning_candidates[:20]
    ]

    # If no winning paths, format the verified partial paths
    if not formatted_winning and partial_candidates:
        partial_candidates.sort(key=lambda item: (
            -(item[3]["min_price"] or 0),  # Higher min price preferred
            item[3]["total"],              # Fewer remaining products preferred
            len(item[1]),                  # Shorter path preferred
        ))
        formatted_winning = [
            format_verified_path(active_dict, steps_list, live_res, "PARTIAL", False)
            for active_dict, steps_list, local_eval, live_res in partial_candidates[:5]
        ]

    # Format unconfirmed candidates (mismatch-guarded: strong locally, live query
    # didn't corroborate). Always surfaced alongside whatever real result we have --
    # even next to a confirmed win, these are extra leads worth a manual check.
    unconfirmed_candidates.sort(key=lambda item: (
        -(item[2]["min_price"] or 0),  # Higher local price preferred
        item[2]["total"],              # Fewer remaining products preferred
        len(item[1]),                  # Shorter path preferred
    ))
    formatted_unconfirmed = [
        {
            "iterations": build_iterations(steps_list),
            "activeFilters": {**start_filters, **active_dict},
            "status": "UNCONFIRMED",
            "nicheMinPrice": local_eval["min_price"],
            "totalProducts": local_eval["total"],
            "sellerCount": local_eval.get("sellers", 0),
            "chainLength": len(active_dict) + len(start_filters),
        }
        for active_dict, steps_list, local_eval in unconfirmed_candidates[:5]
    ]

    status = "WIN" if any(p["status"] == "WIN" for p in formatted_winning) else "PARTIAL"
    best_achievable = max((p.get("nicheMinPrice") or 0 for p in formatted_winning), default=0)

    return {
        "winningPaths": formatted_winning,
        "totalPaths": len(formatted_winning),
        "unconfirmedPaths": formatted_unconfirmed,
        "totalApiCalls": api_calls[0],
        "status": status,
        "goldenFilterCount": len(golden_list),
        "elapsed": round(time.time() - t_start, 1),
        "bestAchievablePrice": best_achievable if best_achievable > 0 else None,
        "marketMinPrice": market_min_price,
        "targetPrice": target_price,
        "sampleSize": len(start_products),
    }
