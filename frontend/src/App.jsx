import { useState, useEffect, useRef } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import "./index.css";

const BACKEND_URL = "http://localhost:8000";

// ─── ANALYSIS ENGINE ──────────────────────────────────────────────────────────
// Find all filter combinations where seller's price is the lowest (L1)
function findL1Opportunities(products, sellerPrice, filters) {
  const results = [];
  const combos = [];

  // Generate all 1-filter and 2-filter combos
  for (let i = 0; i < filters.length; i++) {
    const f1 = filters[i];
    for (const v1 of f1.values) {
      combos.push([{ key: f1.filterKey, name: f1.filterName, value: v1 }]);
    }
    for (let j = i + 1; j < filters.length; j++) {
      const f2 = filters[j];
      for (const v1 of f1.values) {
        for (const v2 of f2.values) {
          combos.push([
            { key: f1.filterKey, name: f1.filterName, value: v1 },
            { key: f2.filterKey, name: f2.filterName, value: v2 },
          ]);
        }
      }
    }
  }

  const maxGap = sellerPrice * 0.8 || 1;

  for (const combo of combos) {
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
    const score = isUntapped ? 100 : Math.round(
      gapScore * 0.5 + scarcityScore * 0.3 + trafficScore * 0.2
    );

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
      isUntapped
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
            {r.combo.map((c, i) => (
              <span key={i} className="filter-chip">
                {c.name}: <strong>{c.value}</strong>
              </span>
            ))}
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
                {r.combo.map((c, i) => (
                  <div className="step-item" key={i}>
                    <span className="step-icon si-set">✓</span>
                    <span className="step-text">
                      Set <strong>"{c.name}"</strong> to{" "}
                      <strong>"{c.value}"</strong>
                    </span>
                  </div>
                ))}
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
  const analyzeTimerRef = useRef(null);

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
        body: JSON.stringify({ url: normalizedUrl }),
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
              This takes ~30s (scraping {">"}30 product pages)
            </span>
          </div>
        )}
        {scrapeError && <div className="err-box">{scrapeError}</div>}
        {scrapeStatus === "done" && scrapedData && (
          <div className="info-box">
            ✓ Loaded{" "}
            <strong>{scrapedData.products.length} products</strong> with{" "}
            <strong>{scrapedData.filters.length} filters</strong>
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
                    Set <strong>both</strong> filter values together for
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
                Lower your price below the cheapest competitor in a filter
                niche.
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
