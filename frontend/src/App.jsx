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

  // Targeted Elimination state
  const [surpassUrl, setSurpassUrl] = useState("");
  const [surpassResults, setSurpassResults] = useState(null);
  const [surpassStatus, setSurpassStatus] = useState("idle");
  const [surpassError, setSurpassError] = useState("");

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
    setSurpassResults(null);
    setSurpassUrl("");
    setSurpassError("");

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

  const handleSurpass = async () => {
    if (!surpassUrl.trim() || !gemUrl.trim()) return;
    setSurpassStatus("loading");
    setSurpassResults(null);
    setSurpassError("");

    try {
      const res = await fetch(`${BACKEND_URL}/surpass`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category_url: gemUrl.trim(),
          competitor_url: surpassUrl.trim(),
          seller_price: priceNum,
          location: selectedLocation,
          golden_filters: scrapedData?.filters?.filter(f => f.isGolden) || []
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Competitor analysis failed");
      }
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setSurpassResults(data);
      setSurpassStatus("done");
    } catch (e) {
      setSurpassError(e.message || "Targeted search failed");
      setSurpassStatus("error");
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
              <div style={{ display: "flex", gap: "12px", marginLeft: "auto" }}>
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
                  Ultra Deep Search(11-15)
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
                  {scrapedData.filters.filter(f => f.isGolden).map((filter) => {
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

                    <div className="surpass-card">
                      <div className="surpass-title">
                        <span>🎯</span> Surgical Competitive Strike
                      </div>
                      <div className="surpass-desc">
                        Analyze any competitor product link. We'll find the exact filter to <strong>eliminate</strong> cheap competitors or the blueprint of specs to <strong>join and win</strong> a high-priced niche.
                      </div>
                      <div className="surpass-input-group">
                        <input
                          type="text"
                          placeholder="https://mkp.gem.gov.in/interactive-panels-with-cpu/p-..."
                          value={surpassUrl}
                          onChange={(e) => setSurpassUrl(e.target.value)}
                        />
                        <button
                          className="btn btn-surpass"
                          onClick={handleSurpass}
                          disabled={surpassStatus === "loading" || !surpassUrl.trim()}
                        >
                          {surpassStatus === "loading" ? <span className="spin" /> : "Fetch Strategy"}
                        </button>
                      </div>

                      {surpassError && (
                        <div className="err-box" style={{ marginTop: "0.5rem" }}>
                          {surpassError}
                        </div>
                      )}

                      {surpassResults && (
                        <div style={{ marginTop: "1.5rem" }}>
                          {/* Competitor Info Header */}
                          <div style={{ 
                            padding: "1rem", 
                            background: "var(--surface3)", 
                            borderRadius: "8px", 
                            border: "1px solid var(--border)",
                            marginBottom: "1.25rem"
                          }}>
                            <div style={{ fontSize: ".65rem", color: "var(--text4)", fontWeight: 800, textTransform: "uppercase", letterSpacing: ".1em", marginBottom: "4px" }}>
                              Targeted Competitor
                            </div>
                            <div style={{ fontSize: ".9rem", fontWeight: 700, color: "var(--text)", marginBottom: "8px", lineHeight: 1.3 }}>
                              {surpassResults.competitor?.name || "Unknown Product"}
                            </div>
                            <div style={{ display: "flex", gap: "12px", alignItems: "baseline" }}>
                              <div style={{ fontSize: "1.2rem", fontWeight: 800, color: "var(--red)" }}>
                                ₹{surpassResults.competitor?.price?.toLocaleString() || "???"}
                              </div>
                              <a href={surpassResults.competitor?.url} target="_blank" rel="noreferrer" style={{ fontSize: ".7rem", color: "var(--accent2)", textDecoration: "none" }}>
                                View on GeM ↗
                              </a>
                            </div>
                          </div>

                          {/* Competitor Specs Section */}
                          {surpassResults.matchedSpecs && surpassResults.matchedSpecs.length > 0 && (
                            <div style={{ marginBottom: "1.5rem" }}>
                              <div style={{ fontSize: ".65rem", color: "var(--text3)", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".1em", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "8px" }}>
                                <span style={{ width: "12px", height: "1px", background: "var(--border)" }}></span>
                                Competitor Active Specs
                                <span style={{ width: "12px", height: "1px", background: "var(--border)" }}></span>
                              </div>
                              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                                {surpassResults.matchedSpecs.map((spec, idx) => (
                                  <div key={idx} style={{ 
                                    background: "var(--bg2)", 
                                    padding: "8px 12px", 
                                    borderRadius: "6px", 
                                    border: "1px solid var(--border2)",
                                    fontSize: ".75rem"
                                  }}>
                                    <div style={{ color: "var(--text4)", fontSize: ".6rem", fontWeight: 600, textTransform: "uppercase" }}>{spec.name}</div>
                                    <div style={{ color: "var(--text2)", fontWeight: 500 }}>{spec.value}</div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Match Strategy Section (Joining a high-priced niche) */}
                          {surpassResults.matchStrategy && (
                            <div style={{ marginBottom: "1.5rem" }}>
                              <div style={{ fontSize: ".65rem", color: "var(--text3)", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".1em", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "8px" }}>
                                <span style={{ width: "12px", height: "1px", background: "var(--border)" }}></span>
                                Niche Winning Option (Join & Win)
                                <span style={{ width: "12px", height: "1px", background: "var(--border)" }}></span>
                              </div>
                              <div className="killer-card" style={{ borderLeftColor: "var(--accent)", background: "var(--accent-glow)" }}>
                                <div className="killer-info">
                                  <div className="killer-tag" style={{ background: "var(--accent)", color: "#fff" }}>L1 Niche Entry</div>
                                  <div className="killer-label" style={{ fontSize: ".9rem", marginTop: "4px" }}>
                                    Match all filters of this <strong>high-priced product</strong> to dominate its niche.
                                  </div>
                                  <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "10px" }}>
                                    {surpassResults.matchStrategy.filters.map((f, i) => (
                                      <div key={i} style={{ 
                                        background: "var(--bg3)", 
                                        padding: "4px 8px", 
                                        borderRadius: "4px", 
                                        fontSize: ".65rem",
                                        border: "1px solid rgba(108, 92, 231, 0.3)"
                                      }}>
                                        <span style={{ color: "var(--text3)" }}>{f.name}:</span> <span style={{ color: "var(--accent2)", fontWeight: 700 }}>{f.value}</span>
                                      </div>
                                    ))}
                                  </div>
                                  <div style={{ fontSize: ".7rem", color: "var(--text2)", marginTop: "10px", fontStyle: "italic" }}>
                                    Your price (₹{priceNum.toLocaleString()}) is significantly lower than the current L1 in this specific niche.
                                  </div>
                                </div>
                                <div className="killer-price">
                                  <div className="killer-price-val" style={{ color: "var(--accent2)" }}>
                                    ₹{surpassResults.matchStrategy.minCompetitorPrice?.toLocaleString() || "???"}
                                  </div>
                                  <div className="killer-price-lbl">Current Niche L1</div>
                                </div>
                              </div>
                            </div>
                          )}

                          {/* Strategies Section (Elimination) */}
                          <div style={{ fontSize: ".65rem", color: "var(--text3)", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".1em", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "8px" }}>
                            <span style={{ width: "12px", height: "1px", background: "var(--border)" }}></span>
                            {surpassResults.competitor?.price < priceNum ? "Elimination Strategy (Way Forward)" : "Alternative Surgical Strikes"}
                            <span style={{ width: "12px", height: "1px", background: "var(--border)" }}></span>
                          </div>

                          {surpassResults.strategies && surpassResults.strategies.length === 0 ? (
                            <div className="warn-box">
                              No single-step filters found to eliminate this competitor. They match all your golden filter options.
                            </div>
                          ) : (
                            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                              {(surpassResults.strategies || []).map((s, idx) => (
                                <div key={idx} className="killer-card" style={{ borderLeftColor: "var(--green)" }}>
                                  <div className="killer-info">
                                    <div className="killer-tag" style={{ background: "var(--green-glow)", color: "var(--green)" }}>Killer Filter Found</div>
                                    <div className="killer-label" style={{ fontSize: ".9rem", marginTop: "4px" }}>
                                      Change <strong>{s.filterName}</strong> to <span style={{ color: "var(--green)", fontWeight: 800 }}>{s.value}</span>
                                    </div>
                                  </div>
                                  <div className="killer-price">
                                    <div className="killer-price-val" style={{ color: "var(--green)" }}>
                                      {s.minCompetitorPrice === null ? "Untapped" : `₹${s.minCompetitorPrice.toLocaleString()}`}
                                    </div>
                                    <div className="killer-price-lbl">New Niche Min Price</div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
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
