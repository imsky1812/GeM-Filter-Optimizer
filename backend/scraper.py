"""
GeMScraper — scrapes GeM marketplace using their internal JSON API.
Supports both product detail page URLs and category listing URLs.
No browser needed — uses requests + BeautifulSoup.
"""
import re
import json
import time
import random
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urlencode, urldefrag


class GeMScraper:
    # Global class-level semaphore ensures no more than 8 concurrent HTTP requests 
    # are sent to GeM's network ANYWHERE in the entire backend application loop,
    # completely insulating our server from firing Firewall-banning spikes.
    _HTTP_SEMAPHORE = threading.BoundedSemaphore(8)

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    }

    # All 36 Indian States and Union Territories (for location filtering)
    INDIAN_STATES = [
        "Andaman and Nicobar Islands",
        "Andhra Pradesh",
        "Arunachal Pradesh",
        "Assam",
        "Bihar",
        "Chandigarh",
        "Chhattisgarh",
        "Dadra and Nagar Haveli and Daman and Diu",
        "Delhi",
        "Goa",
        "Gujarat",
        "Haryana",
        "Himachal Pradesh",
        "Jammu and Kashmir",
        "Jharkhand",
        "Karnataka",
        "Kerala",
        "Ladakh",
        "Lakshadweep",
        "Madhya Pradesh",
        "Maharashtra",
        "Manipur",
        "Meghalaya",
        "Mizoram",
        "Nagaland",
        "Odisha",
        "Puducherry",
        "Punjab",
        "Rajasthan",
        "Sikkim",
        "Tamil Nadu",
        "Telangana",
        "Tripura",
        "Uttar Pradesh",
        "Uttarakhand",
        "West Bengal",
    ]

    # Configuration
    MAX_JSON_PAGES = 2000         # Fetch up to 2000 pages (covers ~24,000 products)
    MAX_ENRICH = 1000            # Enrich up to 1000 products with full specs
    ENRICH_WORKERS = 20          # Parallel workers for spec fetching
    MAX_FILTERS = 10             # Max non-golden filters to return (all golden filters always returned)
    MAX_COMBO_DEPTH = 10          # Explore golden filter combos up to 10 levels deep
    MAX_API_CALLS = 500          # Safety ceiling: stop exploration after this many re-scrapes

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update(self.HEADERS)
        self._product_specs_cache = {}
        
        # Configure robust retry strategy for connection timeouts and server errors
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        
        self._initialize_session()

    def _initialize_session(self):
        """Establish initial session cookies to prevent GeM from redirecting to homepage."""
        try:
            # Emulate browser visiting the homepage first to get JSESSIONID and cookies
            self._session.get("https://mkp.gem.gov.in/", timeout=15)
            time.sleep(0.5)
        except Exception:
            pass

    def __del__(self):
        try:
            self._session.close()
        except Exception:
            pass

    def _normalize_url(self, url: str) -> tuple[str, dict]:
        """
        Normalize a GeM URL. Handles:
          1. Auto-prepend https:// if no protocol
          2. Fragment-based query strings (search#/?q=XXX&page=1)
        Returns (clean_base_url, extra_query_params_dict)
        """
        url = url.strip()

        # Auto-prepend https:// if missing
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        # Parse fragment-based query params (e.g. search#/?q=PC%20Software&...)
        parsed = urlparse(url)
        extra_params = {}

        if parsed.fragment:
            frag = parsed.fragment
            # Strip leading /? or ? from fragment to get query string
            if frag.startswith("/?"):
                frag_qs = frag[2:]
            elif frag.startswith("?"):
                frag_qs = frag[1:]
            elif "?" in frag:
                frag_qs = frag.split("?", 1)[1]
            else:
                frag_qs = frag

            frag_params = parse_qs(frag_qs, keep_blank_values=True)
            for k, v_list in frag_params.items():
                # Flatten single-value lists
                extra_params[k] = v_list[0] if len(v_list) == 1 else v_list

        # Build clean base URL (without fragment and without existing query)
        clean_url = parsed._replace(fragment="", query="").geturl()

        return clean_url, extra_params

    def scrape(self, url: str, location: str = "") -> dict:
        """
        Main entry point. Accepts either:
          - A product page URL (p-XXXXX-YYYYY-cat.html)
          - A category/search URL (including fragment-based query URLs)
        Returns {filters, products, url, productCount, filterCount, yourProduct, location}
        """
        url = url.strip()
        your_product = None

        # Normalize URL: auto-prepend https://, extract fragment-based query params
        url, extra_params = self._normalize_url(url)

        # Detect if this is a product detail page
        product_match = re.search(r'/p-(\d+)-(\d+)-cat\.html', url)
        if product_match:
            catalog_id = product_match.group(1)
            variant_id = f"{catalog_id}-{product_match.group(2)}"
            your_product = self._scrape_product_page(url, variant_id)
            category_url = self._find_category_url(url, catalog_id)
            if category_url:
                url = category_url
            else:
                return {
                    "filters": [],
                    "products": [],
                    "url": url,
                    "productCount": 0,
                    "filterCount": 0,
                    "yourProduct": your_product,
                    "location": location or "All India",
                    "error": "Could not determine the category listing. Try using a category search URL instead.",
                }

        result = self._scrape_category_listing(url, extra_params, location)
        result["yourProduct"] = your_product
        return result

    def scrape_with_filters(self, url: str, selected_filters: list, location: str = "") -> dict:
        """
        Re-scrape a category listing with specific golden filters applied.
        selected_filters: [{"filterKey": "code", "value": "Yes"}, ...]
        GeM's JSON API supports facet params like &facet_code=value.
        Returns the same structure as scrape() but with filtered results.
        """
        url = url.strip()
        url, extra_params = self._normalize_url(url)

        # Merge selected filters into extra_params
        if extra_params is None:
            extra_params = {}
        for sf in selected_filters:
            extra_params[sf["filterKey"]] = sf["value"]

        result = self._scrape_category_listing(url, extra_params, location)
        result["appliedFilters"] = selected_filters
        return result
    def find_l1_combinations(
        self,
        url: str,
        seller_price: int,
        golden_filters: list,          # already scraped golden filters with values
        location: str = "",
        max_depth: int = None,
        min_depth: int = 3,
        max_api_calls: int = None,
    ) -> dict:
        """
        Cascading L1 finder.

        KEY DESIGN DECISIONS:
        - golden_filters come from the initial /scrape (no re-enrichment needed)
        - Each cascade step uses _fast_price_scrape: fetches all listing pages in
          parallel (NO product detail page visits) to get the true min price fast
        - Remaining golden filters = initial set MINUS already-applied keys
          (GeM never adds NEW golden filters when you narrow — it only removes the
           ones you've already applied, so re-discovery is never needed)
        - Results sorted deepest-first (most filters = most specific niche)
        """
        if max_api_calls is None:
            max_api_calls = self.MAX_API_CALLS

        url = url.strip()
        url, base_extra = self._normalize_url(url)

        # Only work with golden filters that have at least 2 values
        golden_filters = [
            f for f in golden_filters
            if f.get("isGolden") and len(f.get("values", [])) >= 1
        ]

        if not golden_filters:
            return {
                "combinations": [],
                "totalScraped": 0,
                "progress": ["No golden filters found — cannot cascade."],
                "truncated": False,
                "goldenFilterCount": 0,
            }

        # Dynamic depth = number of golden filters (no hardcoded cap)
        if max_depth is None:
            max_depth = len(golden_filters)
        
        # ── Tunneling Mode for Ultra Deep Searches (11+) ──
        tunnel_mode = True if (min_depth and min_depth >= 11) else False

        if tunnel_mode:
            # Shuffle randomly to explore DIFFERENT vertical combinations on repeated clicks
            random.shuffle(golden_filters)
        else:
            # Sort by fewest-values first to maximize vertical reach efficiently
            golden_filters.sort(key=lambda f: len(f.get("values", [])))


        combinations = []
        progress_log = []
        seen_combos = set()
        scrape_memo = {}
        api_calls = [0]
        truncated = [False]

        progress_log.append(
            f"[Start] {len(golden_filters)} golden filters · "
            f"Depth {min_depth} to {max_depth} · "
            f"TunnelMode={tunnel_mode} · seller price ₹{seller_price:,}"
        )

        def explore(applied: list, depth: int):
            """Recursively apply one more golden filter, re-scrape for min price."""
            if depth > max_depth or api_calls[0] >= max_api_calls:
                if api_calls[0] >= max_api_calls:
                    truncated[0] = True
                return

            applied_keys = {f["filterKey"] for f in applied}
            # Remaining = all golden filters minus already-applied keys
            available = [g for g in golden_filters if g["filterKey"] not in applied_keys]

            if not available:
                return

            # In Tunnel Mode, we pick ONE available filter at each level to force 
            # linear depth discovery rather than exploding horizontally.
            target_filters = available[:1] if tunnel_mode else available

            for gf in target_filters:
                if api_calls[0] >= max_api_calls:
                    truncated[0] = True
                    return

                vals = gf.get("values", [])
                if tunnel_mode:
                    # Take top 3 values only to force vertical exploration
                    vals = vals[:3]

                for val in vals:
                    if api_calls[0] >= max_api_calls:
                        truncated[0] = True
                        return

                    new_filter = {
                        "filterKey":  gf["filterKey"],
                        "filterName": gf["filterName"],
                        "value":      val,
                        "isGolden":   True,
                    }
                    new_applied = applied + [new_filter]

                    # Dedup
                    sig = tuple(sorted((f["filterKey"], f["value"]) for f in new_applied))
                    if sig in seen_combos:
                        continue
                    seen_combos.add(sig)

                    # Build filter params for this combo
                    extra = dict(base_extra) if base_extra else {}
                    for af in new_applied:
                        extra[af["filterKey"]] = af["value"]

                    combo_label = " + ".join(
                        f'{f["filterName"]}: {f["value"]}' for f in new_applied
                    )

                    memo_key = tuple(sorted(extra.items()))

                    try:
                        if memo_key in scrape_memo:
                            result = scrape_memo[memo_key]
                        else:
                            # Fast scrape: only listing pages, zero enrichment
                            result = self._fast_price_scrape(url, extra, location, seller_price=seller_price)
                            api_calls[0] += 1
                            scrape_memo[memo_key] = result

                        min_price     = result["min_price"]
                        total_in_niche = result["total"]
                        n_products    = result["product_count"]

                        # ── Untapped niche (zero products in this niche) ──────
                        if n_products == 0 and total_in_niche == 0:
                            combinations.append({
                                "combo":             new_applied,
                                "label":             combo_label,
                                "competitorCount":   0,
                                "minCompetitorPrice": None,
                                "sellerPrice":       seller_price,
                                "priceGap":          0,
                                "isUntapped":        True,
                                "hasGolden":         True,
                                "status":            "WIN",
                                "competitors":       [],
                                "depth":             depth,
                                "totalInNiche":      0,
                            })
                            progress_log.append(
                                f"  ✅ UNTAPPED (depth {depth}): {combo_label}"
                            )
                            continue  # can't go deeper — no products to narrow

                        if min_price is None:
                            # Could not determine price — go deeper anyway
                            if depth < max_depth:
                                explore(new_applied, depth + 1)
                            continue

                        if seller_price < min_price:
                            # ── L1 WIN ───────────────────────────────────────
                            price_gap = min_price - seller_price
                            combinations.append({
                                "combo":             new_applied,
                                "label":             combo_label,
                                "competitorCount":   n_products,
                                "minCompetitorPrice": min_price,
                                "sellerPrice":       seller_price,
                                "priceGap":          price_gap,
                                "isUntapped":        False,
                                "hasGolden":         True,
                                "status":            "WIN",
                                "competitors":       [],
                                "depth":             depth,
                                "totalInNiche":      total_in_niche,
                            })
                            progress_log.append(
                                f"  ✅ L1 WIN depth {depth}: gap ₹{price_gap:,} "
                                f"(min competitor ₹{min_price:,}, {n_products} products)"
                            )
                            # Still go deeper — more filters = more specific/defensible niche
                            if depth < max_depth:
                                explore(new_applied, depth + 1)

                        else:
                            progress_log.append(
                                f"  ✗ depth {depth}: min ₹{min_price:,} < ₹{seller_price:,} — going deeper"
                            )
                            if depth < max_depth:
                                explore(new_applied, depth + 1)

                    except Exception as e:
                        progress_log.append(f"  Error: {str(e)[:100]}")
                        continue

        progress_log.append(f"[Cascade] Exploring up to depth {max_depth}...")
        explore([], 1)

        # ── Score and sort: deepest first, then largest price gap ─────────────
        for c in combinations:
            if c["isUntapped"]:
                c["score"] = 1000 + c["depth"] * 10
            else:
                max_gap   = max(seller_price * 0.8, 1)
                gap_s     = min(c["priceGap"] / max_gap, 1) * 60
                scar_s    = max(1 - c["competitorCount"] / 10, 0) * 25
                depth_s   = c["depth"] * 5
                c["score"] = round(gap_s + scar_s + depth_s)

        # Filter to only requested depth range
        combinations = [c for c in combinations if c["depth"] >= min_depth]

        # Deepest first → within same depth, highest score first
        combinations.sort(key=lambda c: (c["depth"], c["score"]), reverse=True)

        summary = (
            f"[Done] {len(combinations)} L1 combos found "
            f"in {api_calls[0]} re-scrapes"
        )
        if truncated[0]:
            summary += f" (capped at {max_api_calls} calls)"
        progress_log.append(summary)

        return {
            "combinations":    combinations,
            "totalScraped":    api_calls[0],
            "progress":        progress_log,
            "truncated":       truncated[0],
            "goldenFilterCount": len(golden_filters),
        }

    # ── FAST PRICE SCRAPE (no enrichment) ────────────────────────────────────

    def _fast_price_scrape(self, url: str, extra_params: dict, location: str, seller_price: int = None) -> dict:
        """
        Fetches ALL category listing pages IN PARALLEL with retry.
        Returns the true minimum price across every product in the filtered result.
        No product detail page visits — prices only, ~10-50x faster than full scrape.
        """
        base_url = url.split("#")[0].split("?")[0]
        if not base_url.endswith("/search"):
            base_url = base_url.rstrip("/")

        extra_qs = ""
        if extra_params:
            filtered = {k: v for k, v in extra_params.items()
                        if k.lower() not in ("page", "format")}
            if filtered:
                extra_qs = "&" + urlencode(filtered)
        if location and location.lower() not in ("", "all india", "all"):
            extra_qs += "&localized_search=" + requests.utils.quote(location)

        # Step 1: page 1 — get total count
        page1_url = f"{base_url}?page=1&format=json{extra_qs}"
        try:
            text = self._fetch(page1_url).strip()
            if not text.startswith("{"):
                return {"min_price": None, "total": 0, "product_count": 0}
            data1 = json.loads(text)
        except Exception:
            return {"min_price": None, "total": 0, "product_count": 0}

        total         = data1.get("number_of_results", 0)
        catalogs1     = data1.get("catalogs", [])
        per_page      = max(len(catalogs1), 10)
        total_pages   = max(1, -(-total // per_page))
        total_pages   = min(total_pages, self.MAX_JSON_PAGES)

        all_prices = [int(c.get("final_price", {}).get("value", 0))
                      for c in catalogs1
                      if int(c.get("final_price", {}).get("value", 0)) > 0]

        # Early exit: if we already found a competitor cheaper than or equal to seller_price, we can't win
        if seller_price is not None and any(p <= seller_price for p in all_prices):
            return {
                "min_price":     min(all_prices) if all_prices else None,
                "total":         total,
                "product_count": len(all_prices),
            }

        if total_pages == 1:
            return {
                "min_price":     min(all_prices) if all_prices else None,
                "total":         total,
                "product_count": len(all_prices),
            }

        # Step 2: remaining pages in parallel with up to 3 retries per page
        def fetch_page(page: int) -> list:
            for attempt in range(5):
                try:
                    purl = f"{base_url}?page={page}&format=json{extra_qs}"
                    t = self._fetch(purl, retries=2).strip()
                    if not t.startswith("{"):
                        # Trigger retry if GeM sent HTML redirects or captcha
                        raise ValueError("Response is not JSON")
                    d = json.loads(t)
                    return [int(c.get("final_price", {}).get("value", 0))
                            for c in d.get("catalogs", [])
                            if int(c.get("final_price", {}).get("value", 0)) > 0]
                except Exception:
                    if attempt < 4:
                        time.sleep(2 * (attempt + 1))
            return []

        pages_left = list(range(2, total_pages + 1))
        # Lower workers to 8 for stability against GeM WAF
        with ThreadPoolExecutor(max_workers=min(8, len(pages_left))) as ex:
            futures = [ex.submit(fetch_page, pg) for pg in pages_left]
            for f in as_completed(futures):
                prices = f.result()
                all_prices.extend(prices)
                # Early exit loop inside ThreadPoolExecutor if a cheaper competitor is found
                if seller_price is not None and any(p <= seller_price for p in prices):
                    break

        return {
            "min_price":     min(all_prices) if all_prices else None,
            "total":         total,
            "product_count": len(all_prices),
        }

    # ── PRODUCT DETAIL PAGE ───────────────────────────────────────────────────

    def _scrape_product_page(self, url: str, variant_id: str) -> dict:
        """Extract product details (name, price, specs) from a product detail page."""
        html = self._fetch(url)
        soup = BeautifulSoup(html, "html.parser")

        name = ""
        h1 = soup.select_one("h1")
        if h1:
            name = h1.get_text(strip=True)
            name = re.sub(r'([A-Z\s]+)\1', r'\1', name).strip()

        price = 0
        for sel in [".final-price", ".offer_price", ".our_price"]:
            el = soup.select_one(sel)
            if el:
                price = self._parse_price(el.get_text(strip=True))
                if price:
                    break

        specs = self._extract_specs_from_page(soup)

        brand_el = soup.select_one(".brand-name")
        brand = brand_el.get_text(strip=True) if brand_el else ""

        seller = ""
        seller_el = soup.select_one(".seller-info")
        if seller_el:
            sold_as = seller_el.select_one("[class*='sold_as']")
            if sold_as:
                seller = sold_as.get_text(strip=True)

        return {
            "id": variant_id,
            "name": name[:150],
            "price": price,
            "specs": specs,
            "brand": brand,
            "seller": seller,
        }

    # ── FIND CATEGORY URL FROM PRODUCT PAGE ──────────────────────────────────

    def _find_category_url(self, product_url: str, catalog_id: str) -> str | None:
        """Given a product page URL, find the category listing URL."""
        html = self._fetch(product_url)
        soup = BeautifulSoup(html, "html.parser")

        title = soup.select_one("title")
        if title:
            title_text = title.get_text(strip=True)
            terms = re.sub(r'Buy\s+', '', title_text, flags=re.I)
            terms = re.sub(r'\s*\|.*$', '', terms)
            terms = re.sub(r'\s*,.*$', '', terms)
            brand_el = soup.select_one(".brand-name")
            if brand_el:
                brand = brand_el.get_text(strip=True)
                terms = terms.replace(brand, '').strip()
            terms = re.sub(r'\s+', ' ', terms).strip()
            words = [w for w in terms.split() if len(w) > 2][:4]
            search_q = '+'.join(words)

            search_url = f"https://mkp.gem.gov.in/search?q={search_q}&format=json"
            try:
                r = self._session.get(search_url, timeout=15)
                soup_search = BeautifulSoup(r.text, "html.parser")
                for a in soup_search.find_all("a", href=True):
                    href = a.get("href", "")
                    if "/search" in href and href != "/search":
                        full_url = href if href.startswith("http") else f"https://mkp.gem.gov.in{href}"
                        test_url = full_url.split("#")[0] + "?format=json"
                        try:
                            r2 = self._session.get(test_url, timeout=10)
                            text = r2.text.strip()
                            if text.startswith("{"):
                                data = json.loads(text)
                                for cat in data.get("catalogs", []):
                                    if catalog_id in str(cat.get("id", "")):
                                        return full_url.split("#")[0]
                        except Exception:
                            pass
            except Exception:
                pass

        return None

    # ── CATEGORY LISTING (JSON API) ──────────────────────────────────────────

    def _scrape_category_listing(self, url: str, extra_params: dict = None, location: str = "") -> dict:
        """
        Scrape ALL products in a GeM category using their JSON API.
        Strategy:
          1. Fetch page 1 to get total_results count + facets
          2. Fetch ALL remaining pages IN PARALLEL (20 workers, retry on failure)
          3. For each catalog item, try to extract specs from the listing JSON directly
             (most GeM categories include spec data inline — no product page visit needed)
          4. Only fall back to product-page enrichment for products where inline specs
             were missing golden-filter fields
        """
        base_url = url.split("#")[0].split("?")[0]
        if not base_url.endswith("/search"):
            base_url = base_url.rstrip("/")

        extra_qs = ""
        if extra_params:
            filtered = {k: v for k, v in extra_params.items()
                        if k.lower() not in ("page", "format")}
            if filtered:
                extra_qs = "&" + urlencode(filtered)
        if location and location.lower() not in ("", "all india", "all"):
            extra_qs += "&localized_search=" + requests.utils.quote(location)

        # ── Step 1: Page 1 — get total count + facets ────────────────────────
        page1_url = f"{base_url}?page=1&format=json{extra_qs}"
        text = self._fetch(page1_url).strip()
        if not text.startswith("{"):
            if extra_qs:
                # Fragment params may be client-side; retry bare
                extra_qs = ""
                page1_url = f"{base_url}?page=1&format=json"
                text = self._fetch(page1_url).strip()
            if not text.startswith("{"):
                return self._scrape_html_listing(url)

        try:
            data1 = json.loads(text)
        except json.JSONDecodeError:
            return self._scrape_html_listing(url)

        total_results = data1.get("number_of_results", 0)
        facet_defs    = self._extract_facet_defs(data1.get("facets", {}))
        catalogs1     = data1.get("catalogs", [])
        per_page      = max(len(catalogs1), 10)
        total_pages   = max(1, -(-total_results // per_page))  # ceiling div
        total_pages   = min(total_pages, self.MAX_JSON_PAGES)

        def parse_catalog(cat: dict) -> dict | None:
            price = int(cat.get("final_price", {}).get("value", 0))
            if price <= 0:
                return None
            product = {
                "id":         cat.get("id", ""),
                "name":       cat.get("title", ""),
                "price":      price,
                "brand":      cat.get("brand", ""),
                "seller":     cat.get("seller", {}).get("name", ""),
                "sellerType": cat.get("seller", {}).get("display_sold_as", ""),
                "rating":     cat.get("seller", {}).get("rating", ""),
                "listPrice":  int(cat.get("list_price", {}).get("value", 0)),
                "discount":   cat.get("discount_percent", 0),
                "imgUrl":     cat.get("img_url", ""),
                "productUrl": self._build_product_url(cat),
                "specs":      self._extract_inline_specs(cat),
            }
            return product

        all_products = [p for cat in catalogs1 if (p := parse_catalog(cat))]

        # ── Step 2: Remaining pages in parallel with retry ────────────────────
        def fetch_page(page: int) -> list:
            for attempt in range(5):
                try:
                    purl = f"{base_url}?page={page}&format=json{extra_qs}"
                    t = self._fetch(purl, retries=2).strip()
                    if not t.startswith("{"):
                        # GeM served HTML (likely a captcha or rate limit redirect), trigger retry loop
                        raise ValueError("Response received is not JSON")
                    d = json.loads(t)
                    return [p for cat in d.get("catalogs", []) if (p := parse_catalog(cat))]
                except Exception:
                    if attempt < 4:
                        time.sleep(2 * (attempt + 1)) # backoff
            return []

        if total_pages > 1:
            pages_left = list(range(2, total_pages + 1))
            # Use safer 8 workers instead of aggressive 20 to avoid WAF rate limits
            with ThreadPoolExecutor(max_workers=min(8, len(pages_left))) as ex:
                futures = [ex.submit(fetch_page, pg) for pg in pages_left]
                for f in as_completed(futures):
                    res = f.result()
                    if res:
                        all_products.extend(res)

        # ── Step 3: Enrich only products missing golden filter specs ──────────
        if all_products:
            all_products, all_filters = self._enrich_and_build_filters(
                all_products, facet_defs
            )
        else:
            all_filters = []

        return {
            "filters":      all_filters,
            "products":     all_products,
            "url":          url,
            "productCount": len(all_products),
            "filterCount":  len(all_filters),
            "totalResults": total_results,
            "location":     location or "All India",
        }

    def _build_product_url(self, catalog: dict) -> str:
        """Build a full product URL from catalog data."""
        url_parts = catalog.get("url", [])
        if url_parts and len(url_parts) >= 3:
            return f"https://mkp.gem.gov.in/{'/'.join(url_parts)}"
        return ""

    def _extract_inline_specs(self, cat: dict) -> dict:
        """
        Extract specs directly from the catalog listing JSON item.
        GeM embeds specs in multiple possible fields — try all of them.
        This avoids visiting individual product pages for most products.
        """
        specs = {}
        # Common keys GeM uses for inline specs
        for key in ("specifications", "product_specifications", "spec_params",
                    "params", "attributes", "properties", "features"):
            items = cat.get(key, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        # Try all naming patterns GeM uses
                        name  = (item.get("name") or item.get("key") or
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

    def _extract_facet_defs(self, facets: dict) -> list:
        """
        Extract facet definitions — and their values — from the JSON response.
        GeM sometimes includes facet_values/topValues directly in the facet object.
        When present, we can skip product-page enrichment for those filters entirely.
        """
        defs = []

        def _pull_values(facet: dict) -> list:
            """Try to read filter values directly from the facet API response."""
            for key in ("facet_values", "topValues", "top_values", "values",
                        "entries", "options", "items", "terms"):
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

        spec_facets = facets.get("product specifications", {}).get("facet_list", [])
        for facet in spec_facets:
            name      = facet.get("name", "")
            code      = facet.get("code", "")
            css_class = facet.get("css_class", "")
            if len(name) > 80:
                continue
            defs.append({
                "filterName":  name,
                "filterKey":   code,
                "isGolden":    css_class == "golden",
                "type":        facet.get("type", ""),
                "facetValues": _pull_values(facet),  # values from API (may be [])
            })

        admin_facets = facets.get("administrative", {}).get("facet_list", [])
        for facet in admin_facets:
            name  = facet.get("name", "")
            code  = facet.get("code", "")
            name_lower = name.lower()
            is_golden = any(k in name_lower for k in
                            ("make in india", "mse", "startup", "pac"))
            if is_golden or name in ("Make in India", "Lead Time for Dispatch"):
                defs.append({
                    "filterName":  name,
                    "filterKey":   code,
                    "isGolden":    is_golden,
                    "type":        facet.get("type", ""),
                    "facetValues": _pull_values(facet),
                })

        return defs

    def _extract_specs_from_page(self, soup: BeautifulSoup) -> dict:
        """
        Extract all specifications from a product detail page.
        Specs are in tables inside #feature_groups, with td key-value pairs.
        """
        specs = {}

        feature_groups = soup.select_one("#feature_groups")
        if feature_groups:
            for table in feature_groups.find_all("table"):
                for row in table.find_all("tr"):
                    cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                    if len(cells) >= 2 and cells[0] and cells[1]:
                        name = cells[0].strip()
                        value = cells[1].strip()
                        if name and value and len(value) < 200:
                            specs[name] = value

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

    def _enrich_single_product(self, product: dict, name_to_code: dict) -> dict:
        """Fetch specs for a single product (used by thread pool)."""
        url = product.get("productUrl")
        if not url:
            return product
        if url in self._product_specs_cache:
            product["specs"] = self._product_specs_cache[url]
            return product
        try:
            html = self._fetch(url)
            soup = BeautifulSoup(html, "html.parser")
            raw_specs = self._extract_specs_from_page(soup)

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

            self._product_specs_cache[url] = matched_specs
            product["specs"] = matched_specs
        except Exception:
            pass
        return product

    def _enrich_and_build_filters(self, products: list, facet_defs: list) -> tuple:
        """
        Build filter values from product specs.

        Strategy (fastest-first cascade):
        1. Use facetValues from the API response directly (zero extra requests)
        2. Use inline specs already extracted from the listing JSON
        3. Only visit product detail pages for golden filters STILL missing values
           — prioritise cheapest products (most relevant for L1 analysis)
        """
        name_to_code = {fd["filterName"]: fd["filterKey"] for fd in facet_defs}

        # ── Level 1: values from facet API ───────────────────────────────────
        filter_values: dict[str, set] = {}
        facet_api_covered: set[str] = set()  # codes covered by API values
        for fd in facet_defs:
            api_vals = fd.get("facetValues", [])
            if api_vals:
                filter_values[fd["filterKey"]] = set(api_vals)
                facet_api_covered.add(fd["filterKey"])

        # ── Level 2: inline specs already in each catalog item ────────────────
        for product in products:
            for spec_name, spec_value in product.get("specs", {}).items():
                if not spec_value or len(spec_value) > 150:
                    continue
                code = name_to_code.get(spec_name)
                if not code:
                    for fname, fcode in name_to_code.items():
                        if self._names_match(spec_name, fname):
                            code = fcode
                            break
                if code:
                    filter_values.setdefault(code, set()).add(spec_value)

        # ── Level 3: product-page enrichment for STILL-missing golden filters ─
        golden_codes_missing = {
            fd["filterKey"] for fd in facet_defs
            if fd.get("isGolden")
            and fd["filterKey"] not in filter_values
        }

        if golden_codes_missing:
            # Sort cheapest first — if we find values early, we stop sooner
            products_sorted = sorted(products, key=lambda p: p["price"])
            to_enrich = products_sorted[:self.MAX_ENRICH]

            with ThreadPoolExecutor(max_workers=self.ENRICH_WORKERS) as executor:
                futures = {
                    executor.submit(self._enrich_single_product, p, name_to_code): p
                    for p in to_enrich
                }
                for future in as_completed(futures):
                    try:
                        product = future.result()
                        for code in name_to_code.values():
                            val = product["specs"].get(code)
                            if val:
                                filter_values.setdefault(code, set()).add(val)
                    except Exception:
                        pass
                    # Early stop: if all golden filters now have values, done
                    if not (golden_codes_missing - filter_values.keys()):
                        break

        # ── Build final filter list ───────────────────────────────────────────
        golden_filters = []
        non_golden_filters = []
        for fd in facet_defs:
            code = fd["filterKey"]
            vals = sorted(filter_values.get(code, set()))
            if not vals:
                continue
            entry = {
                "filterName": fd["filterName"],
                "filterKey":  code,
                "values":     vals[:20],
                "isGolden":   fd.get("isGolden", False),
                "type":       fd.get("type", ""),
            }
            if fd.get("isGolden", False):
                golden_filters.append(entry)
            else:
                non_golden_filters.append(entry)

        # Always return ALL golden filters (never cap them) — they are used for deep search
        golden_filters.sort(key=lambda f: (-len(f["values"]), f["filterName"]))
        # Cap non-golden filters for display only
        non_golden_filters.sort(key=lambda f: (-len(f["values"]), f["filterName"]))
        filters = golden_filters + non_golden_filters[:self.MAX_FILTERS]
        return products, filters


    # ── HTML FALLBACK ────────────────────────────────────────────────────────

    def _scrape_html_listing(self, url: str) -> dict:
        error_msg = "This category URL is invalid, empty, or doesn't support the JSON API. Please search on GeM and select a valid category."
        
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if path == "search":
            error_msg = "You entered a Global Search URL. Please click on a specific Category on the left sidebar in GeM, then copy that URL."

        return {
            "filters": [],
            "products": [],
            "url": url,
            "productCount": 0,
            "filterCount": 0,
            "error": error_msg,
        }

    # ── HTTP ────────────────────────────────────────────────────────────────

    def _fetch(self, url: str, retries: int = 3) -> str:
        last_err = None
        for attempt in range(retries):
            try:
                # Wait for our slot in the global concurrency queue before fetching
                with GeMScraper._HTTP_SEMAPHORE:
                    resp = self._session.get(url, timeout=20, allow_redirects=True)
                resp.raise_for_status()
                
                # Check if GeM redirected us to the homepage or login page due to missing session
                if "mkp.gem.gov.in" in resp.url and (resp.url.strip("/") == "https://mkp.gem.gov.in" or "login" in resp.url.lower()):
                    if attempt < retries - 1:
                        self._initialize_session()
                        continue
                        
                return resp.text
            except requests.RequestException as e:
                last_err = e
                if attempt < retries - 1:
                    time.sleep(1 * (attempt + 1))
        raise RuntimeError(f"Failed to fetch page after {retries} attempts: {last_err}")

    # ── HELPERS ─────────────────────────────────────────────────────────────

    def _names_match(self, name1: str, name2: str) -> bool:
        """Check if two spec/filter names are equivalent."""
        n1 = name1.lower().strip().replace("::", "/")
        n2 = name2.lower().strip().replace("::", "/")
        if n1 == n2:
            return True
        k1 = re.sub(r'[^a-z0-9]', '', n1)
        k2 = re.sub(r'[^a-z0-9]', '', n2)
        return k1 == k2 and len(k1) > 5

    def _parse_price(self, text: str) -> int | None:
        cleaned = re.sub(r'[₹,\s]', '', text)
        cleaned = re.sub(r'(?i)INR|Rs\.?', '', cleaned)
        m = re.search(r'(\d+(?:\.\d+)?)', cleaned)
        if m:
            val = float(m.group(1))
            if 10 <= val <= 10_000_000:
                return int(val)
        return None

    def _to_key(self, name: str) -> str:
        key = re.sub(r'[^a-z0-9\s]', '', name.lower().strip())
        return re.sub(r'\s+', '_', key).strip('_')[:40]
