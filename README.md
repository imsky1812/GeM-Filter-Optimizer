# 🚀 GeM Filter Optimizer

[![License](https://img.shields.io/badge/License-Commercial-blue.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React%2018-61DAFB.svg)](https://reactjs.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)

**Find the filter combinations that make your listing the cheapest one buyers see on the Government e-Marketplace (GeM).**

---

## 🎯 Overview

GeM ranks listings by price within a filtered set of specifications. Pick the right combination of "golden filters" and your price becomes the lowest valid one (**L1**) in that niche.

This tool scans a GeM category, searches combinations of its golden filters in memory, then verifies the best candidates against GeM live, so the paths it reports are checked rather than guessed.

## 💎 What it does

- 🕷️ **Category scan** — pulls products and golden filters through GeM's JSON API. Samples up to 50 pages per category (measured: 600 products out of a 47,000-product category in ~20 s).
- 🧠 **Chain hunt** — breadth-first search over golden-filter combinations up to 4 deep in memory, then live verification of the top candidates. Reports `WIN`, `PARTIAL` or `STUCK`, with the best achievable price floor (measured: ~25–30 s, 60–75 requests).
- 🎯 **Surgical strike** — paste a competitor's listing URL. It reads their specs, matches them to golden filters, and live-tests counter-values that would exclude them. Read *Known limitations* before acting on its "untapped" results.
- 🔍 **Unconfirmed leads** — GeM's search index rejects some literal filter values, multi-word text facets in particular. Rather than silently dropping those paths, the chain hunt surfaces them separately for manual checking.
- 🛡️ **WAF-aware fetching** — one long-lived headless Chromium, at most 8 pages in flight, retries with backoff, staggered verification requests, and a cookie refresh when GeM expires the session.
- ⚡ **GZip responses and a 30-minute scrape cache**, bounded at 100 entries.

---

## 📁 Technical Architecture

```
GeM-Filter-Optimizer/
├── Dockerfile                 # Multistage production image (frontend build + backend + Chromium)
├── docker-compose.yml         # Single-command deployment
├── run_production.bat         # Windows launcher for non-technical users
├── backend/
│   ├── main.py                # FastAPI entry point, routes, URL validation, static mounting
│   ├── crawler.py             # BrowserManager (shared async Playwright) + GeMCrawler
│   ├── scraper.py             # GeMScraper: surgical strike + the chain hunt's fetch/enrich helpers
│   ├── chain_hunt.py          # In-memory BFS set-cover search + live verification
│   ├── l1_surpasser.py        # Standalone sequential L1 elimination engine (CLI + /api/l1-surpass)
│   ├── gem_utils.py           # Shared helpers: name matching, price/URL/spec parsing, seller ids
│   ├── test_*.py              # Regression tests (run with pytest, or each file as a script)
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── App.jsx             # Wizard state machine (Category → Price → Analysis → Results)
    │   ├── components/         # UrlInput, PriceInput, ToolChoice, ChainHuntResults, SurgicalStrike,
    │   │                       # CompetitorSpecsModal, Header, StepIndicator
    │   └── index.css           # Design tokens, dark/light theme, motion, layout
    └── vite.config.js
```

---

## 🛠️ Tech Stack

**Backend**
- [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn — API server
- [Playwright](https://playwright.dev/python/) (Chromium, headless) — the actual fetch layer; GeM's WAF blocks plain HTTP clients, so every scrape and verification goes through a real browser context, managed by a single long-lived `BrowserManager` (dedicated asyncio event loop, page pool, cookie refresh)
- BeautifulSoup4 + lxml — product-page spec parsing, and HTML fallback parsing when the JSON path fails
- Pydantic — request/response models

**Frontend**
- React 18 + Vite 5 — no state library; wizard state lives in `App.jsx`
- Plain CSS with a token system (`index.css`); theme switching via a `data-theme` attribute on `:root`
- [@phosphor-icons/react](https://phosphoricons.com/) — icon set
- Google Fonts: **Space Grotesk** (display/headings) + **Inter** (body/data)

---

## 🚀 Deployment Scenarios

### Scenario A: Automated Local Launch (Windows)
1. Download or clone this repository.
2. Double-click **`run_production.bat`**.
3. It builds the frontend, creates a Python virtual environment, installs dependencies **and headless Chromium**, then serves the app at `http://localhost:8000`.

### Scenario B: Universal Docker (recommended for production)
```bash
docker-compose up --build -d
```
The image installs Chromium during the build and serves the app on port `:8000`.

Run **one worker**. Each worker process starts its own Chromium, its own cache and its own 8-request budget against GeM, so extra workers multiply memory use and the request bursts GeM's WAF blocks.

### Scenario C: Standard Dev Setup
```bash
# Terminal 1: Backend
cd backend
pip install -r requirements.txt
playwright install chromium        # one-time: Playwright ships no browser itself
uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm install
npm run dev
```

### Tests
```bash
cd backend
python -m pytest -q                # or run a single file: python test_error_fixes.py
```

---

## 🔌 API

All routes live under `/api`, documented at `/api/docs`.

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Service status and whether the browser is alive |
| GET | `/locations` | States/UTs for delivery-location filtering |
| POST | `/scrape` | Scan a category: products + golden filters |
| POST | `/chain-hunt` | Find and live-verify filter paths to L1 |
| POST | `/surgical-strike` | Counter-filters against one competitor listing |
| POST | `/product-specs` | Live specs for a single product |
| POST | `/l1-surpass` | Standalone sequential elimination engine (not used by the UI) |
| DELETE | `/cache` | Clear the scrape cache |

Every URL these endpoints accept is opened by the server's own browser, so only GeM hosts (`gem.gov.in`, `mkp.gem.gov.in`, `mkp.gemorion.org`) are allowed.

---

## 🔌 Advanced Configuration

### Environment
- The frontend always calls the API at the relative path `/api` (Vite proxies it to `:8000` in dev), so no build-time API URL is needed.
- `ALLOWED_ORIGINS` — comma-separated origins for cross-origin API access. Unset, the default, means same-origin only.
- **Backend host bind**: `0.0.0.0` for container orchestration.

### Logging & Diagnostics
The server logs each fetch, verification and WAF-blocked response, so a "no path found" result can be traced back to real data rather than a swallowed failure.

---

## ⚠️ Known limitations

- **"Untapped niche" in the surgical strike is unreliable.** GeM's index rejects some literal filter values, returning zero results for a niche that genuinely has products. Verified: 168 of 244 printers in one category are monochrome, yet querying that value live returns 0. The chain hunt guards against this by marking such paths *unconfirmed*; the surgical strike does not yet.
- **Category URLs must be canonical.** Short links from GeM's homepage (e.g. `/computer-printer-0901print/search`) are aliases that serve the single-page app instead of JSON, and the scan returns 422. Use the long canonical category URL.
- **The search works from a sample, not the whole category.** The scan reads up to 50 pages and the chain hunt up to 20, plus a few price-descending pages, so on very large categories the in-memory stage sees a slice. Live verification is what confirms any reported path.
- **`/l1-surpass` has never completed a real end-to-end run** and no part of the UI calls it. Treat it as unverified.

---

## 🗓️ Recent Updates

- **Corrected scraped text.** JSON was being read from the rendered DOM, which HTML-escaped `&`, `<` and `>` — a seller like `L & P INTERNATIONAL` arrived as `L &amp; P`. Fetches now read the raw response body.
- **Fixed seller counts.** GeM's catalog JSON has no `seller.id`; it carries `external_ref_id`. Reading the wrong field left every seller count at 0, which downgraded genuine chain-hunt wins to `PARTIAL` and made every L1 candidate look like it had too few sellers.
- **Hardened the endpoints.** Every URL-accepting route validates that the target is a GeM host, Chromium no longer runs with web security disabled, and cross-origin access is off unless configured.
- **Fixed deployment.** Docker and the Windows launcher install Chromium, without which every scrape failed on a fresh machine, and both run a single worker.
- **Correctness fixes.** Filter values are compared case-insensitively when scoring paths; failed price checks are no longer reported as untapped niches; a fetch that exhausts its retries returns a result instead of HTTP 500.
- **Performance.** Counter-filter checks read one price-sorted page instead of walking the category; the L1 surpasser fetches pages in concurrent batches; spec-name matching is memoized; Chromium warms up at startup.
- **Cleanup.** Helpers duplicated across three modules moved into `gem_utils.py`, roughly 1,100 lines of dead code removed, unused frontend dependencies dropped, and backend dependencies pinned.

---

## ⚖️ Legal & Licensing
This software is a competitive analysis instrument. It reads publicly accessible, unauthenticated data feeds published by the destination web resources for information synthesis only. The user assumes adherence to target domain guidelines.

***

**Built for Scale. Created for Results.** 📈
