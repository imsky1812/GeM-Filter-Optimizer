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

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import time
import logging
from urllib.parse import urlencode
import requests

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


def _get_facet_values_for_key(self, facets: dict, filter_key: str, filter_name: str = "") -> list:
    """Legacy stub. Kept for import compatibility."""
    return []


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
    import math
    import collections
    
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
        extra_qs += "&localized_search=" + requests.utils.quote(location)

    # Force price ascending sort so we get the cheapest products on early pages
    extra_qs += "&sort_type=price_in_asc"

    # Fetch Page 1 to get total results count and facets
    page1_url = f"{base_url}?page=1&format=json{extra_qs}"
    logger.info(f"[IMCDS] Fetching Page 1: {page1_url}")
    
    try:
        text = self._fetch(page1_url).strip()
        api_calls[0] += 1
        if not text.startswith("{"):
            logger.error(f"[IMCDS] Page 1 response is not JSON: {text[:200]}")
            return {
                "winningPaths": [],
                "totalPaths": 0,
                "totalApiCalls": api_calls[0],
                "status": "STUCK",
                "goldenFilterCount": len(golden_filters),
                "elapsed": round(time.time() - t_start, 1),
                "bestAchievablePrice": None,
                "marketMinPrice": None,
                "targetPrice": target_price,
            }
        data1 = json.loads(text)
    except Exception as e:
        logger.error(f"[IMCDS] Failed to fetch Page 1: {e}")
        return {
            "winningPaths": [],
            "totalPaths": 0,
            "totalApiCalls": api_calls[0],
            "status": "STUCK",
            "goldenFilterCount": len(golden_filters),
            "elapsed": round(time.time() - t_start, 1),
            "bestAchievablePrice": None,
            "marketMinPrice": None,
            "targetPrice": target_price,
        }

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
            "seller_id": str(cat.get("seller", {}).get("id", "")),
            "seller_name": cat.get("seller", {}).get("name", ""),
            "oem_id": str(cat.get("oem_id", "")),
            "productUrl": self._build_product_url(cat),
            "specs": self._extract_inline_specs(cat),
        }

    all_products = []
    for cat in catalogs1:
        p = parse_catalog(cat)
        if p:
            all_products.append(p)

    # Check first page prices
    page1_prices = [p["price"] for p in all_products]
    
    # Fetch subsequent pages in parallel
    def fetch_page(page: int) -> list:
        purl = f"{base_url}?page={page}&format=json{extra_qs}"
        try:
            t = self._fetch(purl, retries=2).strip()
            if not t.startswith("{"):
                return []
            d = json.loads(t)
            page_products = []
            for cat in d.get("catalogs", []):
                p = parse_catalog(cat)
                if p:
                    page_products.append(p)
            return page_products
        except Exception:
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
                    res = future.result()
                    if res:
                        all_products.extend(res)
                except Exception as e:
                    logger.error(f"[IMCDS] Error on page {page}: {e}")
    # Deduplicate and sort ascending by price
    seen = {}
    for p in all_products:
        cid = p["catalogue_id"]
        if cid not in seen or p["price"] < seen[cid]["price"]:
            seen[cid] = p
    products = sorted(seen.values(), key=lambda p: p["price"])
    
    # ── STEP 2: ENRICH ONLY RELEVANT PRODUCTS ──
    # Extract facet definitions from page 1 to get name_to_code mapping
    facet_defs = self._extract_facet_defs(facets)
    name_to_code = {fd["filterName"]: fd["filterKey"] for fd in facet_defs}
    
    # In-memory mapping of inline specs for all scraped products
    for p in products:
        raw_specs = p.get("specs") or {}
        matched_specs = {}
        for spec_name, spec_value in raw_specs.items():
            if not spec_value or len(spec_value) > 150:
                continue
            matched_code = name_to_code.get(spec_name)
            if not matched_code:
                for facet_name, facet_code in name_to_code.items():
                    if self._names_match(spec_name, facet_name):
                        matched_code = facet_code
                        break
            if matched_code:
                matched_specs[matched_code] = spec_value
            else:
                matched_specs[self._to_key(spec_name)] = spec_value
        p["specs"] = matched_specs

    # Filter relevant products (cap blockers to 30 to stay within rate limits)
    blockers = [p for p in products if p["price"] <= target_price]
    non_blockers = [p for p in products if p["price"] > target_price]
    relevant_products = blockers[:30] + non_blockers[:10]
    
    # Optimize PDP page visits: only fetch PDP specs for relevant products missing golden keys
    golden_keys = {fd["filterKey"] for fd in facet_defs if fd.get("isGolden")}
    to_enrich = []
    for p in relevant_products:
        missing_golden = golden_keys - set(p["specs"].keys())
        if missing_golden:
            to_enrich.append(p)
            
    logger.info(f"[IMCDS] Relevant products count: {len(relevant_products)}. Fetching PDP specs for {len(to_enrich)} products missing golden keys (max 10 parallel).")
    
    # Enrich in parallel
    if to_enrich:
        with ThreadPoolExecutor(max_workers=min(10, len(to_enrich))) as executor:
            futures = [executor.submit(self._enrich_single_product, p, name_to_code) for p in to_enrich]
            for future in as_completed(futures):
                api_calls[0] += 1
                # _enrich_single_product modifies product in place

    # ── STEP 3: BFS SET-COVER SEARCH ──
    excluded = set(excluded_filter_keys or [])
    excluded.add("mse_applicable")
    
    # Build clean golden filters list from passed golden_filters
    import re
    def sort_spec_values(values):
        def parse_value(v):
            m = re.search(r'[-+]?\d*\.\d+|\d+', str(v))
            if m:
                try:
                    return float(m.group(0))
                except ValueError:
                    pass
            return -1.0
        return sorted(values, key=lambda x: (parse_value(x), str(x)), reverse=True)

    golden_list = []
    for f in golden_filters:
        if f.get("isGolden") and f["filterKey"] not in excluded:
            # Skip filter keys where < 30% of products have that spec populated (unreliable data)
            key = f["filterKey"]
            populated_count = sum(1 for p in products if p.get("specs", {}).get(key))
            populated_ratio = populated_count / len(products) if products else 0
            if populated_ratio < 0.3:
                logger.info(f"[BFS Prune] Skipping filter {f.get('filterName')} ({key}) because only {populated_ratio:.0%} of products have it populated.")
                continue

            sorted_vals = sort_spec_values(f.get("values", []))
            golden_list.append({
                "filterKey": f["filterKey"],
                "filterName": f["filterName"],
                "values": sorted_vals,
            })
            
    # Pre-apply mandatory filters
    start_filters = {}
    if mandatory_filters:
        for mf in mandatory_filters:
            k = mf.get("filterKey")
            v = mf.get("value")
            if k and v:
                start_filters[k] = v
                
    # Filter products matching active conditions
    def matches_filters(product_specs, active_dict):
        for k, v in active_dict.items():
            val = product_specs.get(k)
            if val is None:
                # Spec data is missing - treat as matching (conservative)
                continue
            if val != v:
                return False
        return True

    start_products = [p for p in products if matches_filters(p["specs"], start_filters)]
    
    # Establish original min price and seller count
    market_min_price = min((p["price"] for p in start_products), default=None)
    orig_sellers = len({p["seller_id"] for p in start_products})
    min_sellers_limit = min(3, orig_sellers)
    
    # Helper to evaluate filter state locally
    def evaluate_state(active_dict):
        matched = [p for p in start_products if matches_filters(p["specs"], active_dict)]
        prices = [p["price"] for p in matched]
        min_p = min(prices) if prices else None
        blockers_left = [p for p in matched if p["price"] <= target_price]
        sellers = len({p["seller_id"] for p in matched})
        return {
            "products": matched,
            "min_price": min_p,
            "blockers": blockers_left,
            "sellers": sellers,
            "total": len(matched)
        }

    # BFS Queue: stores (active_filters_dict, path_steps_list)
    # where path_steps_list is a list of tuples (gf_dict, value)
    queue = collections.deque([({}, [])])
    visited = set()
    visited.add(frozenset())
    
    local_winning_paths = []
    local_partial_paths = []
    
    max_states = 5000
    states_checked = 0
    
    while queue and states_checked < max_states:
        curr_active, path_steps = queue.popleft()
        states_checked += 1
        
        eval_res = evaluate_state(curr_active)
        is_blockers_eliminated = (len(eval_res["blockers"]) == 0)
        
        if is_blockers_eliminated:
            local_winning_paths.append((curr_active, path_steps, eval_res))
            if len(local_winning_paths) >= 30:
                break
            continue
            
        local_partial_paths.append((curr_active, path_steps, eval_res))
        
        # Max search depth
        if len(path_steps) >= 4:
            continue
            
        # Expand
        applied_keys = set(curr_active.keys())
        for gf in golden_list:
            key = gf["filterKey"]
            if key in applied_keys:
                continue
                
            # Restrict expansion to only values present in the matching products
            allowed_values = {str(p["specs"].get(key)).strip().lower() for p in eval_res["products"] if p["specs"].get(key)}
            
            for val in gf.get("values", []):
                if str(val).strip().lower() not in allowed_values:
                    continue
                    
                next_active = dict(curr_active)
                next_active[key] = val
                
                sig = frozenset(next_active.items())
                if sig not in visited:
                    visited.add(sig)
                    queue.append((next_active, path_steps + [(gf, val)]))


    # ── STEP 4: PARALLEL LIVE PATH VERIFICATION ──
    candidates = local_winning_paths[:20]
    if len(candidates) < 15:
        # Filter out empty path and sort partial paths so that those eliminating the most blockers (in-memory) are preferred,
        # then higher min price, then fewer products, then shorter chains.
        filtered_partials = [item for item in local_partial_paths if item[1]]
        
        def sort_local_partial_key(item):
            active_dict, steps_list, eval_res = item
            blockers_count = len(eval_res["blockers"])
            min_price = eval_res["min_price"] or 0
            total = eval_res["total"]
            return (
                blockers_count,    # Fewer blockers left is better
                -min_price,        # Higher min price is better
                total,             # Fewer products is better
                len(steps_list)    # Shorter chain is better
            )
        filtered_partials.sort(key=sort_local_partial_key)
        
        # Add the best partial paths up to a cap of 15 candidates
        needed = 15 - len(candidates)
        candidates += filtered_partials[:needed]
        
    verified_paths = []
    
    def verify_candidate(item):
        active_dict, steps_list, local_eval = item
        # Build query parameters
        params = dict(base_extra) if base_extra else {}
        params.update(active_dict)
        # Live scrape page 1 & 2
        live_res = self._chain_scrape(category_url, params, location)
        return active_dict, steps_list, local_eval, live_res

    logger.info(f"[IMCDS] Verifying {len(candidates)} candidate paths live...")
    
    if candidates:
        with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as executor:
            futures = [executor.submit(verify_candidate, c) for c in candidates]
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
            "seller": p.get("seller_name") or p.get("seller", ""),
            "seller_id": p.get("seller_id", ""),
            "brand": p.get("brand", ""),
            "url": p.get("product_url") or p.get("url", ""),
        }

    def extract_competitor_insights(matched_products, t_price):
        if not matched_products:
            return {"message": "no L2 and L3 on this path", "l2": None, "l3": None}
        valid_products = [p for p in matched_products if p["price"] > t_price]
        valid_products.sort(key=lambda x: x["price"])
        if len(valid_products) == 0:
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
        else:
            return {
                "message": "found L2 and L3 but of same brands",
                "l2": l2,
                "l3": format_competitor(valid_products[1])
            }

    # ── STEP 5: RECONSTRUCT AND SORT VERIFIED RESULTS ──
    formatted_winning = []
    
    # Process verified candidates
    winning_candidates = []
    partial_candidates = []
    
    for active_dict, steps_list, local_eval, live_res in verified_paths:
        total = live_res["total"]
        min_price = live_res["min_price"]
        sellers = live_res["seller_count"]
        
        is_untapped = (total == 0)
        
        # Mismatch guard: if the live API returns 0 results, but our in-memory database has matching products,
        # it means the live query is broken or mismatched on the search index, so it is a fake untapped niche.
        if is_untapped and local_eval["total"] > 0:
            logger.warning(f"[IMCDS] Mismatch detected: live total=0 but local total={local_eval['total']} for path {steps_list}. Discarding fake untapped niche.")
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
    
    for active_dict, steps_list, local_eval, live_res, is_untapped in winning_candidates[:20]:
        # Build iterations list (use in-memory values for intermediate steps, live values for final step)
        iterations = []
        curr_act = {}
        prev_min = market_min_price
        for idx, (gf, val) in enumerate(steps_list):
            curr_act[gf["filterKey"]] = val
            
            # If final step, use live verified values
            if idx == len(steps_list) - 1:
                new_min = live_res["min_price"]
                new_total = live_res["total"]
                sellers_count = live_res["seller_count"]
            else:
                # Use in-memory estimate
                step_eval = evaluate_state(curr_act)
                new_min = step_eval["min_price"]
                new_total = step_eval["total"]
                sellers_count = step_eval["sellers"]
                
            step = {
                "iteration": idx + 1,
                "prevMinPrice": prev_min,
                "filterApplied": {
                    "filterKey": gf["filterKey"],
                    "filterName": gf["filterName"],
                    "value": val,
                },
                "result": "LATERAL" if (new_min is not None and prev_min is not None and new_min <= prev_min) else (
                    "ELIMINATED" if (new_min is not None and new_min <= target_price) else "L1_WIN"
                ),
                "newMinPrice": new_min,
                "newTotal": new_total,
                "sellerCount": sellers_count,
            }
            iterations.append(step)
            prev_min = new_min
            
        formatted_winning.append({
            "iterations": iterations,
            "activeFilters": {**start_filters, **active_dict},
            "status": "WIN",
            "isUntapped": is_untapped,
            "nicheMinPrice": live_res["min_price"],
            "totalProducts": live_res["total"],
            "sellerCount": live_res["seller_count"],
            "chainLength": len(active_dict) + len(start_filters),
            "competitorInsights": extract_competitor_insights(live_res["products"], target_price)
        })

    # If no winning paths, format the verified partial paths
    if not formatted_winning and partial_candidates:
        def sort_partial_key(item):
            active_dict, steps_list, local_eval, live_res = item
            min_price = live_res["min_price"] or 0
            total = live_res["total"]
            return (
                -min_price,        # Higher min price preferred
                total,             # Fewer remaining products preferred
                len(steps_list)    # Shorter path preferred
            )
            
        partial_candidates.sort(key=sort_partial_key)
        
        for active_dict, steps_list, local_eval, live_res in partial_candidates[:5]:
            iterations = []
            curr_act = {}
            prev_min = market_min_price
            for idx, (gf, val) in enumerate(steps_list):
                curr_act[gf["filterKey"]] = val
                
                if idx == len(steps_list) - 1:
                    new_min = live_res["min_price"]
                    new_total = live_res["total"]
                    sellers_count = live_res["seller_count"]
                else:
                    step_eval = evaluate_state(curr_act)
                    new_min = step_eval["min_price"]
                    new_total = step_eval["total"]
                    sellers_count = step_eval["sellers"]
                    
                step = {
                    "iteration": idx + 1,
                    "prevMinPrice": prev_min,
                    "filterApplied": {
                        "filterKey": gf["filterKey"],
                        "filterName": gf["filterName"],
                        "value": val,
                    },
                    "result": "LATERAL" if (new_min is not None and prev_min is not None and new_min <= prev_min) else "ELIMINATED",
                    "newMinPrice": new_min,
                    "newTotal": new_total,
                    "sellerCount": sellers_count,
                }
                iterations.append(step)
                prev_min = new_min
                
            formatted_winning.append({
                "iterations": iterations,
                "activeFilters": {**start_filters, **active_dict},
                "status": "PARTIAL",
                "isUntapped": False,
                "nicheMinPrice": live_res["min_price"],
                "totalProducts": live_res["total"],
                "sellerCount": live_res["seller_count"],
                "chainLength": len(active_dict) + len(start_filters),
                "competitorInsights": extract_competitor_insights(live_res["products"], target_price)
            })

    elapsed = time.time() - t_start
    status = "WIN" if any(p["status"] == "WIN" for p in formatted_winning) else "PARTIAL"
    
    # Calculate best achievable price
    best_achievable = 0
    for p in formatted_winning:
        mp = p.get("nicheMinPrice") or 0
        if mp > best_achievable:
            best_achievable = mp
            
    return {
        "winningPaths": formatted_winning,
        "totalPaths": len(formatted_winning),
        "totalApiCalls": api_calls[0],
        "status": status,
        "goldenFilterCount": len(golden_list),
        "elapsed": round(elapsed, 1),
        "bestAchievablePrice": best_achievable if best_achievable > 0 else None,
        "marketMinPrice": market_min_price,
        "targetPrice": target_price,
    }
