"""
GeM Filter Optimizer — FastAPI Backend
Scrapes public GeM listing pages and finds filter combinations where
your product ranks #1 (cheapest price) in every filtered sub-niche.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from scraper import GeMScraper
import hashlib
import time


app = FastAPI(title="GeM Filter Optimizer API", version="3.0.0")

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

class AnalyzeRequest(BaseModel):
    products: list
    filters: list
    seller_price: int
    seller_specs: dict


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "service": "GeM Filter Optimizer API", "version": "3.0.0"}


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

    cache_key = hashlib.md5(url.encode()).hexdigest()
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached["ts"]) < CACHE_TTL:
        return {**cached["data"], "cached": True}

    try:
        result = GeMScraper().scrape(url)
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


# ── Core analysis engine ──────────────────────────────────────────────────────

def _analyze(products: list, seller_price: int, seller_specs: dict, filters: list) -> list:
    """
    For every 1-filter and 2-filter combination, check if the seller's price
    is the lowest (rank #1). Returns results sorted by opportunity score.
    """
    combos = []
    for i, f1 in enumerate(filters):
        for v1 in f1["values"]:
            combos.append([{"key": f1["filterKey"], "name": f1["filterName"], "value": v1}])
        for f2 in filters[i + 1:]:
            for v1 in f1["values"]:
                for v2 in f2["values"]:
                    combos.append([
                        {"key": f1["filterKey"], "name": f1["filterName"], "value": v1},
                        {"key": f2["filterKey"], "name": f2["filterName"], "value": v2},
                    ])

    results = []
    max_gap = seller_price * 0.8 or 1

    for combo in combos:
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
        score          = 100 if is_untapped else round(gap_score * 0.5 + scarcity_score * 0.3 + traffic_score * 0.2)

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
        })

    return sorted(results, key=lambda r: r["score"], reverse=True)
