"""
chain_hunt.py — Sequential L1 Chain Hunt

The CORRECT algorithm for progressive blocker elimination:
  1. Scrape category with current filters → find MIN price
  2. If min_price > target_price → WIN (you are L1)
  3. If no products → WIN (untapped niche)
  4. Try each unused golden filter value:
     - Apply filter ON TOP of existing filters
     - Re-scrape → get NEW min price
     - Accept ONLY if new_min > old_min (strict progress)
  5. Commit the best filter (highest min price gain) and repeat from step 1

Key insight: we don't check if a "specific product" disappeared.
We check if the MINIMUM PRICE went UP. That's the only thing that matters.
"""

import json
import time
import logging
from urllib.parse import urlencode
import requests

logger = logging.getLogger("chain-hunt")


# ── Helper: scrape a category with filters applied ────────────────────────────

def _chain_scrape(self, url: str, extra_params: dict, location: str = "") -> dict:
    """
    Scrape page 1 of the category with filters applied.
    Returns {min_price, products, facets, total, seller_count, error}
    """
    base_url = url.split("#")[0].split("?")[0]

    extra_qs = ""
    if extra_params:
        filtered = {k: v for k, v in extra_params.items()
                    if k.lower() not in ("page", "format")}
        if filtered:
            extra_qs = "&" + urlencode(filtered)
    if location and location.lower() not in ("", "all india", "all"):
        extra_qs += "&localized_search=" + requests.utils.quote(location)

    page1_url = f"{base_url}?page=1&format=json{extra_qs}"
    data1 = None
    for attempt in range(3):
        try:
            text = self._fetch(page1_url, retries=2).strip()
            if text.startswith("{"):
                data1 = json.loads(text)
                break
        except Exception:
            pass
        time.sleep(1.0 * (attempt + 1))

    if not data1:
        return {"min_price": None, "products": [], "facets": {},
                "total": 0, "seller_count": 0, "error": True}

    total = data1.get("number_of_results", 0)
    catalogs = data1.get("catalogs", [])
    facets = data1.get("facets", {})

    products = []
    sellers = set()
    for cat in catalogs:
        price = int(cat.get("final_price", {}).get("value", 0))
        if price <= 0:
            continue
        sid = cat.get("seller", {}).get("id", "")
        sellers.add(sid)
        products.append({
            "id": cat.get("id", ""),
            "name": cat.get("title", ""),
            "price": price,
            "seller": cat.get("seller", {}).get("name", ""),
            "seller_id": sid,
            "brand": cat.get("brand", ""),
        })

    # Also fetch page 2 for better seller diversity count
    if total > len(catalogs):
        try:
            p2url = f"{base_url}?page=2&format=json{extra_qs}"
            t2 = self._fetch(p2url, retries=1).strip()
            if t2.startswith("{"):
                d2 = json.loads(t2)
                for cat in d2.get("catalogs", []):
                    price = int(cat.get("final_price", {}).get("value", 0))
                    if price <= 0:
                        continue
                    sid = cat.get("seller", {}).get("id", "")
                    sellers.add(sid)
                    products.append({
                        "id": cat.get("id", ""),
                        "name": cat.get("title", ""),
                        "price": price,
                        "seller": cat.get("seller", {}).get("name", ""),
                        "seller_id": sid,
                        "brand": cat.get("brand", ""),
                    })
        except Exception:
            pass

    min_price = min((p["price"] for p in products), default=None)

    return {
        "min_price": min_price,
        "products": products,
        "facets": facets,
        "total": total,
        "seller_count": len(sellers),
        "error": False,
    }


# ── Helper: extract available values for a golden filter from live facets ──

def _get_facet_values_for_key(self, facets: dict, filter_key: str, filter_name: str = "") -> list:
    """
    Given raw facets from a scrape response, extract currently-available
    values for a specific golden filter key.
    """
    values = []
    for section_key in ("product specifications", "administrative"):
        section = facets.get(section_key, {})
        for facet in section.get("facet_list", []):
            if facet.get("code") == filter_key or (filter_name and facet.get("name") == filter_name):
                for key in ("facet_values", "topValues", "top_values", "values",
                            "entries", "options", "items", "terms"):
                    raw = facet.get(key, [])
                    if not raw:
                        continue
                    for v in raw:
                        if isinstance(v, dict):
                            label = (v.get("name") or v.get("value") or
                                     v.get("code") or v.get("label") or "")
                        else:
                            label = str(v)
                        label = str(label).strip()
                        if label and label.lower() not in ("true", "false", "null", ""):
                            values.append(label)
                    if values:
                        return values
    return values


# ── Main Algorithm: Sequential L1 Chain Hunt ─────────────────────────────────

def smart_l1_discovery(self, category_url: str, target_price: int,
                       golden_filters: list, location: str = "") -> dict:
    """
    Sequential chain elimination algorithm.

    Strategy: GREEDY-BEST — at each depth, try ALL unused filter values,
    pick the one that raises the minimum price THE MOST, commit to it,
    and continue until we are L1 or run out of filters.
    """
    MAX_API_CALLS = 500
    MAX_TIME = 180  # seconds

    api_calls = [0]
    t_start = time.time()
    category_url, base_extra = self._normalize_url(category_url)

    # Build golden filter lookup
    golden_list = []
    for f in golden_filters:
        if f.get("isGolden"):
            golden_list.append({
                "filterKey": f["filterKey"],
                "filterName": f["filterName"],
                "values": f.get("values", []),
            })

    def _budget_ok():
        return api_calls[0] < MAX_API_CALLS and (time.time() - t_start) < MAX_TIME

    def _do_scrape(extra):
        merged = dict(base_extra) if base_extra else {}
        merged.update(extra)
        result = self._chain_scrape(category_url, merged, location)
        api_calls[0] += 1
        return result

    logger.info(f"[ChainHunt] Starting: target=Rs {target_price}, "
                f"golden_filters={len(golden_list)}")

    # ── GREEDY-BEST CHAIN ────────────────────────────────────────────────
    # At each depth: test all unused filter values, pick the one that
    # raises min_price the most, commit, repeat.

    def _run_chain(initial_active=None, label="primary"):
        active = dict(initial_active or {})
        used_keys = set(active.keys())
        steps = []
        untapped_fallback = None  # saved in case we can't find a proper L1 path

        for depth in range(15):
            if not _budget_ok():
                break

            # 1. Scrape current state
            state = _do_scrape(active)
            if state["error"]:
                break

            current_min = state["min_price"]
            current_total = state["total"]
            current_sellers = state["seller_count"]

            # 2. WIN conditions
            if current_min is None or current_total == 0:
                # Untapped niche — no products at all
                return {
                    "iterations": steps,
                    "activeFilters": dict(active),
                    "status": "WIN",
                    "isUntapped": True,
                    "nicheMinPrice": None,
                    "totalProducts": current_total,
                    "sellerCount": current_sellers,
                    "chainLength": len(used_keys),
                }

            if current_min > target_price:
                # We are L1! All remaining products are more expensive
                return {
                    "iterations": steps,
                    "activeFilters": dict(active),
                    "status": "WIN",
                    "isUntapped": False,
                    "nicheMinPrice": current_min,
                    "totalProducts": current_total,
                    "sellerCount": current_sellers,
                    "chainLength": len(used_keys),
                }

            # 3. Find the BEST filter to raise min_price
            logger.info(
                f"[ChainHunt] [{label}] Depth {depth}: min=Rs {current_min}, "
                f"total={current_total}, filters={len(used_keys)}, "
                f"api={api_calls[0]}, {time.time()-t_start:.0f}s"
            )

            best_candidate = None  # {key, name, value, new_min, total, sellers}

            for gf in golden_list:
                if not _budget_ok():
                    break
                gf_key = gf["filterKey"]
                if gf_key in used_keys:
                    continue

                # Get live values from current facets
                live_vals = self._get_facet_values_for_key(
                    state["facets"], gf_key, gf["filterName"]
                )
                if not live_vals:
                    live_vals = gf.get("values", [])
                if not live_vals:
                    continue

                for val in live_vals:
                    if not _budget_ok():
                        break

                    tentative = dict(active)
                    tentative[gf_key] = val

                    test = _do_scrape(tentative)
                    if test["error"]:
                        continue

                    new_min = test["min_price"]
                    new_total = test["total"]
                    new_sellers = test["seller_count"]

                    # Untapped niche — save as fallback but DON'T return yet.
                    # We prefer paths where products exist but we're L1.
                    if new_min is None or new_total == 0:
                        if untapped_fallback is None:
                            untapped_fallback = {
                                "step": {
                                    "iteration": depth + 1,
                                    "prevMinPrice": current_min,
                                    "filterApplied": {
                                        "filterKey": gf_key,
                                        "filterName": gf["filterName"],
                                        "value": val,
                                    },
                                    "result": "UNTAPPED",
                                    "newMinPrice": None,
                                    "newTotal": 0,
                                },
                                "path": {
                                    "iterations": steps[:],
                                    "activeFilters": tentative,
                                    "status": "WIN",
                                    "isUntapped": True,
                                    "nicheMinPrice": None,
                                    "totalProducts": 0,
                                    "sellerCount": 0,
                                    "chainLength": len(used_keys) + 1,
                                },
                            }
                        continue  # Keep searching for non-untapped wins!

                    # Log what we found for debugging
                    logger.debug(
                        f"[ChainHunt]   {gf['filterName']}={val}: "
                        f"min=Rs {new_min}, total={new_total}"
                    )

                    # Skip if total products is too low (niche too narrow)
                    # At deeper depths the pool is already narrow, so relax the threshold
                    min_products = 3 if depth <= 1 else 1
                    if new_total < min_products:
                        logger.debug(f"[ChainHunt]   -> SKIP: only {new_total} products")
                        continue

                    # STRICT PROGRESS: new min must be HIGHER than current min
                    if new_min <= current_min:
                        continue

                    # Check if this is BETTER than our current best candidate
                    if best_candidate is None or new_min > best_candidate["new_min"]:
                        best_candidate = {
                            "key": gf_key,
                            "name": gf["filterName"],
                            "value": val,
                            "new_min": new_min,
                            "total": new_total,
                            "sellers": new_sellers,
                        }

                    # If this value already makes us L1, stop searching
                    if new_min > target_price:
                        break

                # If we found an L1 winner, no need to test more filters
                if best_candidate and best_candidate["new_min"] > target_price:
                    break

            # 4. Apply the best candidate
            if best_candidate is None:
                # No filter can raise the min price — stuck
                logger.info(
                    f"[ChainHunt] [{label}] STUCK at min=Rs {current_min} "
                    f"after {len(used_keys)} filters"
                )
                break

            step = {
                "iteration": depth + 1,
                "prevMinPrice": current_min,
                "filterApplied": {
                    "filterKey": best_candidate["key"],
                    "filterName": best_candidate["name"],
                    "value": best_candidate["value"],
                },
                "result": "ELIMINATED" if best_candidate["new_min"] <= target_price else "L1_WIN",
                "newMinPrice": best_candidate["new_min"],
                "newTotal": best_candidate["total"],
                "sellerCount": best_candidate["sellers"],
            }
            steps.append(step)

            logger.info(
                f"[ChainHunt] [{label}] PROGRESS: Rs {current_min} -> "
                f"Rs {best_candidate['new_min']} via "
                f"{best_candidate['name']}={best_candidate['value']}"
            )

            active[best_candidate["key"]] = best_candidate["value"]
            used_keys.add(best_candidate["key"])

            # Check if we just won
            if best_candidate["new_min"] > target_price:
                return {
                    "iterations": steps,
                    "activeFilters": dict(active),
                    "status": "WIN",
                    "isUntapped": False,
                    "nicheMinPrice": best_candidate["new_min"],
                    "totalProducts": best_candidate["total"],
                    "sellerCount": best_candidate["sellers"],
                    "chainLength": len(used_keys),
                }

        # If we get here, we're stuck.
        results = []

        # Return the chain progress so far as a partial result
        if steps:
            last_step = steps[-1]
            stuck_min = last_step.get("newMinPrice", current_min)
            results.append({
                "iterations": steps,
                "activeFilters": dict(active),
                "status": "PARTIAL",
                "isUntapped": False,
                "nicheMinPrice": stuck_min,
                "totalProducts": last_step.get("newTotal", current_total),
                "sellerCount": last_step.get("sellerCount", 0),
                "chainLength": len(used_keys),
            })

        # Also return the untapped fallback if we found one
        if untapped_fallback:
            fb = untapped_fallback["path"]
            fb["iterations"] = steps + [untapped_fallback["step"]]
            results.append(fb)

        return results[0] if results else None  # Return best

    # ── Run the chain from different starting points ─────────────────────

    winning_paths = []

    # Primary: greedy-best from no filters
    path1 = _run_chain({}, "main")
    if path1:
        winning_paths.append(path1)

    # Alternative: try starting with each high-impact filter
    alt_count = 0
    for gf in golden_list[:6]:
        if not _budget_ok() or alt_count >= 4:
            break
        for val in gf.get("values", [])[:2]:
            if not _budget_ok():
                break
            start = {gf["filterKey"]: val}
            path = _run_chain(start, f"alt-{gf['filterName'][:15]}={val}")
            if path:
                if not any(p["activeFilters"] == path["activeFilters"] for p in winning_paths):
                    winning_paths.append(path)
                    alt_count += 1

    # Sort: prefer WIN > PARTIAL, then real L1 (not untapped) > highest min price > shortest chain
    winning_paths.sort(key=lambda p: (
        0 if p.get("status") == "WIN" else 1,
        0 if not p.get("isUntapped") else 1,
        -(p.get("nicheMinPrice") or 0),
        p.get("chainLength", 999),
    ))

    elapsed = time.time() - t_start
    status = "STUCK"
    if winning_paths:
        if any(p.get("status") == "WIN" for p in winning_paths):
            status = "WIN"
        else:
            status = "PARTIAL"

    logger.info(f"[ChainHunt] Done in {elapsed:.1f}s: {len(winning_paths)} winning paths, "
                f"{api_calls[0]} API calls")

    return {
        "winningPaths": winning_paths[:20],
        "totalPaths": len(winning_paths),
        "totalApiCalls": api_calls[0],
        "status": status,
        "goldenFilterCount": len(golden_list),
        "elapsed": round(elapsed, 1),
    }
