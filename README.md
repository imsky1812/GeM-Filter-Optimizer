# 🏆 GeM Filter Optimizer

**Find the exact filters that make your product rank #1 (L1) on the Government e-Marketplace (GeM).**

GeM Filter Optimizer is a full-stack intelligence tool built for GeM sellers. It scrapes real product listings from any GeM category, analyzes every possible filter combination, and instantly tells you which filters to apply on your listing so that buyers always see your product as the **cheapest (L1)** in that filtered view.

---

## 🎯 The Problem

On GeM, buyers filter products by specifications like brand, material, capacity, etc. Your product might not be the overall cheapest, but it **could be the cheapest within specific filter combinations**. Manually checking hundreds of filter permutations is impossible — this tool automates it.

## 💡 How It Works

1. **Paste** a GeM category URL (e.g., `https://mkp.gem.gov.in/{category}/search`)
2. **Scrape** — the backend fetches all products and their specs via GeM's internal JSON API
3. **Enter your price** — the tool instantly finds every filter combination where your price beats all competitors
4. **Apply the filters** on your GeM seller dashboard and rank L1!

---

## 🖥️ Tech Stack

| Layer      | Technology                        |
|------------|-----------------------------------|
| Frontend   | React 18, Vite, Recharts          |
| Backend    | Python, FastAPI, Uvicorn          |
| Scraping   | Requests, BeautifulSoup4          |
| Styling    | Custom CSS (dark theme)           |

---

## 📁 Project Structure

```
gem-filter-optimizer/
│
├── frontend/                    # React web app (Vite)
│   ├── src/
│   │   ├── App.jsx              # Main application component (UI + analysis engine)
│   │   ├── index.css            # All styles (dark theme)
│   │   └── main.jsx             # React DOM entry point
│   ├── index.html               # HTML shell
│   ├── package.json             # Node dependencies
│   └── vite.config.js           # Vite dev server config (proxies to backend)
│
├── backend/                     # Python FastAPI server
│   ├── main.py                  # API routes (/scrape, /analyze, /cache)
│   ├── scraper.py               # GeM scraper (requests + BeautifulSoup)
│   ├── requirements.txt         # Python dependencies
│   └── __init__.py
│
├── docs/
│   └── GeM_Filter_Optimizer_Spec.docx
│
├── .gitignore
├── SETUP.txt                    # Quick setup guide
└── README.md                    # This file
```

---

## 🚀 Quick Start

### Prerequisites

- **Node.js 18+** — [Download](https://nodejs.org)
- **Python 3.11+** — [Download](https://python.org/downloads)

### 1. Clone the repository

```bash
git clone https://github.com/imsky1812/GeM-Filter-Optimizer.git
cd GeM-Filter-Optimizer
```

### 2. Start the Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Open the app

Navigate to **http://localhost:3000** in your browser.

---

## 🔌 API Endpoints

| Method   | Endpoint   | Description                              |
|----------|------------|------------------------------------------|
| `GET`    | `/`        | Health check                             |
| `POST`   | `/scrape`  | Scrape a GeM URL → returns products + filters |
| `POST`   | `/analyze` | Analyze filter opportunities             |
| `DELETE` | `/cache`   | Clear the 30-min scrape cache            |

Swagger docs available at: `http://localhost:8000/docs`

---

## 📖 Usage Guide

1. **Find a category on GeM** — Go to [mkp.gem.gov.in](https://mkp.gem.gov.in), search for your product category, and click on the specific sub-category from the left sidebar.

2. **Copy the URL** — It will look like:
   ```
   https://mkp.gem.gov.in/{category-slug}/search#/?q=...
   ```

3. **Paste into the tool** — Click "Scrape →" and wait ~30 seconds while it fetches all products and extracts specifications.

4. **Enter your selling price** — The tool instantly computes all filter combinations where your price is the lowest (L1).

5. **Apply the winning filters** — Go to your GeM Seller Dashboard → Edit your product listing → Set the recommended filter values → Save and submit.

---

## ⚙️ Key Features

- **Automated Scraping** — Fetches all products from GeM's internal JSON API (no browser automation needed)
- **Parallel Spec Extraction** — Enriches products with full specifications using multi-threaded requests
- **L1 Analysis Engine** — Tests every single-filter and 2-filter combination to find L1 opportunities
- **Untapped Niche Detection** — Identifies filter combinations with zero competitors
- **Opportunity Scoring** — Ranks results by price gap, competition scarcity, and traffic potential
- **Smart Caching** — 30-minute cache to avoid redundant scraping
- **Robust Session Handling** — Auto-retries with exponential backoff and session cookie management
- **Dark Theme UI** — Clean, modern interface with interactive charts

---

## ⚠️ Important Notes

- This tool scrapes **publicly available** data from the GeM marketplace. No login is required.
- Some category URLs may be deprecated or empty on GeM — the tool will notify you with a descriptive error message.
- Use **category-specific URLs** (not global search URLs) for best results.
- GeM may rate-limit aggressive scraping. The tool includes built-in throttling (0.2s delay between pages).

---

## 📄 License

This project is for educational and personal use. GeM marketplace data belongs to the Government e-Marketplace, Government of India.

---

## 🤝 Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
