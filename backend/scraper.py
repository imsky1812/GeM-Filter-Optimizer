"""
GeMScraper — scrapes GeM marketplace using their internal JSON API.
Supports both product detail page URLs and category listing URLs.
No browser needed — uses requests + BeautifulSoup.
"""
import re
import json
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urlencode, urldefrag


class GeMScraper:

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

    # Configuration
    MAX_JSON_PAGES = 50          # Fetch up to 50 pages (600 products)
    MAX_ENRICH = 150             # Enrich up to 150 products with full specs
    ENRICH_WORKERS = 10          # Parallel workers for spec fetching
    MAX_FILTERS = 15             # Max filters to return

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update(self.HEADERS)
        
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

    def scrape(self, url: str) -> dict:
        """
        Main entry point. Accepts either:
          - A product page URL (p-XXXXX-YYYYY-cat.html)
          - A category/search URL (including fragment-based query URLs)
        Returns {filters, products, url, productCount, filterCount, yourProduct}
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
                    "error": "Could not determine the category listing. Try using a category search URL instead.",
                }

        result = self._scrape_category_listing(url, extra_params)
        result["yourProduct"] = your_product
        return result

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

    def _scrape_category_listing(self, url: str, extra_params: dict = None) -> dict:
        """
        Scrape a GeM category listing page using the JSON API.
        Fetches ALL pages to get every product in the category.
        extra_params: additional query params extracted from fragment-based URLs.
        """
        base_url = url.split("#")[0].split("?")[0]
        if not base_url.endswith("/search"):
            base_url = base_url.rstrip("/")

        # Build extra query string from fragment params (excluding page/format)
        extra_qs = ""
        if extra_params:
            filtered = {k: v for k, v in extra_params.items()
                        if k.lower() not in ("page", "format")}
            if filtered:
                extra_qs = "&" + urlencode(filtered)

        all_products = []
        facet_defs = []
        total_results = 0

        # Fetch ALL pages from the JSON API (12 products per page)
        for page in range(1, self.MAX_JSON_PAGES + 1):
            if page > 1:
                time.sleep(0.2)
            json_url = f"{base_url}?page={page}&format=json{extra_qs}"
            try:
                text = self._fetch(json_url)
                text = text.strip()
                if not text.startswith("{"):
                    if page == 1 and extra_qs:
                        # Fragment params (like q=) may be client-side only;
                        # retry without them before giving up
                        extra_qs = ""
                        json_url = f"{base_url}?page=1&format=json"
                        text = self._fetch(json_url).strip()
                        if not text.startswith("{"):
                            return self._scrape_html_listing(url)
                    elif page == 1:
                        return self._scrape_html_listing(url)
                    else:
                        break

                data = json.loads(text)
                total_results = data.get("number_of_results", 0)

                catalogs = data.get("catalogs", [])
                for cat in catalogs:
                    product = {
                        "id": cat.get("id", ""),
                        "name": cat.get("title", ""),
                        "price": int(cat.get("final_price", {}).get("value", 0)),
                        "brand": cat.get("brand", ""),
                        "seller": cat.get("seller", {}).get("name", ""),
                        "sellerType": cat.get("seller", {}).get("display_sold_as", ""),
                        "rating": cat.get("seller", {}).get("rating", ""),
                        "listPrice": int(cat.get("list_price", {}).get("value", 0)),
                        "discount": cat.get("discount_percent", 0),
                        "imgUrl": cat.get("img_url", ""),
                        "productUrl": self._build_product_url(cat),
                        "specs": {},
                    }
                    if product["price"] > 0:
                        all_products.append(product)

                if page == 1:
                    facet_defs = self._extract_facet_defs(data.get("facets", {}))

                # Stop if we got fewer products than a full page (no more data)
                if len(catalogs) < 10:
                    break

            except (json.JSONDecodeError, requests.RequestException) as e:
                if page == 1:
                    raise RuntimeError(f"Failed to parse category listing: {e}")
                break

        # Enrich products with specs from their detail pages (parallel)
        if all_products:
            all_products, all_filters = self._enrich_and_build_filters(
                all_products, facet_defs
            )
        else:
            all_filters = []

        return {
            "filters": all_filters,
            "products": all_products,
            "url": url,
            "productCount": len(all_products),
            "filterCount": len(all_filters),
            "totalResults": total_results,
        }

    def _build_product_url(self, catalog: dict) -> str:
        """Build a full product URL from catalog data."""
        url_parts = catalog.get("url", [])
        if url_parts and len(url_parts) >= 3:
            return f"https://mkp.gem.gov.in/{'/'.join(url_parts)}"
        return ""

    def _extract_facet_defs(self, facets: dict) -> list:
        """Extract facet definitions from the JSON response."""
        defs = []

        spec_facets = facets.get("product specifications", {}).get("facet_list", [])
        for facet in spec_facets:
            name = facet.get("name", "")
            code = facet.get("code", "")
            css_class = facet.get("css_class", "")
            if len(name) > 80:
                continue
            defs.append({
                "filterName": name,
                "filterKey": code,
                "isGolden": css_class == "golden",
                "type": facet.get("type", ""),
            })

        admin_facets = facets.get("administrative", {}).get("facet_list", [])
        for facet in admin_facets:
            name = facet.get("name", "")
            code = facet.get("code", "")
            if name in ("Make in India", "Lead Time for Dispatch"):
                defs.append({
                    "filterName": name,
                    "filterKey": code,
                    "isGolden": False,
                    "type": facet.get("type", ""),
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
        if not product.get("productUrl"):
            return product
        try:
            html = self._fetch(product["productUrl"])
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

            product["specs"] = matched_specs
        except Exception:
            pass
        return product

    def _enrich_and_build_filters(self, products: list, facet_defs: list) -> tuple:
        """
        Fetch product detail pages IN PARALLEL to extract specifications.
        Then build filter values from the collected specs.
        Returns (all_products_with_specs, filters)
        """
        name_to_code = {}
        for fd in facet_defs:
            name_to_code[fd["filterName"]] = fd["filterKey"]

        # Select products to enrich — spread across price range for coverage
        # Sort by price and sample evenly to cover cheap, mid, and expensive
        products_sorted = sorted(products, key=lambda p: p["price"])
        total = len(products_sorted)
        enrich_count = min(self.MAX_ENRICH, total)

        if enrich_count < total:
            # Evenly sample across price range
            step = total / enrich_count
            indices = [int(i * step) for i in range(enrich_count)]
            to_enrich = [products_sorted[i] for i in indices]
        else:
            to_enrich = products_sorted

        # Parallel spec fetching
        filter_values = {}

        with ThreadPoolExecutor(max_workers=self.ENRICH_WORKERS) as executor:
            futures = {
                executor.submit(self._enrich_single_product, p, name_to_code): p
                for p in to_enrich
            }
            for future in as_completed(futures):
                try:
                    product = future.result()
                    # Collect filter values from specs
                    for code in name_to_code.values():
                        val = product["specs"].get(code)
                        if val:
                            filter_values.setdefault(code, set()).add(val)
                except Exception:
                    pass

        # Build final filter list with actual values from products
        filters = []
        for fd in facet_defs:
            code = fd["filterKey"]
            vals = sorted(filter_values.get(code, set()))
            if not vals or len(vals) < 2:
                continue
            if len(vals) > 20:
                vals = vals[:20]

            filters.append({
                "filterName": fd["filterName"],
                "filterKey": code,
                "values": vals,
                "isGolden": fd.get("isGolden", False),
                "type": fd.get("type", ""),
            })

        filters.sort(key=lambda f: (not f.get("isGolden", False), -len(f["values"]), f["filterName"]))

        return products, filters[:self.MAX_FILTERS]

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
