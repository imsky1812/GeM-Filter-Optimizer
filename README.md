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
- 🧠 **Deep Cascade Logic (Levels 3-10)**: Proprietary recursion tree traversal uncovers non-obvious, deeply nested niches where major brands are excluded.
- 🛡️ **Anti-Throttling Core**: Self-healing query engine with linear retry back-off safeguards against portal firewalls and WAF limiters.
- ⚡ **Ultra-Low Latency API**: Backend with integrated **GZip compression** middleware minimizes payload transit size for sub-second interactions.
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
│   ├── main.py                # API entry & monolithic Static Web mounting
│   ├── scraper.py             # Advanced concurrent recursion engine
│   └── requirements.txt       
└── frontend/
    ├── src/
    │   ├── App.jsx            # Analysis intelligence core
    │   └── index.css          # Premium dark glassmorphism styles
    └── vite.config.js         
```

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

## ⚖️ Legal & Licensing
This software serves as a competitive analysis instrument. The software leverages publicly accessible, unauthenticated JSON data feeds provided by the destination web resources for information synthesis purposes only. User assumes adherence to target domain guidelines. 

***

**Built for Scale. Created for Results.** 📈
