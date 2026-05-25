"""
GeM Filter Optimizer — FastAPI Backend
Scrapes public GeM listing pages and finds filter combinations where
your product ranks #1 (cheapest price) in every filtered sub-niche.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from scraper import GeMScraper
from l1_surpasser import L1ChainSurpasser
import hashlib
import time
import logging
import os

# ── Configure Production Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gem-optimizer")

app = FastAPI(
    title="GeM Filter Optimizer API", 
    version="4.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json"
)

# ── Middlewares ───────────────────────────────────────────────────────────────
app.add_middleware(GZipMiddleware, minimum_size=1000)  # Compress responses >1KB
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

class ProductSpecRequest(BaseModel):
    product_url: str

class ChainHuntRequest(BaseModel):
    category_url: str
    target_price: int
    golden_filters: list
    location: Optional[str] = ""
    mandatory_filters: Optional[list] = []
    excluded_filter_keys: Optional[list] = []

class SurgicalStrikeRequest(BaseModel):
    product_url: str
    category_url: str
    target_price: int
    golden_filters: list
    location: Optional[str] = ""

class L1SurpassRequest(BaseModel):
    category_url: str
    my_catalogue_id: str
    my_price: int


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "service": "GeM Filter Optimizer API", "version": "4.0.0"}


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
            detail="URL must be a GeM portal page (gem.gov.in or mkp.gem.gov.in).",
        )

    cache_key = hashlib.md5(f"{url}|{req.location}".encode()).hexdigest()
    if cache_key in _cache:
        entry = _cache[cache_key]
        if time.time() - entry["ts"] < CACHE_TTL:
            return {**entry["data"], "cached": True}

    scraper = GeMScraper()
    result = scraper.scrape(url, location=req.location or "")

    if not result.get("products"):
        is_product_page = "/product-detail/" in url or "/product/" in url
        if is_product_page:
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


@app.delete("/cache")
def clear_cache():
    _cache.clear()
    return {"cleared": True}


# ── Smart L1 Chain Hunt ───────────────────────────────────────────────────────

@app.post("/chain-hunt")
def chain_hunt(req: ChainHuntRequest):
    """
    Sequential L1 Chain Surpasser.
    Iteratively eliminates each L1 blocker one-by-one through golden filter
    application, re-evaluating the market after each change, until the
    user's product becomes L1.
    """
    if req.target_price <= 0:
        raise HTTPException(status_code=400, detail="target_price must be > 0.")

    golden = req.golden_filters
    if not golden:
        raise HTTPException(
            status_code=422,
            detail="No golden filters provided. Run category scrape first."
        )

    try:
        scraper = GeMScraper()
        # Always exclude MSE — only manufacturers can use it, not resellers
        excluded = set(req.excluded_filter_keys or [])
        excluded.add("mse_applicable")
        result = scraper.smart_l1_discovery(
            category_url=req.category_url,
            target_price=req.target_price,
            golden_filters=golden,
            location=req.location or "",
            excluded_filter_keys=list(excluded),
            mandatory_filters=req.mandatory_filters or [],
        )
        return result
    except Exception as e:
        logger.error(f"Chain hunt failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chain hunt failed: {str(e)}")


# ── Product Specifications ───────────────────────────────────────────────────

@app.post("/product-specs")
def get_product_specs(req: ProductSpecRequest):
    """
    Scrape live specifications for a single product.
    Used for Clickable Competitor L2/L3 insights.
    """
    try:
        scraper = GeMScraper()
        # _scrape_product_page requires two arguments: url and variant_id
        product_data = scraper._scrape_product_page(req.product_url, "")
        return {"status": "success", "specs": product_data.get("specs", {})}
    except Exception as e:
        logger.error(f"Failed to scrape specs for {req.product_url}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── Surgical Strike ──────────────────────────────────────────────────────────

@app.post("/surgical-strike")
def surgical_strike(req: SurgicalStrikeRequest):
    """
    Surgical Strike: Analyze a specific competitor product.
    Scrapes the competitor's product page to extract their specs,
    matches them against golden filters, and identifies which filter
    values to apply to exclude that competitor from the niche.
    """
    if req.target_price <= 0:
        raise HTTPException(status_code=400, detail="target_price must be > 0.")

    product_url = req.product_url.strip()
    if not product_url.startswith("http://") and not product_url.startswith("https://"):
        product_url = "https://" + product_url

    try:
        scraper = GeMScraper()
        result = scraper.surgical_strike(
            product_url=product_url,
            category_url=req.category_url,
            target_price=req.target_price,
            golden_filters=req.golden_filters,
            location=req.location or "",
        )
        return result
    except Exception as e:
        logger.error(f"Surgical strike failed: {e}")
        raise HTTPException(status_code=500, detail=f"Surgical strike failed: {str(e)}")


# ── L1 Chain Surpasser (Hardened Engine) ────────────────────────────────────

@app.post("/l1-surpass")
def l1_surpass(req: L1SurpassRequest):
    """
    Hardened L1 Chain Surpasser.
    Sequential filter elimination with full-category scrapes,
    offset-drift detection, deduplication, and structured logging.
    """
    if req.my_price <= 0:
        raise HTTPException(status_code=400, detail="my_price must be > 0.")
    if not req.category_url.strip():
        raise HTTPException(status_code=400, detail="category_url is required.")

    try:
        surpasser = L1ChainSurpasser(
            category_url=req.category_url,
            my_catalogue_id=req.my_catalogue_id,
            my_price=req.my_price,
        )
        result = surpasser.run()
        return result
    except Exception as e:
        logger.error(f"L1 Surpass failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"L1 Chain Surpasser failed: {str(e)}"
        )


# ── PRODUCTION STATIC FILE MOUNT ───────────────────────────────────────────────
# Mounts compiled React static frontend if 'dist' folder exists in scope
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
    logger.info(f"Production frontend mounted successfully from {static_dir}")
else:
    logger.info("Static directory 'dist' not found; standalone API mode enabled.")
