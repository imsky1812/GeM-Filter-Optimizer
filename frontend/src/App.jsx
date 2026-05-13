import { useState, useEffect, useRef } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import "./index.css";

const BACKEND_URL = "/api";

// ─── ANALYSIS ENGINE ──────────────────────────────────────────────────────────


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
  const [locations, setLocations] = useState(["All India"]);
  const [selectedLocation, setSelectedLocation] = useState("All India");
  const handlePrintReport = () => window.print();

  // Deep Search state
  const [deepStatus, setDeepStatus] = useState("idle"); // idle | loading | done | error
  const [deepResults, setDeepResults] = useState(null);
  const [deepError, setDeepError] = useState("");
  const [deepDepthTab, setDeepDepthTab] = useState(null); // selected depth tab
  const [deepRange, setDeepRange] = useState({ min: 3, max: 10 });
  const [mandatoryFilters, setMandatoryFilters] = useState([]);
  const [isFilterDropdownOpen, setIsFilterDropdownOpen] = useState(false);
  const [hoveredFilterKey, setHoveredFilterKey] = useState(null);


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

  const handleDeepSearch = async (minD = 3, maxD = 10) => {
    if (!gemUrl.trim() || !priceNum) return;
    setDeepRange({ min: minD, max: maxD });
    setDeepStatus("loading");
    setDeepResults(null);
    setDeepError("");
    setDeepDepthTab(null);
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
          min_depth: minD,
          max_depth: maxD,
          golden_filters: scrapedData
            ? scrapedData.filters.filter((f) => f.isGolden)
            : [],
          mandatory_filters: mandatoryFilters,
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
        <div className="card fade-in fade-in-d1" style={{ position: "relative", zIndex: 50 }}>
          <div className="card-hdr">
            <div className="step-num">02</div>
            <div>
              <div className="card-title">Your Product Price</div>
              <div className="card-desc">
                Enter your selling price and launch Deep Search for guaranteed L1 ranking paths
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
            {priceNum > 0 && (
              <div style={{ display: "flex", gap: "12px", marginLeft: "auto" }}>
                <button
                  className="btn btn-deep"
                  onClick={() => handleDeepSearch(3, 10)}
                  disabled={scrapeStatus !== "done"}
                  style={{ padding: "8px 16px", fontSize: "0.85rem", background: "var(--primary)", border: "none", borderRadius: "6px", color: "white", cursor: "pointer", boxShadow: "0 4px 12px rgba(156, 39, 176, 0.3)" }}
                >
                  🔍 Standard Search (3-10)
                </button>
                <button
                  className="btn btn-deep"
                  onClick={() => handleDeepSearch(11, 15)}
                  disabled={scrapeStatus !== "done"}
                  style={{ padding: "8px 16px", fontSize: "0.85rem", background: "linear-gradient(135deg, var(--primary), #9c27b0)", border: "none", borderRadius: "6px", color: "white", cursor: "pointer", boxShadow: "0 4px 12px rgba(156, 39, 176, 0.3)" }}
                >
                  🚀 Ultra Deep Search (11-15)
                </button>
              </div>
            )}
          </div>
          {/* Mandatory Filters Section - MOVED TO STEP 2 */}
          <div className="mandatory-filters-section" style={{ marginTop: "1.5rem", textAlign: "left", background: "var(--surface2)", padding: "1rem", borderRadius: "8px", border: "1px solid var(--border)" }}>
            <div style={{ marginBottom: "0.5rem", fontWeight: "bold", fontSize: "0.9rem" }}>
              Mandatory Spec Requirements (Optional)
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--text3)", marginBottom: "1rem" }}>
              Select any specific features the buyer absolutely requires. The deep search will start from these filters and find the remaining golden filters needed for L1.
            </div>
            
            {/* Selected Filters Chips */}
            {mandatoryFilters.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "1rem" }}>
                {mandatoryFilters.map((mf, idx) => (
                  <div key={idx} style={{ 
                    background: "rgba(156, 39, 176, 0.15)", 
                    border: "1px solid rgba(156, 39, 176, 0.4)",
                    padding: "4px 8px", 
                    borderRadius: "4px",
                    fontSize: "0.75rem",
                    display: "flex",
                    alignItems: "center",
                    gap: "4px"
                  }}>
                    <span style={{ color: "var(--text2)" }}>{mf.filterName}:</span>
                    <strong style={{ color: "var(--text1)" }}>{mf.value}</strong>
                    <button 
                      onClick={() => setMandatoryFilters(prev => prev.filter((_, i) => i !== idx))}
                      style={{ background: "none", border: "none", color: "var(--text3)", cursor: "pointer", marginLeft: "4px", padding: 0 }}
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Dropdown UI */}
            <div style={{ position: "relative" }}>
              <button 
                className="btn" 
                onClick={() => setIsFilterDropdownOpen(!isFilterDropdownOpen)}
                style={{ 
                  background: isFilterDropdownOpen ? "rgba(156, 39, 176, 0.15)" : "var(--surface1)", 
                  border: isFilterDropdownOpen ? "1px solid var(--primary)" : "1px solid var(--border)", 
                  fontSize: "0.8rem", 
                  padding: "8px 16px",
                  borderRadius: "6px",
                  color: isFilterDropdownOpen ? "var(--text1)" : "var(--text2)",
                  transition: "all 0.2s ease"
                }}
              >
                + Add Required Spec <span style={{ marginLeft: "6px", fontSize: "0.7rem", opacity: 0.7 }}>{isFilterDropdownOpen ? "▲" : "▼"}</span>
              </button>

              {isFilterDropdownOpen && scrapedData && (
                <div style={{ 
                  position: "absolute", top: "100%", left: 0, marginTop: "8px",
                  background: "rgba(20, 20, 30, 0.85)", backdropFilter: "blur(12px)",
                  border: "1px solid rgba(255, 255, 255, 0.1)",
                  borderRadius: "8px", boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
                  zIndex: 999, width: "320px", maxHeight: "320px", overflowY: "auto"
                }}>
                  {scrapedData.filters.filter(f => f.isGolden).map((filter) => {
                    const isHovered = hoveredFilterKey === filter.filterKey;
                    return (
                      <div 
                        key={filter.filterKey}
                        onMouseEnter={() => setHoveredFilterKey(filter.filterKey)}
                        onMouseLeave={() => setHoveredFilterKey(null)}
                        style={{ 
                          padding: "10px 16px", borderBottom: "1px solid rgba(255,255,255,0.05)",
                          background: isHovered ? "rgba(156, 39, 176, 0.15)" : "transparent",
                          cursor: "pointer", position: "relative",
                          display: "flex", justifyContent: "space-between", alignItems: "center",
                          transition: "background 0.1s"
                        }}
                      >
                        <span style={{ fontSize: "0.85rem", color: isHovered ? "var(--text1)" : "var(--text2)" }}>{filter.filterName}</span>
                        <span style={{ fontSize: "0.7rem", color: isHovered ? "var(--primary)" : "var(--text4)", transform: isHovered ? "translateX(2px)" : "none", transition: "transform 0.2s" }}>▶</span>

                        {/* Sub-menu for values */}
                        {isHovered && (
                          <div style={{
                            position: "absolute", top: "-1px", left: "100%", marginLeft: "4px",
                            background: "rgba(25, 25, 35, 0.95)", backdropFilter: "blur(12px)",
                            border: "1px solid rgba(156, 39, 176, 0.3)",
                            borderRadius: "8px", boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
                            zIndex: 1000, minWidth: "220px", maxHeight: "320px", overflowY: "auto"
                          }}>
                            {filter.values.map(val => {
                              const isSelected = mandatoryFilters.some(mf => mf.filterKey === filter.filterKey && mf.value === val);
                              return (
                                <div 
                                  key={val}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (!isSelected) {
                                      setMandatoryFilters(prev => [...prev, {
                                        filterKey: filter.filterKey,
                                        filterName: filter.filterName,
                                        value: val,
                                        isGolden: true
                                      }]);
                                    }
                                    setIsFilterDropdownOpen(false);
                                    setHoveredFilterKey(null);
                                  }}
                                  style={{
                                    padding: "10px 16px", borderBottom: "1px solid rgba(255,255,255,0.05)",
                                    fontSize: "0.85rem", cursor: isSelected ? "default" : "pointer",
                                    display: "flex", justifyContent: "space-between", alignItems: "center",
                                    color: isSelected ? "var(--primary)" : "var(--text2)",
                                    opacity: isSelected ? 0.7 : 1
                                  }}
                                  onMouseEnter={(e) => {
                                    if (!isSelected) {
                                      e.currentTarget.style.background = "rgba(156, 39, 176, 0.2)";
                                      e.currentTarget.style.color = "var(--text1)";
                                    }
                                  }}
                                  onMouseLeave={(e) => {
                                    if (!isSelected) {
                                      e.currentTarget.style.background = "transparent";
                                      e.currentTarget.style.color = "var(--text2)";
                                    }
                                  }}
                                >
                                  <span>{val}</span>
                                  {isSelected && <span style={{ fontSize: "0.8rem" }}>✓</span>}
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
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

      {/* DEEP SEARCH ACTIVE VIEW */}
      {deepStatus !== "idle" && (
        <div className="card fade-in fade-in-d2">
          <div className="deep-search-panel">
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
                      Exploring depths {deepRange.min} to {deepRange.max} golden filter combinations...
                    </div>
                  </div>
                )}

                {deepStatus === "error" && (
                  <div className="err-box" style={{ marginTop: "1rem" }}>
                    {deepError}
                    <div style={{ display: "flex", gap: "1rem", marginTop: "1rem" }}>
                      <button
                        className="btn btn-deep"
                        onClick={() => handleDeepSearch(deepRange.min, deepRange.max)}
                        style={{ flex: 1 }}
                      >
                        Retry
                      </button>
                      <button
                        className="btn"
                        onClick={() => setDeepStatus("idle")}
                        style={{ 
                          flex: 1, 
                          background: "rgba(255,255,255,0.05)", 
                          color: "var(--text2)",
                          border: "1px solid var(--border)"
                        }}
                      >
                        ← Back to Options
                      </button>
                    </div>
                  </div>
                )}

                {deepStatus === "done" && deepResults && (
                  <>
                    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: "1.2rem" }}>
                      <button
                        onClick={() => setDeepStatus("idle")}
                        style={{
                          background: "transparent",
                          border: "1px solid var(--border)",
                          color: "var(--text2)",
                          padding: "6px 12px",
                          borderRadius: "6px",
                          cursor: "pointer",
                          fontSize: ".75rem",
                          display: "flex",
                          alignItems: "center",
                          gap: "6px",
                          transition: "all 0.2s"
                        }}
                        onMouseOver={(e) => e.currentTarget.style.borderColor = "var(--primary)"}
                        onMouseOut={(e) => e.currentTarget.style.borderColor = "var(--border)"}
                      >
                        <span>←</span> Back to Deep Search Options
                      </button>
                    </div>
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
                    
                    {deepRange.max <= 10 && (
                      <div style={{
                        background: "rgba(156, 39, 176, 0.08)",
                        border: "1px dashed rgba(156, 39, 176, 0.3)",
                        borderRadius: "8px",
                        padding: "0.8rem 1rem",
                        marginBottom: "1.5rem",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: "1rem",
                        flexWrap: "wrap"
                      }}>
                        <div style={{ fontSize: ".8rem", color: "var(--text2)" }}>
                          <strong style={{ color: "#9c27b0" }}>💡 Explore further?</strong> Standard search stopped at depth 10. Run an ultra-deep scan to find extreme combinations (11 to 15 filters).
                        </div>
                        <button 
                          onClick={() => handleDeepSearch(11, 15)}
                          style={{
                            background: "linear-gradient(135deg, var(--primary), #9c27b0)",
                            border: "none", color: "#fff", fontSize: ".75rem", fontWeight: "bold",
                            padding: "6px 14px", borderRadius: "6px", cursor: "pointer", boxShadow: "0 2px 6px rgba(0,0,0,0.2)"
                          }}
                        >
                          ⚡ Scan Depths 11 - 15
                        </button>
                      </div>
                    )}

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
                        {(() => {
                          const depths = [...new Set(deepResults.combinations.map(c => c.depth))].sort((a, b) => a - b);
                          const activeDepth = deepDepthTab !== null && depths.includes(deepDepthTab)
                            ? deepDepthTab
                            : depths[0];
                          const group = deepResults.combinations.filter(c => c.depth === activeDepth);
                          return (
                            <>
                              {/* Depth Tab Bar */}
                              <div className="depth-tab-bar">
                                {depths.map(d => {
                                  const cnt = deepResults.combinations.filter(c => c.depth === d).length;
                                  const isActive = d === activeDepth;
                                  return (
                                    <button
                                      key={d}
                                      className={`depth-tab-btn${isActive ? " depth-tab-active" : ""}`}
                                      onClick={() => setDeepDepthTab(d)}
                                    >
                                      <span className="depth-tab-label">Depth {d}</span>
                                      <span className="depth-tab-count">{cnt}</span>
                                    </button>
                                  );
                                })}
                              </div>

                              {/* Tab description */}
                              <div className="depth-tab-desc">
                                <span className="depth-badge">Depth {activeDepth}</span>
                                &nbsp;— {activeDepth} golden filter{activeDepth > 1 ? "s" : ""} applied
                                &nbsp;·&nbsp; <strong>{group.length}</strong> winning niche{group.length !== 1 ? "s" : ""}
                              </div>

                              {/* Combo cards for active depth */}
                              {group.map((r, i) => (
                                <OpportunityCard key={i} r={r} rank={i + 1} />
                              ))}
                            </>
                          );
                        })()}

                        {/* Progress log toggle */}
                        <details className="progress-log-details">
                          <summary>View search log ({deepResults.progress?.length ?? 0} entries)</summary>
                          <div className="progress-log">
                            {(deepResults.progress ?? []).map((line, i) => (
                              <div key={i} className={`log-line ${line.includes("✅") ? "log-win" :
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
            </div>
          )}
        </div>
    );
}
