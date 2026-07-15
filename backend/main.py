"""
GeM Filter Optimizer — FastAPI Backend (v5.0.0)

Powered by Playwright-based browser crawling for complete, accurate
GeM marketplace data extraction. Finds filter combinations where
your product ranks #1 (cheapest price) in every filtered sub-niche.
"""
from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from contextlib import asynccontextmanager
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


# ── Application Lifecycle ────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage browser lifecycle: start on boot, shutdown on exit."""
    logger.info("Starting GeM Filter Optimizer v5.0.0...")
    try:
        from crawler import BrowserManager
        bm = BrowserManager.get_instance()
        logger.info("Browser manager initialized.")
    except Exception as e:
        logger.warning(f"Browser pre-init skipped (will lazy-init on first request): {e}")
    
    yield  # App is running
    
    # Shutdown
    logger.info("Shutting down browser...")
    try:
        from crawler import BrowserManager
        BrowserManager.get_instance().shutdown()
    except Exception:
        pass
    logger.info("Shutdown complete.")


app = FastAPI(
    title="GeM Filter Optimizer API",
    version="5.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ── Middlewares ───────────────────────────────────────────────────────────────
app.add_middleware(GZipMiddleware, minimum_size=1000)
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

api_router = APIRouter(prefix="/api")

@api_router.get("/")
def root():
    return {"status": "ok", "service": "GeM Filter Optimizer API", "version": "5.0.0"}


@api_router.get("/health")
def health():
    """Health check that verifies the browser is alive."""
    try:
        from crawler import BrowserManager
        bm = BrowserManager.get_instance()
        return {
            "status": "healthy",
            "browser_alive": bm.is_alive,
            "version": "5.0.0",
        }
    except Exception as e:
        return {"status": "degraded", "error": str(e), "version": "5.0.0"}


@api_router.get("/locations")
def locations():
    """Return the list of all Indian states/UTs for location filtering."""
    from crawler import GeMCrawler
    return {
        "locations": ["All India"] + GeMCrawler.INDIAN_STATES,
        "total": len(GeMCrawler.INDIAN_STATES) + 1,
    }


@api_router.post("/scrape")
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

    # Use new Playwright-based crawler
    from crawler import GeMCrawler
    crawler = GeMCrawler()
    result = crawler.crawl_category(url, location=req.location or "")

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


@api_router.delete("/cache")
def clear_cache():
    _cache.clear()
    return {"cleared": True}


# ── Smart L1 Chain Hunt ───────────────────────────────────────────────────────

@api_router.post("/chain-hunt")
def chain_hunt(req: ChainHuntRequest):
    """
    Sequential L1 Chain Surpasser (now powered by Playwright crawler).
    Uses the new GeMCrawler for live verification of filter paths.
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
        # Use the existing chain_hunt logic via scraper (which now delegates to crawler)
        from scraper import GeMScraper
        scraper = GeMScraper()
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

@api_router.post("/product-specs")
def get_product_specs(req: ProductSpecRequest):
    """
    Scrape live specifications for a single product using Playwright.
    Used for Clickable Competitor L2/L3 insights.
    """
    try:
        from crawler import GeMCrawler
        crawler = GeMCrawler()
        product_data = crawler.crawl_product(req.product_url)
        return {"status": "success", "specs": product_data.get("specs", {})}
    except Exception as e:
        logger.error(f"Failed to scrape specs for {req.product_url}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── Surgical Strike ──────────────────────────────────────────────────────────

@api_router.post("/surgical-strike")
def surgical_strike(req: SurgicalStrikeRequest):
    """
    Surgical Strike: Analyze a specific competitor product.
    Now uses Playwright crawler for more reliable spec extraction.
    """
    if req.target_price <= 0:
        raise HTTPException(status_code=400, detail="target_price must be > 0.")

    product_url = req.product_url.strip()
    if not product_url.startswith("http://") and not product_url.startswith("https://"):
        product_url = "https://" + product_url

    try:
        from scraper import GeMScraper
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

@api_router.post("/l1-surpass")
def l1_surpass(req: L1SurpassRequest):
    """
    Hardened L1 Chain Surpasser.
    Sequential filter elimination with full-category scrapes.
    """
    if req.my_price <= 0:
        raise HTTPException(status_code=400, detail="my_price must be > 0.")
    if not req.category_url.strip():
        raise HTTPException(status_code=400, detail="category_url is required.")

    try:
        from l1_surpasser import L1ChainSurpasser
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


# ── API Router Inclusion ──────────────────────────────────────────────────────
app.include_router(api_router)


# ── PRODUCTION STATIC FILE MOUNT ───────────────────────────────────────────────
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
    logger.info(f"Production frontend mounted successfully from {static_dir}")
else:
    logger.info("Static directory 'dist' not found; standalone API mode enabled.")
