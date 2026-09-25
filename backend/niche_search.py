"""
L1 niche search, measured by GeM itself.

The question: which combination of golden filters leaves the seller as the
cheapest listing (L1) at their price?

The old engine answered it from a sample: it read a few hundred of the
cheapest listings, opened product pages for ~40 of them to learn their specs,
and searched filter combinations in memory. A listing whose specs it hadn't
read passed every filter, so on a big category (48k chairs) almost every
cheap listing blocked every niche, and it reported "no path" for combinations
it could not actually evaluate.

This engine asks GeM instead. One filtered query returns GeM's exact count of
matching listings and the cheapest of them, across the entire category, with
GeM applying the filter to every listing's specs. So:

1. Every golden-filter value is queried once (level 1).
2. Combinations are explored best-first, one filter at a time, up to
   MAX_DEPTH deep, within a query budget. A combination is pruned without a
   query when one of its parent niche's blockers (a listing at or under the
   seller's price) also appears in the single-value niche being added: that
   listing survives the intersection, so the combination cannot win.
3. A winning niche is dropped if a broader one (a subset of its filters)
   already wins -- a seller wants the widest niche they lead.
4. Finalists are priced from product pages before any verdict, because GeM's
   search index lags behind price cuts (see chain_hunt._reprice_from_pages).
"""
import heapq
import itertools
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from chain_hunt import (
    LIVE_PRICE_DEPTH,
    _reprice_from_pages,
    _unreachable_result,
    extract_competitor_insights,
)
from gem_utils import (
    HTML_PARSER,
    build_product_url,
    extract_specs_from_soup,
    make_name_resolver,
    query_values_for,
)

logger = logging.getLogger("gem-niche-search")

MAX_DEPTH = 4
# Live niche queries spent on combinations, on top of one per filter value.
COMBINATION_BUDGET = 120
QUERY_CONCURRENCY = 4
MAX_WINS = 30
FINALISTS = 12
PARTIALS_SHOWN = 5
# Product pages read to learn filter values the category scan didn't see.
DISCOVERY_PAGES = 24


def _discover_values(crawler, category_url: str, location: str, filter_meta: dict) -> dict:
    """
    Learn golden-filter values from a spread of listings across the category.

    The scan reads specs from the ~15 cheapest listings, so which values it
    finds depends on which 15 those were -- two scans of the same chairs
    category produced 6 and 13 values. Reading listings from the cheap end,
    the expensive end and GeM's default order sees far more of what sellers
    actually list. Returns {filterKey: {value, ...}}.
    """
    import json
    from urllib.parse import urlencode
    from bs4 import BeautifulSoup
    from crawler import _extract_json_text

    base_url = crawler._normalize_url(category_url)[0]
    extra = {"localized_search": location} if location and location.lower() not in ("", "all india", "all") else {}
    pages = [{"page": 1, "sort_type": "price_in_asc"}, {"page": 1, "sort_type": "price_in_desc"},
             {"page": 1}, {"page": 3}, {"page": 8}]
    listing_pages = crawler._bm.fetch_many(
        [f"{base_url}?{urlencode({**q, 'format': 'json', **extra})}" for q in pages],
        timeout=20000, retries=2, concurrency=2)

    urls = []
    for text in listing_pages:
        body = _extract_json_text(text or "")
        if not body:
            continue
        for cat in json.loads(body).get("catalogs", []):
            u = build_product_url(cat)
            if u and u not in urls:
                urls.append(u)
    # Take evenly from each source rather than the first page's worth.
    picked = urls[::max(1, len(urls) // DISCOVERY_PAGES)][:DISCOVERY_PAGES]

    resolve = make_name_resolver([m["name"] for m in filter_meta.values()])
    key_for = {m["name"]: k for k, m in filter_meta.items()}
    found = {k: set() for k in filter_meta}
    for html in crawler._bm.fetch_many(picked, timeout=20000, retries=2, concurrency=4):
        if not html or "default_variant_id" not in html:
            continue
        for spec_name, value in extract_specs_from_soup(BeautifulSoup(html, HTML_PARSER)).items():
            name = resolve(spec_name)
            if name and value and len(value) <= 150:
                found[key_for[name]].add(value.strip())
    return found


def find_l1_niches(category_url: str, target_price: int, golden_filters: list,
                   location: str = "", excluded_filter_keys: list = None,
                   mandatory_filters: list = None) -> dict:
    from crawler import GeMCrawler

    t_start = time.time()
    crawler = GeMCrawler()
    calls = [0]

    excluded = set(excluded_filter_keys or []) | {"mse_applicable"}
    start_filters = {mf["filterKey"]: mf["value"] for mf in (mandatory_filters or [])
                     if mf.get("filterKey") and mf.get("value")}

    def query(filters: dict, pages: int = 1) -> dict:
        calls[0] += 1
        return crawler.crawl_filtered_prices(category_url, {**start_filters, **filters},
                                             location, max_pages=pages)

    # ── The category itself ──────────────────────────────────────────────
    base = query({})
    if base.get("error"):
        # GeM's homepage links are aliases that serve the app, not JSON.
        canonical = crawler._resolve_canonical_category(crawler._normalize_url(category_url)[0])
        if canonical:
            logger.info(f"[Niche] Following canonical category {canonical}")
            category_url = canonical
            base = query({})
    if base.get("error"):
        return _unreachable_result(calls[0], len(golden_filters), t_start, target_price,
                                   "GeM didn't return a readable listing for this category")

    category_total = base["total"]
    market_floor = base["min_price"]
    logger.info(f"[Niche] {category_total} listings, floor {market_floor}, target {target_price}")

    # ── Level 1: every golden value, measured by GeM ─────────────────────
    options = []          # (filterKey, value)
    filter_meta = {}      # filterKey -> {name, type}
    for f in golden_filters:
        key = f.get("filterKey")
        if not f.get("isGolden") or not key or key in excluded or key in start_filters:
            continue
        filter_meta[key] = {"name": f.get("filterName", key), "type": f.get("type", ""),
                            "values": list(f.get("values", []))}

    discovered = _discover_values(crawler, category_url, location, filter_meta) if filter_meta else {}
    calls[0] += 5 + DISCOVERY_PAGES
    learned = 0
    for key, meta in filter_meta.items():
        known = {v.lower() for v in meta["values"]}
        for v in sorted(discovered.get(key, ())):
            if v.lower() not in known:
                meta["values"].append(v)
                known.add(v.lower())
                learned += 1
        seen = set()
        for v in meta["values"]:
            for qv in query_values_for(v, meta["type"]):
                if qv.lower() not in seen:
                    seen.add(qv.lower())
                    options.append((key, qv))
    logger.info(f"[Niche] {learned} filter values learned beyond the scan; {len(options)} to measure")

    stats = {}            # frozenset({(k, v), ...}) -> query result
    parent = {}           # state -> (parent_state, (k, v)) that produced it
    root = frozenset()
    stats[root] = base

    with ThreadPoolExecutor(max_workers=QUERY_CONCURRENCY) as pool:
        for opt, res in zip(options, pool.map(lambda o: query({o[0]: o[1]}), options)):
            state = frozenset([opt])
            stats[state] = res
            parent[state] = (root, opt)

    unrecognized, ignored_keys, usable = [], set(), []
    for opt in options:
        res = stats[frozenset([opt])]
        if res.get("error"):
            continue
        if res.get("ignored"):
            ignored_keys.add(opt[0])
        elif res["total"] == 0:
            unrecognized.append({"filterKey": opt[0], "filterName": filter_meta[opt[0]]["name"],
                                 "value": opt[1]})
        else:
            usable.append(opt)
    usable = [o for o in usable if o[0] not in ignored_keys]

    # How much of the category do the values we know about account for? On a
    # single-choice filter the listings across its values should add up to
    # the category; a shortfall means values exist that the scan never saw.
    coverage = []
    for key, meta in filter_meta.items():
        if key in ignored_keys or meta["type"] == "MultiselectAnd":
            continue
        counted = sum(stats[frozenset([o])]["total"] for o in usable if o[0] == key)
        if category_total:
            coverage.append({"filterKey": key, "filterName": meta["name"],
                             "share": round(min(1.0, counted / category_total), 3)})

    # ── Combinations, best-first ─────────────────────────────────────────
    def floor(state):
        return stats[state].get("min_price")

    def wins(state):
        r = stats[state]
        return (not r.get("error") and not r.get("ignored") and r["total"] > 0
                and r["min_price"] is not None and r["min_price"] > target_price)

    def blockers(state):
        return {p["url"] for p in stats[state].get("products") or []
                if p.get("url") and p["price"] <= target_price}

    single_urls = {o: {p["url"] for p in stats[frozenset([o])].get("products") or [] if p.get("url")}
                   for o in usable}

    frontier, tick = [], itertools.count()

    def push_children(state):
        if len(state) >= MAX_DEPTH or wins(state):
            return
        r = stats[state]
        if r.get("error") or r.get("ignored") or r["total"] == 0:
            return
        used = {k for k, _ in state}
        blocking = blockers(state)
        for opt in usable:
            if opt[0] in used:
                continue
            child = state | {opt}
            if child in stats:
                continue
            # Adding a value that a blocker already has leaves that blocker in.
            if blocking & single_urls[opt]:
                continue
            # A broader niche already wins with this value alone.
            if wins(frozenset([opt])):
                continue
            # The child's floor can't be under either parent's: a lower
            # bound on how close it gets to beating the seller's price.
            bound = max((x for x in (floor(state), floor(frozenset([opt]))) if x is not None),
                        default=0)
            heapq.heappush(frontier, (-bound, len(child), next(tick), state, opt))

    # Already the cheapest in the whole category: no filter needed.
    if wins(root):
        usable = []
    for o in usable:
        push_children(frozenset([o]))

    spent = 0
    with ThreadPoolExecutor(max_workers=QUERY_CONCURRENCY) as pool:
        while frontier and spent < COMBINATION_BUDGET and sum(map(wins, stats)) < MAX_WINS:
            batch = []
            while frontier and len(batch) < QUERY_CONCURRENCY:
                _, _, _, state, opt = heapq.heappop(frontier)
                child = state | {opt}
                if child not in stats and all(child != b[0] for b in batch):
                    batch.append((child, state, opt))
            if not batch:
                break
            results = pool.map(lambda b: query(dict(b[0])), batch)
            for (child, state, opt), res in zip(batch, results):
                stats[child] = res
                parent[child] = (state, opt)
                spent += 1
                push_children(child)

    logger.info(f"[Niche] {len(options)} single-value and {spent} combination queries; "
                f"{sum(map(wins, stats))} winning niches before page checks")

    # ── Pick finalists ──────────────────────────────────────────────────
    winning = [s for s in stats if wins(s)]
    winning = [s for s in winning if not any(o < s for o in winning)]   # broadest only
    winning.sort(key=lambda s: (len(s), -stats[s]["total"]))
    winning = winning[:FINALISTS]

    failed = sum(1 for s in stats if stats[s].get("error"))
    blocked = [s for s in stats if s and not wins(s) and not stats[s].get("error")
               and not stats[s].get("ignored") and stats[s]["total"] > 0]
    blocked.sort(key=lambda s: (-(floor(s) or 0), len(s)))
    partial = blocked[:PARTIALS_SHOWN] if not winning else []

    # Winners need every listing we can see, so read their second page too.
    for s in winning:
        fuller = query(dict(s), pages=2)
        if not fuller.get("error") and not fuller.get("ignored"):
            stats[s] = fuller

    # ── Price the deciding listings from their own pages ────────────────
    chosen = winning + partial
    wanted = []
    for s in chosen:
        listings = sorted(stats[s].get("products") or [], key=lambda p: p["price"])
        depth = len(listings) if s in winning else LIVE_PRICE_DEPTH
        wanted.extend(p["url"] for p in listings[:depth] if p.get("url"))
    page_prices = crawler.live_prices(wanted) if wanted else {}
    calls[0] += len(page_prices)
    for s in chosen:
        _reprice_from_pages(stats[s], page_prices)

    # ── Assemble the answer ─────────────────────────────────────────────
    def path_order(state):
        steps, cur = [], state
        while cur:
            prev, opt = parent[cur]
            steps.append((prev, cur, opt))
            cur = prev
        return list(reversed(steps))

    def iterations(state, won):
        out = []
        for i, (prev, cur, (key, val)) in enumerate(path_order(state)):
            before, after = floor(prev) if prev else market_floor, stats[cur].get("min_price")
            if cur == state and won:
                result = "L1_WIN"
            elif after is not None and before is not None and after <= before:
                result = "LATERAL"
            else:
                result = "ELIMINATED"
            out.append({
                "iteration": i + 1,
                "prevMinPrice": before,
                "filterApplied": {"filterKey": key, "filterName": filter_meta[key]["name"], "value": val},
                "result": result,
                # Every step is GeM's own count over the whole category, on
                # the search index's prices -- one scale from first row to last.
                "newMinPrice": after,
                "newTotal": stats[cur]["total"],
                "sellerCount": stats[cur].get("seller_count", 0),
                "scope": "live",
            })
        return out

    paths = []
    for s in chosen:
        r = stats[s]
        won = r["min_price"] is not None and r["min_price"] > target_price
        paths.append({
            "iterations": iterations(s, won),
            "activeFilters": {**start_filters, **dict(s)},
            "status": "WIN" if won else "PARTIAL",
            "isUntapped": False,
            "nicheMinPrice": r["min_price"],
            "totalProducts": r["total"],
            "sellerCount": r.get("seller_count", 0),
            "priceCheck": r.get("priceCheck"),
            "chainLength": len(s) + len(start_filters),
            "competitorInsights": extract_competitor_insights(r.get("products") or [], target_price),
        })
    # A page check can take a win away; winners first, broadest first.
    paths.sort(key=lambda p: (p["status"] != "WIN", p["chainLength"], -(p["totalProducts"] or 0)))

    floors = [p["nicheMinPrice"] for p in paths if p["nicheMinPrice"]]
    return {
        "winningPaths": paths,
        "totalPaths": len(paths),
        "unconfirmedPaths": [],
        "totalApiCalls": calls[0],
        "status": "WIN" if any(p["status"] == "WIN" for p in paths) else "PARTIAL",
        "goldenFilterCount": len(filter_meta),
        "elapsed": round(time.time() - t_start, 1),
        "bestAchievablePrice": max(floors) if floors else None,
        "marketMinPrice": market_floor,
        "targetPrice": target_price,
        "engine": "gem-filter-search",
        "searchedListings": category_total,
        "sampleSize": category_total,
        "nicheQueries": len(options) + spent,
        "failedQueries": failed,
        "unrecognizedValues": unrecognized,
        "ignoredFilterKeys": sorted(ignored_keys),
        "filterCoverage": coverage,
        "valuesLearned": learned,
    }
