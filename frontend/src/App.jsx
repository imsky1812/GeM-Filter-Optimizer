import { useState, useEffect, useRef } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
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


  // Chain Hunt state
  const [chainStatus, setChainStatus] = useState("idle"); // idle | loading | done | error
  const [chainResults, setChainResults] = useState(null);
  const [chainError, setChainError] = useState("");
  const [chainPathIdx, setChainPathIdx] = useState(0);

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
            ? scrapedData.filters.filter((f) => f.isGolden && f.filterKey !== "mse_applicable")
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

  const handleChainHunt = async () => {
    if (!gemUrl.trim() || !priceNum) return;
    setChainStatus("loading");
    setChainResults(null);
    setChainError("");
    setChainPathIdx(0);

    let normalizedUrl = gemUrl.trim();
    if (!normalizedUrl.startsWith("http://") && !normalizedUrl.startsWith("https://")) {
      normalizedUrl = "https://" + normalizedUrl;
    }

    try {
      const res = await fetch(`${BACKEND_URL}/chain-hunt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category_url: normalizedUrl,
          target_price: priceNum,
          golden_filters: scrapedData
            ? scrapedData.filters.filter((f) => f.isGolden && f.filterKey !== "mse_applicable")
            : [],
          location: selectedLocation,
          mandatory_filters: mandatoryFilters,
          excluded_filter_keys: ["mse_applicable"],
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(
          typeof err.detail === "object"
            ? err.detail.message
            : err.detail || "Chain hunt failed"
        );
      }
      const data = await res.json();
      setChainResults(data);
      setChainStatus("done");
    } catch (e) {
      setChainError(e.message || "Chain hunt failed");
      setChainStatus("error");
    }
  };

  const exportToPDF = () => {
    if (!deepResults || !deepResults.combinations) return;

    const doc = new jsPDF();
    const pageWidth = doc.internal.pageSize.width;

    doc.setFontSize(16);
    doc.setTextColor(20, 20, 30);
    doc.text("GeM L1 Filter Combinations", 14, 20);

    doc.setFontSize(10);
    doc.setTextColor(100, 100, 100);
    const splitUrl = doc.splitTextToSize(`Category URL: ${gemUrl}`, pageWidth - 28);
    doc.text(splitUrl, 14, 28);

    doc.text(`Target Price: Rs ${priceNum.toLocaleString()}`, 14, 38 + (splitUrl.length - 1) * 4);

    let currentY = 46 + (splitUrl.length - 1) * 4;

    deepResults.combinations.forEach((comboData, idx) => {
      doc.setFontSize(12);
      doc.setTextColor(0, 0, 0);
      const title = `Option ${idx + 1} (Score: ${comboData.score} | Competitors: ${comboData.competitorCount})`;
      doc.text(title, 14, currentY);

      const tableData = comboData.combo.map(c => [
        c.name || c.filterName || c.filterKey || "Filter",
        c.value
      ]);

      autoTable(doc, {
        startY: currentY + 4,
        head: [['Filter Name', 'Required Value']],
        body: tableData,
        theme: 'grid',
        headStyles: { fillColor: [108, 92, 231] },
        margin: { left: 14, right: 14 },
      });

      currentY = doc.lastAutoTable.finalY + 12;

      if (currentY > doc.internal.pageSize.height - 20) {
        doc.addPage();
        currentY = 20;
      }
    });

    doc.save("GeM_L1_Filters.pdf");
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
            Initializing Category · Extracting Golden Filters...
            <br />
            <span style={{ fontSize: ".7rem", color: "var(--text4)" }}>
              Fetching base definitions from GeM
            </span>
          </div>
        )}
        {scrapeError && <div className="err-box">{scrapeError}</div>}
        {scrapeStatus === "done" && scrapedData && (
          <div className="info-box">
            ✓ Initialized Category: Found{" "}
            <strong>{scrapedData.filters.length} Golden Filters</strong>
            {scrapedData.location && scrapedData.location !== "All India" && (
              <span className="loc-badge">📍 {scrapedData.location}</span>
            )}
            <span>
              {" "}
              ({scrapedData.totalResults.toLocaleString()} total products available in category)
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
              <div style={{ display: "flex", gap: "12px", marginLeft: "auto", flexWrap: "wrap" }}>
                <button
                  className="chain-hunt-trigger"
                  onClick={handleChainHunt}
                  disabled={scrapeStatus !== "done" || chainStatus === "loading"}
                >
                  {chainStatus === "loading" ? (
                    <><span className="spin" /> Hunting...</>
                  ) : (
                    "⚡ Smart L1 Hunt"
                  )}
                </button>
                <button
                  className="btn btn-primary"
                  onClick={() => handleDeepSearch(3, 10)}
                  disabled={scrapeStatus !== "done"}
                >
                  Deep Search (3-10)
                </button>
                <button
                  className="btn btn-primary"
                  onClick={() => handleDeepSearch(11, 15)}
                  disabled={scrapeStatus !== "done"}
                >
                  Ultra Deep (11-15)
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
                <div className="custom-scrollbar" style={{
                  position: "absolute", top: "100%", left: 0, marginTop: "8px",
                  background: "rgba(20, 20, 30, 0.95)", backdropFilter: "blur(12px)",
                  border: "1px solid rgba(255, 255, 255, 0.1)",
                  borderRadius: "8px", boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
                  zIndex: 999, width: "320px", maxHeight: "360px", overflowY: "auto", overflowX: "hidden"
                }}>
                  {scrapedData.filters.filter(f => f.isGolden && f.filterKey !== "mse_applicable").map((filter) => {
                    const isHovered = hoveredFilterKey === filter.filterKey;
                    return (
                      <div key={filter.filterKey} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                        <div
                          onClick={() => setHoveredFilterKey(isHovered ? null : filter.filterKey)}
                          style={{
                            padding: "10px 16px",
                            background: isHovered ? "rgba(156, 39, 176, 0.15)" : "transparent",
                            cursor: "pointer",
                            display: "flex", justifyContent: "space-between", alignItems: "center",
                            transition: "background 0.2s"
                          }}
                        >
                          <span style={{ fontSize: "0.85rem", color: isHovered ? "var(--text1)" : "var(--text2)", fontWeight: isHovered ? 600 : 400 }}>
                            {filter.filterName}
                          </span>
                          <span style={{ fontSize: "0.7rem", color: isHovered ? "var(--primary)" : "var(--text4)", transform: isHovered ? "rotate(90deg)" : "none", transition: "transform 0.2s" }}>
                            ▶
                          </span>
                        </div>

                        {/* Accordion values list */}
                        {isHovered && (
                          <div className="custom-scrollbar" style={{
                            background: "rgba(10, 10, 15, 0.6)",
                            maxHeight: "220px", overflowY: "auto", overflowX: "hidden",
                            borderTop: "1px solid rgba(255,255,255,0.02)"
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
                                    padding: "8px 16px 8px 24px", borderBottom: "1px solid rgba(255,255,255,0.02)",
                                    fontSize: "0.8rem", cursor: isSelected ? "default" : "pointer",
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
                    className="btn btn-primary"
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
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.2rem" }}>
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

                  <button
                    onClick={exportToPDF}
                    style={{
                      background: "rgba(108, 92, 231, 0.15)",
                      border: "1px solid var(--primary)",
                      color: "var(--text)",
                      padding: "6px 14px",
                      borderRadius: "6px",
                      cursor: "pointer",
                      fontSize: ".75rem",
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                      fontWeight: 600,
                      transition: "all 0.2s"
                    }}
                    onMouseOver={(e) => e.currentTarget.style.background = "rgba(108, 92, 231, 0.25)"}
                    onMouseOut={(e) => e.currentTarget.style.background = "rgba(108, 92, 231, 0.15)"}
                  >
                    Export as PDF 📄
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
                      className="btn btn-primary"
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

      {/* CHAIN HUNT RESULTS */}
      {chainStatus !== "idle" && (
        <div className="card fade-in fade-in-d2">
          <div className="chain-hunt-panel">
            {chainStatus === "loading" && (
              <div className="chain-loading">
                <span className="spin spin-amber" />
                <div className="chain-loading-title">⚡ Sequential L1 Chain Hunt Running...</div>
                <div className="chain-loading-sub">
                  Iteratively eliminating each L1 blocker one-by-one.
                  Re-scraping the market after every filter change.
                  This may take 2–5 minutes.
                </div>
                <div className="chain-loading-bar">
                  <div className="chain-loading-fill" />
                </div>
              </div>
            )}

            {chainStatus === "error" && (
              <div className="err-box" style={{ marginTop: "1rem" }}>
                {chainError}
                <div style={{ display: "flex", gap: "1rem", marginTop: "1rem" }}>
                  <button className="btn btn-primary" onClick={handleChainHunt} style={{ flex: 1 }}>Retry</button>
                  <button className="btn" onClick={() => setChainStatus("idle")} style={{ flex: 1, background: "rgba(255,255,255,0.05)", color: "var(--text2)", border: "1px solid var(--border)" }}>← Back</button>
                </div>
              </div>
            )}

            {chainStatus === "done" && chainResults && (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                  <button
                    onClick={() => setChainStatus("idle")}
                    style={{ background: "transparent", border: "1px solid var(--border)", color: "var(--text2)", padding: "6px 12px", borderRadius: "6px", cursor: "pointer", fontSize: ".75rem", display: "flex", alignItems: "center", gap: "6px", transition: "all 0.2s" }}
                    onMouseOver={(e) => e.currentTarget.style.borderColor = "var(--primary)"}
                    onMouseOut={(e) => e.currentTarget.style.borderColor = "var(--border)"}
                  >
                    <span>←</span> Back
                  </button>
                  <div style={{ fontSize: ".7rem", color: "var(--text3)" }}>
                    ⚡ Sequential Chain Elimination
                  </div>
                </div>

                {/* Summary stats */}
                <div className="chain-summary">
                  <div className="chain-stat chain-stat-win">
                    <div className="chain-stat-val">{chainResults.winningPaths?.length ?? 0}</div>
                    <div className="chain-stat-lbl">Paths Found</div>
                  </div>
                  <div className="chain-stat chain-stat-api">
                    <div className="chain-stat-val">{chainResults.totalApiCalls ?? 0}</div>
                    <div className="chain-stat-lbl">API Calls</div>
                  </div>
                  <div className="chain-stat">
                    <div className="chain-stat-val">{chainResults.goldenFilterCount ?? 0}</div>
                    <div className="chain-stat-lbl">Golden Filters</div>
                  </div>
                  <div className="chain-stat">
                    <div className="chain-stat-val" style={{
                      color: chainResults.status === "WIN" ? "var(--green)" : chainResults.status === "PARTIAL" ? "var(--amber)" : "var(--red)"
                    }}>
                      {chainResults.status === "WIN" ? "✓ WIN" : chainResults.status === "PARTIAL" ? "⚠ STUCK" : "✗ FAIL"}
                    </div>
                    <div className="chain-stat-lbl">Status</div>
                  </div>
                </div>

                {/* ── STUCK / NO L1 PATH BANNER ── */}
                {chainResults.status !== "WIN" && (
                  <div style={{
                    background: "linear-gradient(135deg, rgba(239, 68, 68, 0.08) 0%, rgba(251, 191, 36, 0.06) 100%)",
                    border: "1px solid rgba(239, 68, 68, 0.25)",
                    borderRadius: "12px",
                    padding: "1.25rem 1.5rem",
                    marginBottom: "1.25rem",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "1rem" }}>
                      <div style={{
                        width: "40px", height: "40px", borderRadius: "50%",
                        background: "rgba(239, 68, 68, 0.15)", display: "flex",
                        alignItems: "center", justifyContent: "center", fontSize: "1.3rem", flexShrink: 0
                      }}>🚫</div>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: "1rem", color: "#ef4444" }}>
                          No Path to L1 at ₹{priceNum.toLocaleString()}
                        </div>
                        <div style={{ fontSize: "0.78rem", color: "var(--text3)", marginTop: "2px" }}>
                          All golden filters exhausted — no combination can make your product the cheapest.
                        </div>
                      </div>
                    </div>

                    <div style={{
                      display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.75rem",
                      background: "rgba(0,0,0,0.15)", borderRadius: "8px", padding: "0.75rem",
                    }}>
                      <div style={{ textAlign: "center" }}>
                        <div style={{ fontSize: "0.65rem", color: "var(--text4)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "4px" }}>
                          Your Price
                        </div>
                        <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text1)" }}>
                          ₹{priceNum.toLocaleString()}
                        </div>
                      </div>
                      <div style={{ textAlign: "center" }}>
                        <div style={{ fontSize: "0.65rem", color: "var(--text4)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "4px" }}>
                          Best Achievable Floor
                        </div>
                        <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--amber)" }}>
                          ₹{(chainResults.bestAchievablePrice ?? 0).toLocaleString()}
                        </div>
                      </div>
                      <div style={{ textAlign: "center" }}>
                        <div style={{ fontSize: "0.65rem", color: "var(--text4)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "4px" }}>
                          Gap (Unreachable)
                        </div>
                        <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#ef4444" }}>
                          ₹{(priceNum - (chainResults.bestAchievablePrice ?? 0)).toLocaleString()}
                        </div>
                      </div>
                    </div>

                    {chainResults.bestAchievablePrice && (
                      <div style={{
                        marginTop: "0.75rem", padding: "0.6rem 0.75rem",
                        background: "rgba(251, 191, 36, 0.08)", borderRadius: "6px",
                        border: "1px solid rgba(251, 191, 36, 0.15)",
                        fontSize: "0.78rem", color: "var(--text2)",
                        display: "flex", alignItems: "center", gap: "8px",
                      }}>
                        <span style={{ fontSize: "1rem" }}>💡</span>
                        <span>
                          To become L1 in this category, you would need to list your product
                          below <strong style={{ color: "var(--amber)" }}>
                            ₹{chainResults.bestAchievablePrice.toLocaleString()}
                          </strong> (the highest price floor achievable through spec filters).
                        </span>
                      </div>
                    )}
                  </div>
                )}

                {(!chainResults.winningPaths || chainResults.winningPaths.length === 0) ? (
                  <div className="empty" style={{ marginTop: "1rem" }}>
                    <div className="empty-icon">🔍</div>
                    <div className="empty-text">
                      No filter combinations found.<br />
                      <span style={{ color: "var(--text4)", fontSize: ".8rem" }}>
                        The current L1 products cannot be bypassed with available golden filters.
                        Try lowering your price or check if additional filter options exist.
                      </span>
                    </div>
                  </div>
                ) : (
                  <>
                    {/* Path selector tabs */}
                    <div style={{ fontSize: ".72rem", color: "var(--text3)", marginBottom: ".75rem" }}>
                      Found <strong>{chainResults.winningPaths.length}</strong> {chainResults.status === "WIN" ? "winning" : ""} path{chainResults.winningPaths.length !== 1 ? "s" : ""}{chainResults.status === "WIN" ? " to L1" : ""} — select one to view the elimination chain:
                    </div>
                    <div className="chain-path-tabs">
                      {chainResults.winningPaths.map((path, idx) => (
                        <button
                          key={idx}
                          className={`chain-path-tab ${chainPathIdx === idx ? "chain-path-tab-active" : ""}`}
                          onClick={() => setChainPathIdx(idx)}
                        >
                          Path {idx + 1}
                          <span className="chain-path-badge">
                            {path.iterations?.length ?? 0} step{(path.iterations?.length ?? 0) !== 1 ? "s" : ""}
                          </span>
                          {path.isUntapped && <span style={{ color: "var(--amber)", fontSize: ".65rem" }}>★</span>}
                        </button>
                      ))}
                    </div>

                    {/* Active path timeline */}
                    {(() => {
                      const path = chainResults.winningPaths[chainPathIdx];
                      if (!path) return null;
                      const steps = path.iterations || [];
                      return (
                        <div className="chain-timeline">
                          {steps.map((step, idx) => (
                            <div key={idx} className="chain-step" style={{ animationDelay: `${idx * 0.08}s` }}>
                              {/* Node circle */}
                              <div className="chain-node chain-node-blocker">{idx + 1}</div>

                              {/* Blocker card */}
                              <div className="chain-blocker-card">
                                <div className="chain-blocker-header">
                                  <div className="chain-blocker-tag">⛔ Competitors at Floor Price</div>
                                  <div className="chain-blocker-price">₹{step.prevMinPrice?.toLocaleString()}</div>
                                </div>
                                <div className="chain-blocker-name" style={{ color: "var(--text3)", fontStyle: "italic", fontSize: "0.8rem" }}>
                                  Current market minimum price
                                </div>

                                {/* Filter action */}
                                <div className="chain-filter-action">
                                  <div className="chain-filter-icon">🎯</div>
                                  <div className="chain-filter-text">
                                    Apply <strong>"{step.filterApplied?.filterName}"</strong> = <strong>"{step.filterApplied?.value}"</strong>
                                  </div>
                                </div>

                                {/* New L1 preview */}
                                {step.result === "LATERAL" ? (
                                  <div className="chain-new-l1" style={{ color: "var(--text3)", opacity: 0.8 }}>
                                    → Pool narrowed to <strong>{step.newTotal}</strong> products
                                    <span style={{ marginLeft: "auto", fontSize: ".6rem", background: "rgba(255,255,255,0.06)", padding: "2px 6px", borderRadius: "4px" }}>
                                      LATERAL
                                    </span>
                                  </div>
                                ) : step.newMinPrice !== null && step.newMinPrice !== undefined && (
                                  <div className="chain-new-l1">
                                    → Price floor raised to: <strong>₹{step.newMinPrice?.toLocaleString()}</strong>
                                    <span style={{ marginLeft: "auto", fontSize: ".65rem" }}>
                                      {step.newTotal} products remain
                                    </span>
                                  </div>
                                )}
                                {step.result === "UNTAPPED" && (
                                  <div className="chain-new-l1" style={{ color: "var(--amber)" }}>
                                    → Niche is now <strong>untapped</strong> — zero competitors!
                                  </div>
                                )}
                              </div>
                            </div>
                          ))}

                          {/* Victory/Partial card */}
                          <div className="chain-step" style={{ animationDelay: `${steps.length * 0.08}s` }}>
                            <div className={`chain-node ${path.isUntapped ? "chain-node-untapped" : path.status === "PARTIAL" ? "chain-node-partial" : "chain-node-victory"}`}>
                                {path.status === "PARTIAL" ? "⚠" : "✓"}
                            </div>
                            <div className="chain-victory-card" style={path.status === "PARTIAL" ? { borderColor: "var(--amber)", background: "rgba(251, 191, 36, 0.05)" } : {}}>
                              <div className="chain-victory-header">
                                <div className="chain-victory-tag">
                                  {path.isUntapped 
                                    ? "🏆 Untapped Niche" 
                                    : path.status === "PARTIAL" 
                                        ? "⚠ Stuck - Cannot Reach Target" 
                                        : "🏆 You Are L1!"}
                                </div>
                                <div className="chain-victory-price">
                                  {path.isUntapped
                                    ? "No Competitors"
                                    : `Max Price Reached: ₹${path.nicheMinPrice?.toLocaleString() ?? "?"}`}
                                </div>
                              </div>
                              <div className="chain-victory-detail">
                                {path.status === "PARTIAL" ? (
                                    <>
                                        After <strong>{steps.length} elimination{steps.length !== 1 ? "s" : ""}</strong>, 
                                        the highest price floor reachable is <strong>₹{path.nicheMinPrice?.toLocaleString() ?? "?"}</strong>. 
                                        No further filters can raise the price above your target of <strong>₹{priceNum.toLocaleString()}</strong>.
                                    </>
                                ) : (
                                    <>
                                        After <strong>{steps.length} elimination{steps.length !== 1 ? "s" : ""}</strong>,
                                        your product at <strong>₹{priceNum.toLocaleString()}</strong> is now the cheapest.
                                        {!path.isUntapped && path.nicheMinPrice && (
                                        <> Price gap: <strong>₹{(path.nicheMinPrice - priceNum).toLocaleString()}</strong></>
                                        )}
                                        {path.totalProducts > 0 && (
                                        <> · <strong>{path.totalProducts}</strong> products in niche</>
                                        )}
                                    </>
                                )}
                              </div>
                              <div className="chain-active-filters">
                                {Object.entries(path.activeFilters || {}).map(([key, val]) => {
                                  const gf = scrapedData?.filters?.find(f => f.filterKey === key);
                                  return (
                                    <div key={key} className="chain-filter-chip">
                                      {gf?.filterName || key}: <strong>{val}</strong>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })()}

                    <button
                      className="chain-hunt-trigger"
                      onClick={handleChainHunt}
                      style={{ marginTop: "1.5rem" }}
                    >
                      🔄 Re-run Chain Hunt
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
