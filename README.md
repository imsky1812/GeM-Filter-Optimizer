# 🚀 GeM Filter Optimizer — Enterprise Edition

[![License](https://img.shields.io/badge/License-Commercial-blue.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React%2018-61DAFB.svg)](https://reactjs.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)

**Secure the L1 Winning Slot effortlessly. Automated market intelligence to dominate Government e-Marketplace (GeM) listings.**

---

## 🎯 Overview

**GeM Filter Optimizer** is a high-performance full-stack business intelligence engine designed to help GeM vendors maximize their sales ranking. By analyzing competitor taxonomy and processing real-time market payloads, it accurately surfaces specific combinations of "Golden Filters" that position your pricing as the undisputed **lowest valid price (L1)**.

Stop manually checking thousands of permutations. Apply dynamic data science to your sales operation.

## 💎 Key Features

- 🕷️ **High-Volume Scaled Scraper**: Effortlessly ingest entire categories (10,000+ pages) via asynchronous multi-threaded payload fetching.
- 🎯 **Surgical Competitive Strike**: **New!** Paste any specific competitor's URL to analyze their specs. Instantly find a "Killer Filter" to **eliminate** cheaper competitors or a "Blueprint" to **join and undercut** high-priced premium niches.
- 🧠 **Deep & Ultra-Deep Cascade (Levels 3-15)**: Proprietary recursion tree traversal uncovers non-obvious, deeply nested niches. Standard search covers depth 3-10, while Ultra-Deep mode pushes to depth 15 for extreme market isolation.
- 🛡️ **Anti-Throttling Core**: Self-healing query engine with linear retry back-off and dynamic concurrency management safeguards against portal firewalls and WAF limiters.
- ⚡ **Ultra-Low Latency API**: Backend with integrated **GZip compression** and smart caching minimizes payload transit size for sub-second interactions.
- 📊 **Interactive Visualization**: Advanced React plotting for distribution density, pricing spectrums, and competitor opportunity matrices.
- 📜 **Instant PDF Strategy Report**: Generate formatted, print-ready executive summaries that isolate exact actionable settings for product management teams.

---

## 📁 Technical Architecture

```
GeM-Filter-Optimizer/
├── Dockerfile                 # Multistage Production Image Builder
├── docker-compose.yml         # Single-command deployment orchestrator
├── run_production.bat         # Retail Installer for Non-Technical Clients
├── backend/
│   ├── main.py                # FastAPI entry point, route definitions, static mounting
│   ├── crawler.py             # Playwright-backed BrowserManager + GeMCrawler (category/product fetch)
│   ├── scraper.py             # GeMScraper facade — JSON-API-first scraping, HTML fallback
│   ├── chain_hunt.py          # Sequential L1 Chain Hunt: in-memory BFS set-cover search + live verification
│   ├── l1_surpasser.py        # Surgical Strike: single-competitor golden-filter counter analysis
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
- [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn — async API server
- [Playwright](https://playwright.dev/python/) (Chromium, headless) — the actual fetch layer; GeM's WAF blocks plain `requests` calls, so every scrape/verify goes through a real browser context, managed by a single long-lived `BrowserManager` (dedicated asyncio event loop, page pool, cookie refresh)
- BeautifulSoup4 + lxml — HTML fallback parsing when the JSON API path fails
- Pydantic — request/response models

**Frontend**
- React 18 + Vite 5 — no framework beyond that (no Redux/Zustand; wizard state lives in `App.jsx`)
- Plain CSS with a token system (`index.css`) — no Tailwind/CSS-in-JS; theme switching via a `data-theme` attribute on `:root`
- [@phosphor-icons/react](https://phosphoricons.com/) — icon set (replaced all emoji-as-icon usage)
- Google Fonts: **Space Grotesk** (display/headings) + **Inter** (body/data)
- Recharts — pricing/distribution charts
- jsPDF + jspdf-autotable — exportable strategy report

---

## 🚀 Deployment Scenarios

### Scenario A: Automated Local Launch (Windows)
Perfect for retail/sales users who lack programming experience.
1. Download/Clone this repository.
2. Double-click **`run_production.bat`**.
3. The script will automatically handle node installation, python virtual environments, and launch the secured interface at `http://localhost:8000`.

### Scenario B: Universal Docker (Recommended for Production)
Ideal for running on private Cloud servers, VPS, AWS, or locally via Docker Desktop.
```bash
# Launch complete stack in isolated environment
docker-compose up --build -d
```
*The application will be hosted globally on port `:8000` with static rendering enabled.*

### Scenario C: Standard Dev Setup
```bash
# Terminal 1: Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Terminal 2: Frontend 
cd frontend
npm install
npm run dev
```

---

## 🔌 Advanced Configuration

### Environment Bindings
By default, the backend serves unified traffic. For distributed architecture, you can configure explicit routing:
- **Frontend Build Direct**: `VITE_API_BASE_URL=/api`
- **Backend Host Bind**: `0.0.0.0` (Internal container orchestration)

### Logging & Diagnostics
Production server utilizes integrated **FastAPI structured logging** for health auditing and real-time diagnostic visibility. Access OpenAPI documentation on deployment at `/api/docs`.

---

## 🗓️ Recent Updates

**Backend**
- **Fixed a silent failure that made "no path found" untrustworthy.** GeM's WAF sometimes rejects a live-verification request outright (a "Request Rejected" block page). `crawler.py` was treating that unparseable response identically to a genuine zero-result answer, so blocked requests silently reported as valid data — the chain-hunt's own "is this a fake mismatch" guard then discarded real (verified-locally) niches because the "live" side was actually just a swallowed failure. Fixed: unparseable responses now flag `error: True` and log the actual response body, so a blocked request can no longer masquerade as a computed answer.
- **Reduced chain-hunt verification concurrency.** The verification step was firing up to 8 filtered-price requests at GeM in a tight burst — exactly the pattern that trips WAF bot-detection. Dropped to 2 concurrent requests with a staggered submission delay (`chain_hunt.py`).

**Frontend — full visual identity pass**
- **Color/consistency fixes**: three different colors (indigo, amber, red) were each doing double duty as both a CTA color and a semantic state color; consolidated to one clear system.
- **Dark mode**: black-first by default, toggle to light, persisted via `localStorage`. Full token-driven theme (surfaces, ink, accents, shadows) — no component-level color overrides needed.
- **Brand identity**: switched accent to red, added Space Grotesk for display type, an ambient background glow + grain texture, bolder hero typography.
- **Icons**: replaced every emoji-as-icon instance across all components with Phosphor icons.
- **Motion**: press feedback on every interactive element, hover lifts, staggered list/chip/timeline reveals, and a real celebration (bounce, glow, confetti) on an actual L1 win.
- **Copy pass**: tightened UI text throughout for a more confident, declarative voice; removed em dashes from all user-facing strings.
- **Layout**: wider container on the Results step to fit denser content (stat tiles, timeline, competitor cards).

---

## ⚖️ Legal & Licensing
This software serves as a competitive analysis instrument. The software leverages publicly accessible, unauthenticated JSON data feeds provided by the destination web resources for information synthesis purposes only. User assumes adherence to target domain guidelines. 

***

**Built for Scale. Created for Results.** 📈
