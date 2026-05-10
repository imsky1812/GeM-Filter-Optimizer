import { useState, useEffect, useRef } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import "./index.css";

const BACKEND_URL = "http://localhost:8000";

// ─── ANALYSIS ENGINE ──────────────────────────────────────────────────────────

// Dynamically reconstruct GeM's internal taxonomy dependencies
function detectDependencies(products, filters) {
  const rules = [];
  if (!products || products.length < 5) return rules;

  for (let i = 0; i < filters.length; i++) {
    for (let j = 0; j < filters.length; j++) {
      if (i === j) continue;
      
      const f1 = filters[i];
      const f2 = filters[j];
      const observations = {};
      let totalObserved = 0;
      
      for (const p of products) {
        const v1 = String(p.specs[f1.filterKey] || "").toLowerCase();
        const v2 = String(p.specs[f2.filterKey] || "").toLowerCase();
        
        if (v1 && v2) {
          if (!observations[v1]) observations[v1] = new Set();
          observations[v1].add(v2);
          totalObserved++;
        }
      }
      
      // Need enough representative data to infer a hard taxonomy rule
      if (totalObserved < 10) continue; 

      let strictlyDetermines = true;
      for (const v2Set of Object.values(observations)) {
        if (v2Set.size > 1) {
          strictlyDetermines = false;
          break;
        }
      }
      
      if (strictlyDetermines) {
        const mapping = {};
        for (const [v1, v2Set] of Object.entries(observations)) {
          mapping[v1] = Array.from(v2Set)[0];
        }
        rules.push({
          detKey: f1.filterKey,
          depKey: f2.filterKey,
          mapping: mapping
        });
      }
    }
  }
  return rules;
}

// Find all filter combinations where seller's price is the lowest (L1)
function findL1Opportunities(products, sellerPrice, filters) {
  const results = [];
  const combos = [];

  // Generate all 1-filter and 2-filter combos
  for (let i = 0; i < filters.length; i++) {
    const f1 = filters[i];
    for (const v1 of f1.values) {
      combos.push([{ key: f1.filterKey, name: f1.filterName, value: v1, isGolden: f1.isGolden }]);
    }
    for (let j = i + 1; j < filters.length; j++) {
      const f2 = filters[j];
      for (const v1 of f1.values) {
        for (const v2 of f2.values) {
          combos.push([
            { key: f1.filterKey, name: f1.filterName, value: v1, isGolden: f1.isGolden },
            { key: f2.filterKey, name: f2.filterName, value: v2, isGolden: f2.isGolden },
          ]);
        }
      }
    }
  }

  const rules = detectDependencies(products, filters);
  const validCombos = [];

  for (const combo of combos) {
    let isContradictory = false;
    for (let i = 0; i < combo.length; i++) {
      for (let j = 0; j < combo.length; j++) {
        if (i === j) continue;
        const c1 = combo[i];
        const c2 = combo[j];
        
        const rule = rules.find(r => r.detKey === c1.key && r.depKey === c2.key);
        if (rule) {
          const expectedV2 = rule.mapping[c1.value.toLowerCase()];
          if (expectedV2 && expectedV2 !== c2.value.toLowerCase()) {
            isContradictory = true;
            break;
          }
        }
      }
      if (isContradictory) break;
    }
    if (!isContradictory) {
      validCombos.push(combo);
    }
  }

  const maxGap = sellerPrice * 0.8 || 1;

  for (const combo of validCombos) {
    // Find products matching this filter combo
    const matching = products.filter((p) =>
      combo.every(
        (c) =>
          String(p.specs[c.key] || "").toLowerCase() === c.value.toLowerCase()
      )
    );

    const isUntapped = matching.length === 0;
    const minCompPrice = isUntapped ? Infinity : Math.min(...matching.map((p) => p.price));

    // Only include combos where seller IS the cheapest (L1)
    if (minCompPrice <= sellerPrice) continue;

    const priceGap = isUntapped ? sellerPrice * 0.5 : minCompPrice - sellerPrice;
    const gapScore = isUntapped ? 100 : Math.min(priceGap / maxGap, 1) * 100;
    const scarcityScore = Math.max(1 - matching.length / 10, 0) * 100;
    const trafficScore = isUntapped ? 80 : Math.min(matching.length / 5, 1) * 100;
    const hasGolden = combo.some((c) => c.isGolden);
    
    // Severely penalize score if combo does NOT include any Golden filters,
    // because GeM calculates L1 strictly based on Golden parameters.
    const rawScore = gapScore * 0.5 + scarcityScore * 0.3 + trafficScore * 0.2;
    const score = isUntapped ? 100 : Math.round(hasGolden ? rawScore : rawScore * 0.3);

    const competitors = matching.sort((a, b) => a.price - b.price).slice(0, 3);

    results.push({
      combo,
      label: combo.map((c) => `${c.name}: ${c.value}`).join(" + "),
      competitorCount: matching.length,
      minCompetitorPrice: minCompPrice,
      sellerPrice,
      priceGap: isUntapped ? 0 : priceGap, // don't show arbitrary gap
      score,
      isSingle: combo.length === 1,
      competitors,
      isUntapped,
      hasGolden
    });
  }

  return results.sort((a, b) => b.score - a.score);
}

// ─── SMALL COMPONENTS ─────────────────────────────────────────────────────────
const ChartTip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div
      style={{
        background: "var(--surface2)",
        border: "1px solid var(--border)",
        borderRadius: 10,
        padding: "10px 14px",
        fontSize: 12,
        color: "var(--text)",
        boxShadow: "var(--shadow-lg)",
      }}
    >
      <div
        style={{
          fontWeight: 600,
          marginBottom: 4,
          maxWidth: 220,
          lineHeight: 1.3,
        }}
      >
        {d.label}
      </div>
      <div>
        Score: <strong>{d.score}</strong>
      </div>
      <div>
        Gap:{" "}
        <strong style={{ color: "var(--green)" }}>
          ₹{d.priceGap.toLocaleString()}
        </strong>
      </div>
      <div>
        Competitors: <strong>{d.competitorCount}</strong>
      </div>
    </div>
  );
};

function OpportunityCard({ r, rank }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="win-card">
      <div className="win-card-top" onClick={() => setOpen((o) => !o)}>
        <span className="win-rank win-rank-ready">L1</span>
        <div className="win-card-body">
          <div className="win-filters">
            {r.combo.map((c, i) => {
              const filterName = c.name || c.filterName || c.filterKey || "Filter";
              return (
                <span key={i} className={`filter-chip ${c.isGolden ? 'filter-chip-golden' : ''}`}>
                  {c.isGolden && <span className="golden-dot">★</span>}
                  <span className="filter-chip-name">{filterName}</span>: <strong>{c.value}</strong>
                </span>
              );
            })}
          </div>
          <div className="win-meta">
            <span>
              Next cheapest:{" "}
              <strong>{r.isUntapped ? "None (Untapped)" : `₹${r.minCompetitorPrice.toLocaleString()}`}</strong>
            </span>
            <span>
              Your price:{" "}
              <strong>₹{r.sellerPrice.toLocaleString()}</strong>
            </span>
            <span>
              Gap:{" "}
              <strong className="gap-val">
                {r.isUntapped ? "∞" : `₹${r.priceGap.toLocaleString()}`}
              </strong>
            </span>
            <span>
              Competitors: <strong>{r.competitorCount}</strong>
            </span>
          </div>
        </div>
        <div className="win-score">
          <div className="win-score-num">{r.score}</div>
          <div className="win-score-label">score</div>
        </div>
        <span className="expand-arrow">{open ? "▲" : "▼"}</span>
      </div>
      {open && (
        <div className="win-detail">
          {!r.hasGolden && (
            <div className="warn-box" style={{ marginBottom: "1rem" }}>
              <span style={{ fontSize: "1rem", marginRight: "6px" }}>⚠</span>
              <span>
                <strong>Warning:</strong> This combination uses only normal filters.
                On GeM, changing normal filters <strong>does NOT</strong> change who gets the L1 position.
                L1 is determined strictly by Golden Parameters and Make in India/MSE status.
                Use combinations with Golden Filters to guarantee L1.
              </span>
            </div>
          )}
          <div className="detail-cols">
            <div>
              <div className="detail-section-title">Price Ranking</div>
              <table className="comp-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Product</th>
                    <th>Price</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="yours-row">
                    <td>
                      <span
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 11,
                          fontWeight: 700,
                          background: "var(--green)",
                          color: "#000",
                          padding: "2px 5px",
                          borderRadius: 3,
                        }}
                      >
                        1
                      </span>
                    </td>
                    <td>
                      Your Product{" "}
                      <span className="rank1-badge">YOU</span>
                    </td>
                    <td
                      className="price-mono"
                      style={{ color: "var(--green)" }}
                    >
                      ₹{r.sellerPrice.toLocaleString()}
                    </td>
                  </tr>
                  {r.competitors.map((c, i) => (
                    <tr key={i}>
                      <td
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 11,
                          color: "var(--text4)",
                        }}
                      >
                        {i + 2}
                      </td>
                      <td
                        style={{
                          maxWidth: 160,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {c.name || c.id}
                      </td>
                      <td className="price-mono">
                        ₹{c.price.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div>
              <div className="detail-section-title">
                How to Apply on GeM
              </div>
              <div className="steps-list">
                <div className="step-item">
                  <span className="step-icon si-info">1</span>
                  <span className="step-text">
                    Go to <strong>GeM Seller Dashboard → My Products</strong>
                  </span>
                </div>
                <div className="step-item">
                  <span className="step-icon si-info">2</span>
                  <span className="step-text">
                    Click <strong>Edit Listing</strong> on your product
                  </span>
                </div>
                {r.combo.map((c, i) => {
                  const filterName = c.name || c.filterName || c.filterKey || "Filter";
                  return (
                    <div className="step-item" key={i}>
                      <span className="step-icon si-set">✓</span>
                      <span className="step-text">
                        Set <strong>"{filterName}"</strong> to{" "}
                        <strong>"{c.value}"</strong>
                      </span>
                    </div>
                  );
                })}
                <div className="step-item">
                  <span className="step-icon si-info">→</span>
                  <span className="step-text">
                    Save &amp; submit listing for review
                  </span>
                </div>
                <div className="step-item">
                  <span className="step-icon si-result">★</span>
                  <span className="step-text">
                    <strong>
                      You rank L1 — cheapest by ₹
                      {r.priceGap.toLocaleString()}
                    </strong>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── MAIN APP ─────────────────────────────────────────────────────────────────
export default function App() {
  const [gemUrl, setGemUrl] = useState("");
  const [sellerPrice, setSellerPrice] = useState("");
  const [scrapedData, setScrapedData] = useState(null);
  const [scrapeStatus, setScrapeStatus] = useState("idle");
  const [scrapeError, setScrapeError] = useState("");
  const [results, setResults] = useState(null);
  const [activeTab, setActiveTab] = useState("single");
  const [locations, setLocations] = useState(["All India"]);
  const [selectedLocation, setSelectedLocation] = useState("All India");
  const analyzeTimerRef = useRef(null);

  // Deep Search state
  const [deepStatus, setDeepStatus] = useState("idle"); // idle | loading | done | error
  const [deepResults, setDeepResults] = useState(null);
  const [deepError, setDeepError] = useState("");

  // Fetch locations on mount
  useEffect(() => {
    fetch(`${BACKEND_URL}/locations`)
      .then((res) => res.json())
      .then((data) => {
        if (data && data.locations) {
          setLocations(data.locations);
        }
      })
      .catch((err) => console.error("Failed to load locations", err));
  }, []);

  const priceNum = parseInt(sellerPrice) || 0;

  // Auto-analyze when price changes (debounced)
  useEffect(() => {
    if (analyzeTimerRef.current) clearTimeout(analyzeTimerRef.current);

    if (!scrapedData || !priceNum) {
      setResults(null);
      return;
    }

    analyzeTimerRef.current = setTimeout(() => {
      const all = findL1Opportunities(
        scrapedData.products,
        priceNum,
        scrapedData.filters
      );

      const singles = all.filter((r) => r.isSingle);
      const combos = all.filter((r) => !r.isSingle);
      const bestGap =
        all.length > 0
          ? Math.max(...all.map((r) => r.priceGap))
          : 0;

      setResults({ all, singles, combos, bestGap });
      setActiveTab(singles.length > 0 ? "single" : "combo");
    }, 300);

    return () => clearTimeout(analyzeTimerRef.current);
  }, [priceNum, scrapedData]);

  const handleScrape = async () => {
    if (!gemUrl.trim()) return;
    setScrapeStatus("loading");
    setScrapeError("");
    setScrapedData(null);
    setResults(null);
    // Reset deep search when re-scraping
    setDeepStatus("idle");
    setDeepResults(null);
    setDeepError("");

    // Auto-prepend https:// if user didn't include a protocol
    let normalizedUrl = gemUrl.trim();
    if (!normalizedUrl.startsWith("http://") && !normalizedUrl.startsWith("https://")) {
      normalizedUrl = "https://" + normalizedUrl;
      setGemUrl(normalizedUrl);
    }

    try {
      const res = await fetch(`${BACKEND_URL}/scrape`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: normalizedUrl, location: selectedLocation }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(
          typeof err.detail === "object"
            ? err.detail.message
            : err.detail || "Backend error"
        );
      }
      const parsed = await res.json();
      setScrapedData(parsed);
      setScrapeStatus("done");
    } catch (e) {
      setScrapeError(e.message || "Failed to scrape");
      setScrapeStatus("error");
    }
  };

  const handleDeepSearch = async () => {
    if (!gemUrl.trim() || !priceNum) return;
    setDeepStatus("loading");
    setDeepResults(null);
    setDeepError("");
    setActiveTab("deep");

    let normalizedUrl = gemUrl.trim();
    if (!normalizedUrl.startsWith("http://") && !normalizedUrl.startsWith("https://")) {
      normalizedUrl = "https://" + normalizedUrl;
    }

    try {
      const res = await fetch(`${BACKEND_URL}/find-l1`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: normalizedUrl,
          seller_price: priceNum,
          location: selectedLocation,
          max_depth: 10,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(
          typeof err.detail === "object"
            ? err.detail.message
            : err.detail || "Deep search failed"
        );
      }
      const data = await res.json();
      setDeepResults(data);
      setDeepStatus("done");
    } catch (e) {
      setDeepError(e.message || "Deep search failed");
      setDeepStatus("error");
    }
  };

  const totalWins = results ? results.all.length : 0;
  const chartList =
    results && activeTab === "single" ? results.singles : results?.combos || [];
  const chartData = chartList.slice(0, 12).map((r) => ({
    label: r.combo.map((c) => c.value).join(" + "),
    score: r.score,
    priceGap: r.priceGap,
    competitorCount: r.competitorCount,
  }));

  // Price range info for the category
  const minCatPrice = scrapedData
    ? Math.min(...scrapedData.products.map((p) => p.price))
    : 0;
  const maxCatPrice = scrapedData
    ? Math.max(...scrapedData.products.map((p) => p.price))
    : 0;

  return (
    <div className="app">
      {/* HEADER */}
      <div className="hdr">
        <div className="hdr-eyebrow">GeM India · L1 Filter Intelligence</div>
        <h1>
          Find Your <em>L1 Rank</em> Filters
        </h1>
        <p className="hdr-sub">
          Enter a GeM category URL and your price → instantly see the{" "}
          <strong>best filters to apply</strong> so buyers always see your
          product as the <strong>cheapest (L1)</strong>.
        </p>
      </div>

      {/* STEP 1: URL */}
      <div className="card fade-in">
        <div className="card-hdr">
          <div className="step-num">01</div>
          <div>
            <div className="card-title">GeM Category URL</div>
            <div className="card-desc">
              Paste a category listing URL from mkp.gem.gov.in
            </div>
          </div>
        </div>
        <div className="input-row">
          <input
            type="text"
            value={gemUrl}
            onChange={(e) => setGemUrl(e.target.value)}
            placeholder="mkp.gem.gov.in/.../search or mkp.gemorion.org/.../search#/?q=..."
            onKeyDown={(e) => e.key === "Enter" && handleScrape()}
            id="gem-url-input"
          />
          <div className="location-select-wrap">
            <select 
              value={selectedLocation} 
              onChange={(e) => setSelectedLocation(e.target.value)}
              className="location-select"
              title="Filter by Seller Delivery Location"
            >
              {locations.map((loc, i) => (
                <option key={i} value={loc}>{loc}</option>
              ))}
            </select>
            <span className="select-arrow">▼</span>
          </div>
          <button
            className="btn btn-primary"
            onClick={handleScrape}
            disabled={scrapeStatus === "loading" || !gemUrl.trim()}
            id="scrape-btn"
          >
            {scrapeStatus === "loading" ? (
              <>
                <span className="spin" />
                Scraping...
              </>
            ) : (
              "Scrape →"
            )}
          </button>
        </div>
        {scrapeStatus === "loading" && (
          <div className="loading">
            <span className="spin spin-muted" />
            Fetching products · Extracting specs · Building filters...
            <br />
            <span style={{ fontSize: ".7rem", color: "var(--text4)" }}>
              Scanning all products in category (unlimited pages)
            </span>
          </div>
        )}
        {scrapeError && <div className="err-box">{scrapeError}</div>}
        {scrapeStatus === "done" && scrapedData && (
          <div className="info-box">
            ✓ Loaded{" "}
            <strong>{scrapedData.products.length} products</strong> with{" "}
            <strong>{scrapedData.filters.length} filters</strong>
            {scrapedData.location && scrapedData.location !== "All India" && (
              <span className="loc-badge">📍 {scrapedData.location}</span>
            )}
            {scrapedData.totalResults > scrapedData.productCount && (
              <span>
                {" "}
                (out of {scrapedData.totalResults} in this category)
              </span>
            )}
            <span
              style={{
                marginLeft: 8,
                fontFamily: "var(--mono)",
                fontSize: ".65rem",
                color: "var(--text3)",
              }}
            >
              Price range: ₹{minCatPrice.toLocaleString()} – ₹
              {maxCatPrice.toLocaleString()}
            </span>
          </div>
        )}
      </div>

      {/* STEP 2: PRICE → AUTO-ANALYZE */}
      {scrapedData && (
        <div className="card fade-in fade-in-d1">
          <div className="card-hdr">
            <div className="step-num">02</div>
            <div>
              <div className="card-title">Your Product Price</div>
              <div className="card-desc">
                Enter your selling price — we'll instantly show the best
                filters for L1 ranking
              </div>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div className="price-wrap">
              <span className="price-sym">₹</span>
              <input
                type="number"
                value={sellerPrice}
                onChange={(e) => setSellerPrice(e.target.value)}
                placeholder={minCatPrice.toLocaleString()}
                id="price-input"
              />
            </div>
            {priceNum > 0 && results && (
              <div
                style={{
                  fontSize: ".75rem",
                  color:
                    totalWins > 0 ? "var(--green)" : "var(--text3)",
                }}
              >
                {totalWins > 0 ? (
                  <>
                    🏆{" "}
                    <strong>
                      {totalWins} L1 opportunit
                      {totalWins === 1 ? "y" : "ies"}
                    </strong>{" "}
                    found
                  </>
                ) : (
                  <>
                    No L1 positions at this price — try{" "}
                    <strong>
                      below ₹{minCatPrice.toLocaleString()}
                    </strong>
                  </>
                )}
              </div>
            )}
          </div>
          {priceNum > 0 && priceNum >= maxCatPrice && (
            <div className="warn-box" style={{ marginTop: ".75rem" }}>
              ⚠ Your price ₹{priceNum.toLocaleString()} is above all{" "}
              {scrapedData.products.length} products in this category.
              Lower your price to find L1 opportunities.
            </div>
          )}
        </div>
      )}

      {/* RESULTS */}
      {results && totalWins > 0 && (
        <>
          {/* Stats */}
          <div className="stats fade-in">
            <div className="stat">
              <div className="stat-lbl">Total L1 Wins</div>
              <div className="stat-val g">{totalWins}</div>
            </div>
            <div className="stat">
              <div className="stat-lbl">Single Filters</div>
              <div className="stat-val g">{results.singles.length}</div>
            </div>
            <div className="stat">
              <div className="stat-lbl">Filter Combos</div>
              <div className="stat-val a">{results.combos.length}</div>
            </div>
            <div className="stat">
              <div className="stat-lbl">Best Gap</div>
              <div className="stat-val g">
                ₹{results.bestGap.toLocaleString()}
              </div>
            </div>
          </div>

          {/* Results Card */}
          <div className="card fade-in fade-in-d2">
            <div className="results-hdr">
              <div className="results-title">
                🏆 Best Filters for L1 Rank
              </div>
              <div className="tally">
                <span className="tally-chip tally-green">
                  {results.singles.length} single filters
                </span>
                <span className="tally-chip tally-amber">
                  {results.combos.length} filter combos
                </span>
              </div>
            </div>

            <div className="tabs">
              <button
                className={`tab ${activeTab === "single" ? "on" : ""}`}
                onClick={() => setActiveTab("single")}
              >
                🎯 Single Filters ({results.singles.length})
              </button>
              <button
                className={`tab ${activeTab === "combo" ? "on" : ""}`}
                onClick={() => setActiveTab("combo")}
              >
                🔗 Filter Combos ({results.combos.length})
              </button>
              <button
                className={`tab ${activeTab === "chart" ? "on" : ""}`}
                onClick={() => setActiveTab("chart")}
              >
                📊 Chart
              </button>
              <button
                className={`tab tab-deep ${activeTab === "deep" ? "on" : ""}`}
                onClick={() => setActiveTab("deep")}
                id="deep-search-tab"
              >
                🔍 Deep Search
              </button>
            </div>

            {activeTab === "single" &&
              (results.singles.length === 0 ? (
                <div className="empty">
                  <div className="empty-icon">🎯</div>
                  <div className="empty-text">
                    No single-filter L1 positions. Check filter combos.
                  </div>
                </div>
              ) : (
                <>
                  <div
                    style={{
                      fontSize: ".72rem",
                      color: "var(--text3)",
                      marginBottom: "1rem",
                    }}
                  >
                    Set any <strong>one</strong> of these filter values on
                    your GeM listing to rank L1 in that filtered view:
                  </div>
                  {results.singles.map((r, i) => (
                    <OpportunityCard key={i} r={r} rank={i + 1} />
                  ))}
                </>
              ))}

            {activeTab === "combo" &&
              (results.combos.length === 0 ? (
                <div className="empty">
                  <div className="empty-icon">🔗</div>
                  <div className="empty-text">
                    No combo-filter L1 positions found.
                  </div>
                </div>
              ) : (
                <>
                  <div
                    style={{
                      fontSize: ".72rem",
                      color: "var(--text3)",
                      marginBottom: "1rem",
                    }}
                  >
                    Set <strong>all</strong> filter values together for
                    these L1 niches:
                  </div>
                  {results.combos.slice(0, 100).map((r, i) => (
                    <OpportunityCard key={i} r={r} rank={i + 1} />
                  ))}
                  {results.combos.length > 100 && (
                    <div
                      style={{
                        fontSize: ".72rem",
                        color: "var(--text4)",
                        textAlign: "center",
                        padding: "1rem",
                      }}
                    >
                      + {results.combos.length - 100} more combos
                    </div>
                  )}
                </>
              ))}

            {activeTab === "deep" && (
              <div className="deep-search-panel">
                {deepStatus === "idle" && (
                  <div className="deep-search-intro">
                    <div className="deep-icon">🔍</div>
                    <div className="deep-title">Cascading Golden Filter Search</div>
                    <div className="deep-desc">
                      Deep Search re-scrapes GeM <strong>live</strong> after each golden filter is applied,
                      then picks the <em>next available</em> golden filter from the narrowed result —
                      repeating up to <strong>10 levels</strong> until your price becomes L1.
                      This finds combinations of <strong>3 to 10 golden filters</strong> that
                      static analysis misses.
                    </div>
                    <div className="deep-warning">
                      ⏱ This may take <strong>1–3 minutes</strong> depending on category size.
                    </div>
                    <button
                      className="btn btn-deep"
                      onClick={handleDeepSearch}
                      disabled={!priceNum || scrapeStatus !== "done"}
                      id="deep-search-btn"
                    >
                      🔍 Start Deep Search
                    </button>
                  </div>
                )}

                {deepStatus === "loading" && (
                  <div className="deep-loading">
                    <span className="spin spin-amber" />
                    <div className="deep-loading-title">Deep Search Running...</div>
                    <div className="deep-loading-sub">
                      Re-scraping GeM with cascading golden filters.
                      This may take 1–3 minutes.
                    </div>
                    <div className="deep-progress-bar">
                      <div className="deep-progress-fill" />
                    </div>
                    <div style={{ fontSize: ".68rem", color: "var(--text4)", marginTop: ".5rem" }}>
                      Exploring depth 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 golden filter combinations...
                    </div>
                  </div>
                )}

                {deepStatus === "error" && (
                  <div className="err-box" style={{ marginTop: "1rem" }}>
                    {deepError}
                    <button
                      className="btn btn-deep"
                      onClick={handleDeepSearch}
                      style={{ marginTop: "1rem" }}
                    >
                      Retry
                    </button>
                  </div>
                )}

                {deepStatus === "done" && deepResults && (
                  <>
                    <div className="deep-summary-row">
                      <div className="deep-stat">
                        <div className="deep-stat-val">{deepResults.combinations?.length ?? 0}</div>
                        <div className="deep-stat-lbl">L1 Combos Found</div>
                      </div>
                      <div className="deep-stat">
                        <div className="deep-stat-val">{deepResults.totalScraped ?? 0}</div>
                        <div className="deep-stat-lbl">Re-Scrapes Done</div>
                      </div>
                      <div className="deep-stat">
                        <div className="deep-stat-val">{deepResults.goldenFilterCount ?? 0}</div>
                        <div className="deep-stat-lbl">Golden Filters</div>
                      </div>
                      {deepResults.truncated && (
                        <div className="deep-stat deep-stat-warn">
                          <div className="deep-stat-val">⚡</div>
                          <div className="deep-stat-lbl">Search capped at 120 calls</div>
                        </div>
                      )}
                    </div>

                    {deepResults.combinations?.length === 0 ? (
                      <div className="empty" style={{ marginTop: "1rem" }}>
                        <div className="empty-icon">🔍</div>
                        <div className="empty-text">
                          No L1 niches found even with cascading golden filters.<br />
                          <span style={{ color: "var(--text4)", fontSize: ".8rem" }}>
                            Try lowering your price.
                          </span>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div style={{ fontSize: ".72rem", color: "var(--text3)", marginBottom: "1rem" }}>
                          Found <strong>{deepResults.combinations.length}</strong> L1 winning combinations
                          via live re-scraping — sorted by opportunity score:
                        </div>
                        {/* Group by depth */}
                        {[...new Set(deepResults.combinations.map(c => c.depth))].sort().map(depth => {
                          const group = deepResults.combinations.filter(c => c.depth === depth);
                          return (
                            <div key={depth} className="depth-group">
                              <div className="depth-group-hdr">
                                <span className="depth-badge">Depth {depth}</span>
                                <span className="depth-badge-sub">
                                  {depth} golden filter{depth > 1 ? "s" : ""} applied — {group.length} win{group.length !== 1 ? "s" : ""}
                                </span>
                              </div>
                              {group.map((r, i) => (
                                <OpportunityCard key={i} r={r} rank={i + 1} />
                              ))}
                            </div>
                          );
                        })}

                        {/* Progress log toggle */}
                        <details className="progress-log-details">
                          <summary>View search log ({deepResults.progress?.length ?? 0} entries)</summary>
                          <div className="progress-log">
                            {(deepResults.progress ?? []).map((line, i) => (
                              <div key={i} className={`log-line ${
                                line.includes("✅") ? "log-win" :
                                line.includes("Error") ? "log-err" :
                                line.includes("[Done]") ? "log-done" :
                                line.includes("deeper") ? "log-deeper" : ""
                              }`}>
                                {line}
                              </div>
                            ))}
                          </div>
                        </details>

                        <button
                          className="btn btn-deep"
                          onClick={handleDeepSearch}
                          style={{ marginTop: "1.5rem" }}
                        >
                          🔄 Re-run Deep Search
                        </button>
                      </>
                    )}
                  </>
                )}
              </div>
            )}

            {activeTab === "chart" && (
              <>
                <div
                  style={{
                    fontSize: ".72rem",
                    fontWeight: 600,
                    color: "var(--text3)",
                    marginBottom: ".5rem",
                    fontFamily: "var(--mono)",
                    textTransform: "uppercase",
                    letterSpacing: ".06em",
                  }}
                >
                  Viewing: Top {results.all.length} Opportunities
                </div>
                <div
                  style={{
                    fontSize: ".72rem",
                    color: "var(--text4)",
                    marginBottom: ".5rem",
                  }}
                >
                  Opportunity score — higher means better L1 position
                </div>
                <div className="chart-wrap">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={results.all.slice(0, 12).map((r) => ({
                        label: r.combo
                          .map((c) => c.value)
                          .join(" + "),
                        score: r.score,
                        priceGap: r.priceGap,
                        competitorCount: r.competitorCount,
                      }))}
                      margin={{
                        top: 5,
                        right: 10,
                        bottom: 70,
                        left: 0,
                      }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="rgba(255,255,255,.04)"
                      />
                      <XAxis
                        dataKey="label"
                        tick={{
                          fontSize: 9,
                          fontFamily: "var(--mono)",
                          fill: "var(--text3)",
                        }}
                        angle={-40}
                        textAnchor="end"
                        interval={0}
                      />
                      <YAxis
                        tick={{
                          fontSize: 10,
                          fontFamily: "var(--mono)",
                          fill: "var(--text3)",
                        }}
                      />
                      <Tooltip content={<ChartTip />} />
                      <Bar dataKey="score" radius={[6, 6, 0, 0]}>
                        {results.all.slice(0, 12).map((r, i) => (
                          <Cell
                            key={i}
                            fill={
                              r.isSingle
                                ? "var(--green)"
                                : "var(--amber)"
                            }
                            opacity={0.8}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </>
            )}
          </div>
        </>
      )}

      {/* No results state */}
      {results && totalWins === 0 && priceNum > 0 && (
        <div className="card">
          <div className="empty">
            <div className="empty-icon">💰</div>
            <div className="empty-text">
              No L1 filter positions at ₹{priceNum.toLocaleString()}.
              <br />
              The cheapest product in this category is{" "}
              <strong>₹{minCatPrice.toLocaleString()}</strong>.
              <br />
              <span style={{ color: "var(--text4)", fontSize: ".8rem" }}>
                Lower your price below the cheapest competitor in a filter niche.
              </span>
            </div>
            <button
              className="btn btn-deep"
              style={{ marginTop: "1.5rem" }}
              onClick={() => {
                setActiveTab("deep");
                handleDeepSearch();
              }}
              disabled={deepStatus === "loading"}
              id="try-deep-search-btn"
            >
              🔍 Try Deep Search — find 3+ golden filter combos
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
