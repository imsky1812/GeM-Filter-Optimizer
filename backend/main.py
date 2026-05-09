"""
GeM Filter Optimizer — FastAPI Backend
Scrapes public GeM listing pages and finds filter combinations where
your product ranks #1 (cheapest price) in every filtered sub-niche.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from scraper import GeMScraper
import hashlib
import time


app = FastAPI(title="GeM Filter Optimizer API", version="3.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Cache (30 min TTL) ────────────────────────────────────────────────────────
_cache: dict = {}
CACHE_TTL = 1800


# ── Request models ────────────────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    url: str
    location: Optional[str] = ""

class AnalyzeRequest(BaseModel):
    products: list
    filters: list
    seller_price: int
    seller_specs: dict

class FindL1Request(BaseModel):
    url: str
    seller_price: int
    location: Optional[str] = ""
    max_depth: Optional[int] = None
    golden_filters: Optional[list] = []  # from initial /scrape response


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "service": "GeM Filter Optimizer API", "version": "3.0.0"}


@app.get("/locations")
def locations():
    """Return the list of all Indian states/UTs for location filtering."""
    return {
        "locations": ["All India"] + GeMScraper.INDIAN_STATES,
        "total": len(GeMScraper.INDIAN_STATES) + 1,
    }


@app.post("/scrape")
def scrape(req: ScrapeRequest):
    url = req.url.strip()

    # Auto-prepend https:// if no protocol given
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    gem_hosts = [
        "gem.gov.in",
        "mkp.gem.gov.in",
        "mkp.gemorion.org",
    ]
    from urllib.parse import urlparse as _urlparse
    parsed_host = _urlparse(url).hostname or ""
    if not any(parsed_host == h or parsed_host.endswith("." + h) for h in gem_hosts):
        raise HTTPException(
            status_code=400,
            detail="URL must be a GeM portal page (gem.gov.in, mkp.gem.gov.in, or mkp.gemorion.org).",
        )

    cache_key = hashlib.md5(f"{url}|{req.location or ''}".encode()).hexdigest()
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached["ts"]) < CACHE_TTL:
        return {**cached["data"], "cached": True}

    try:
        result = GeMScraper().scrape(url, location=req.location or "")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scraping failed: {e}")

    # Check for error from scraper (e.g., couldn't resolve category)
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])

    if not result["products"]:
        is_product_url = "/p-" in url and "-cat.html" in url
        if is_product_url:
            detail = (
                "Found your product but couldn't locate the category listing. "
                "Try using a category search URL instead, e.g.: "
                "https://mkp.gem.gov.in/{category-slug}/search"
            )
        else:
            detail = (
                "No products found on this page. Make sure the URL is a GeM "
                "category listing page (e.g. from the category search results)."
            )
        raise HTTPException(status_code=422, detail=detail)

    _cache[cache_key] = {"data": result, "ts": time.time()}
    return {**result, "cached": False}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    if req.seller_price <= 0:
        raise HTTPException(status_code=400, detail="Seller price must be > 0.")
    results = _analyze(req.products, req.seller_price, req.seller_specs, req.filters)
    return {"results": results, "total": len(results)}


@app.delete("/cache")
def clear_cache():
    _cache.clear()
    return {"cleared": True}


@app.post("/find-l1")
def find_l1(req: FindL1Request):
    """
    Cascading golden filter deep search.
    Re-scrapes the GeM API after each golden filter is applied to find
    the next available golden filters in the narrowed niche, repeating
    until the seller's price becomes L1 or max_depth is reached.
    Supports 3+ golden filter combinations.
    """
    if req.seller_price <= 0:
        raise HTTPException(status_code=400, detail="seller_price must be > 0.")

    url = req.url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    from urllib.parse import urlparse as _urlparse
    gem_hosts = ["gem.gov.in", "mkp.gem.gov.in", "mkp.gemorion.org"]
    parsed_host = _urlparse(url).hostname or ""
    if not any(parsed_host == h or parsed_host.endswith("." + h) for h in gem_hosts):
        raise HTTPException(
            status_code=400,
            detail="URL must be a GeM portal page (gem.gov.in or mkp.gem.gov.in).",
        )

    # If frontend passed golden_filters from initial scrape, use them directly.
    # Otherwise fall back to doing a fresh scrape inside find_l1_combinations.
    golden_filters = req.golden_filters or []
    if not golden_filters:
        # No filters passed — do a quick scrape to get them
        try:
            scraped = GeMScraper().scrape(url, location=req.location or "")
            golden_filters = [f for f in scraped.get("filters", []) if f.get("isGolden")]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch golden filters: {e}")

    if not golden_filters:
        raise HTTPException(
            status_code=422,
            detail="No golden filters found for this category. Cannot run deep search."
        )

    try:
        result = GeMScraper().find_l1_combinations(
            url=url,
            seller_price=req.seller_price,
            golden_filters=golden_filters,
            location=req.location or "",
            max_depth=req.max_depth,  # None = dynamic (= number of golden filters)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deep search failed: {e}")

    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])

    return result


# ── Core analysis engine ──────────────────────────────────────────────────────

def _detect_dependencies(products: list, filters: list) -> list:
    """
    Dynamically reconstruct GeM's internal taxonomy dependencies.
    """
    rules = []
    if not products or len(products) < 5:
        return rules

    for i, f1 in enumerate(filters):
        for j, f2 in enumerate(filters):
            if i == j:
                continue
                
            observations = {}
            total_observed = 0
            
            for p in products:
                specs = p.get("specs", {})
                v1 = str(specs.get(f1["filterKey"], "")).strip().lower()
                v2 = str(specs.get(f2["filterKey"], "")).strip().lower()
                
                if v1 and v2:
                    if v1 not in observations:
                        observations[v1] = set()
                    observations[v1].add(v2)
                    total_observed += 1
                    
            if total_observed < 10:
                continue
                
            strictly_determines = True
            for v2_set in observations.values():
                if len(v2_set) > 1:
                    strictly_determines = False
                    break
                    
            if strictly_determines:
                mapping = {v1: list(v2_set)[0] for v1, v2_set in observations.items()}
                rules.append({
                    "detKey": f1["filterKey"],
                    "depKey": f2["filterKey"],
                    "mapping": mapping
                })
                
    return rules

def _analyze(products: list, seller_price: int, seller_specs: dict, filters: list) -> list:
    """
    For every 1-filter and 2-filter combination, check if the seller's price
    is the lowest (rank #1). Returns results sorted by opportunity score.
    """
    combos = []
    for i, f1 in enumerate(filters):
        for v1 in f1["values"]:
            combos.append([{"key": f1["filterKey"], "name": f1["filterName"], "value": v1, "isGolden": f1.get("isGolden", False)}])
        for f2 in filters[i + 1:]:
            for v1 in f1["values"]:
                for v2 in f2["values"]:
                    combos.append([
                        {"key": f1["filterKey"], "name": f1["filterName"], "value": v1, "isGolden": f1.get("isGolden", False)},
                        {"key": f2["filterKey"], "name": f2["filterName"], "value": v2, "isGolden": f2.get("isGolden", False)},
                    ])

    rules = _detect_dependencies(products, filters)
    valid_combos = []
    
    for combo in combos:
        is_contradictory = False
        for i, c1 in enumerate(combo):
            for j, c2 in enumerate(combo):
                if i == j:
                    continue
                
                rule = next((r for r in rules if r["detKey"] == c1["key"] and r["depKey"] == c2["key"]), None)
                if rule:
                    expected_v2 = rule["mapping"].get(str(c1["value"]).lower())
                    if expected_v2 and expected_v2 != str(c2["value"]).lower():
                        is_contradictory = True
                        break
            if is_contradictory:
                break
                
        if not is_contradictory:
            valid_combos.append(combo)

    results = []
    max_gap = seller_price * 0.8 or 1

    for combo in valid_combos:
        matching = [
            p for p in products
            if all(str(p["specs"].get(c["key"], "")).lower() == c["value"].lower() for c in combo)
        ]
        is_untapped = len(matching) == 0
        min_comp = float('inf') if is_untapped else min(p["price"] for p in matching)

        # Only include combos where seller IS the cheapest
        if min_comp <= seller_price:
            continue

        price_gap   = seller_price * 0.5 if is_untapped else min_comp - seller_price
        qualifies   = all(
            str(seller_specs.get(c["key"], "")).lower() == c["value"].lower()
            for c in combo
        )
        spec_changes = [
            {"filterName": c["name"], "filterKey": c["key"],
             "required": c["value"], "current": seller_specs.get(c["key"], "Not set")}
            for c in combo
            if str(seller_specs.get(c["key"], "")).lower() != c["value"].lower()
        ]

        gap_score      = 100 if is_untapped else min(price_gap / max_gap, 1) * 100
        scarcity_score = max(1 - len(matching) / 10, 0) * 100
        traffic_score  = 80 if is_untapped else min(len(matching) / 5, 1) * 100
        has_golden     = any(c.get("isGolden", False) for c in combo)
        raw_score      = gap_score * 0.5 + scarcity_score * 0.3 + traffic_score * 0.2
        score          = 100 if is_untapped else round(raw_score if has_golden else raw_score * 0.3)

        competitors = sorted(matching, key=lambda p: p["price"])[:3]

        results.append({
            "combo":               combo,
            "label":               " + ".join(f'{c["name"]}: {c["value"]}' for c in combo),
            "competitorCount":     len(matching),
            "minCompetitorPrice":  min_comp,
            "sellerPrice":         seller_price,
            "priceGap":            0 if is_untapped else price_gap,
            "qualifies":           qualifies,
            "specChanges":         spec_changes,
            "competitors":         competitors,
            "score":               score,
            "status":              "WIN" if qualifies else "POSSIBLE",
            "isUntapped":          is_untapped,
            "hasGolden":           has_golden,
        })

    return sorted(results, key=lambda r: r["score"], reverse=True)
