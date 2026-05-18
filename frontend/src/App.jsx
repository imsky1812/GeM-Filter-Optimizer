import { useState, useEffect } from "react";
import "./index.css";

const BACKEND_URL = "/api";

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

  // Chain Hunt state
  const [chainStatus, setChainStatus] = useState("idle");
  const [chainResults, setChainResults] = useState(null);
  const [chainError, setChainError] = useState("");
  const [chainPathIdx, setChainPathIdx] = useState(0);

  // Surgical Strike state
  const [strikeUrl, setStrikeUrl] = useState("");
  const [strikeStatus, setStrikeStatus] = useState("idle"); // idle | loading | done | error
  const [strikeResults, setStrikeResults] = useState(null);
  const [strikeError, setStrikeError] = useState("");

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
    // Reset all modes when re-scraping
    setChainStatus("idle");
    setChainResults(null);
    setStrikeStatus("idle");
    setStrikeResults(null);

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

  const handleSurgicalStrike = async () => {
    if (!strikeUrl.trim() || !gemUrl.trim() || !priceNum) return;
    setStrikeStatus("loading");
    setStrikeResults(null);
    setStrikeError("");

    let normalizedUrl = gemUrl.trim();
    if (!normalizedUrl.startsWith("http://") && !normalizedUrl.startsWith("https://")) {
      normalizedUrl = "https://" + normalizedUrl;
    }

    try {
      const res = await fetch(`${BACKEND_URL}/surgical-strike`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_url: strikeUrl.trim(),
          category_url: normalizedUrl,
          target_price: priceNum,
          golden_filters: scrapedData
            ? scrapedData.filters.filter((f) => f.isGolden && f.filterKey !== "mse_applicable")
            : [],
          location: selectedLocation,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(
          typeof err.detail === "object"
            ? err.detail.message
            : err.detail || "Surgical strike failed"
        );
      }
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setStrikeResults(data);
      setStrikeStatus("done");
    } catch (e) {
      setStrikeError(e.message || "Surgical strike failed");
      setStrikeStatus("error");
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
                Enter your selling price and launch Smart L1 Hunt to find golden filter paths
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
      {/* ── SURGICAL STRIKE SECTION ── */}
      {scrapedData && priceNum > 0 && (
        <div className="card fade-in fade-in-d2">
          <div className="card-hdr">
            <div className="step-num" style={{ background: "linear-gradient(135deg, #ef4444, #dc2626)" }}>🎯</div>
            <div>
              <div className="card-title">Surgical Strike</div>
              <div className="card-desc">
                Target a specific competitor — paste their product URL to find which golden filters can exclude them
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: "12px", alignItems: "center", marginTop: "1rem" }}>
            <input
              type="text"
              value={strikeUrl}
              onChange={(e) => setStrikeUrl(e.target.value)}
              placeholder="Paste competitor's GeM product URL (e.g. mkp.gem.gov.in/.../product-detail/...)"
              onKeyDown={(e) => e.key === "Enter" && handleSurgicalStrike()}
              style={{ flex: 1 }}
              id="strike-url-input"
            />
            <button
              className="chain-hunt-trigger"
              onClick={handleSurgicalStrike}
              disabled={!strikeUrl.trim() || strikeStatus === "loading"}
              style={{ background: "linear-gradient(135deg, #ef4444, #dc2626)", whiteSpace: "nowrap" }}
            >
              {strikeStatus === "loading" ? (
                <><span className="spin" /> Analyzing...</>
              ) : (
                "🎯 Analyze Competitor"
              )}
            </button>
          </div>

          {/* Loading */}
          {strikeStatus === "loading" && (
            <div style={{ textAlign: "center", padding: "2rem 0" }}>
              <span className="spin spin-amber" />
              <div style={{ fontSize: ".85rem", color: "var(--text3)", marginTop: ".75rem" }}>
                Fetching competitor specs and matching against golden filters...
              </div>
            </div>
          )}

          {/* Error */}
          {strikeStatus === "error" && (
            <div className="err-box" style={{ marginTop: "1rem" }}>
              {strikeError}
              <div style={{ display: "flex", gap: "1rem", marginTop: "1rem" }}>
                <button className="btn btn-primary" onClick={handleSurgicalStrike} style={{ flex: 1 }}>Retry</button>
                <button className="btn" onClick={() => setStrikeStatus("idle")} style={{ flex: 1, background: "rgba(255,255,255,0.05)", color: "var(--text2)", border: "1px solid var(--border)" }}>Dismiss</button>
              </div>
            </div>
          )}

          {/* Results */}
          {strikeStatus === "done" && strikeResults && (
            <div style={{ marginTop: "1.25rem" }}>
              {/* Competitor Info Header */}
              <div style={{
                background: "rgba(239, 68, 68, 0.06)",
                border: "1px solid rgba(239, 68, 68, 0.2)",
                borderRadius: "10px",
                padding: "1rem 1.25rem",
                marginBottom: "1rem",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div style={{ fontSize: "0.7rem", color: "var(--text4)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                      Target Competitor
                    </div>
                    <div style={{ fontWeight: 700, fontSize: "0.95rem", marginTop: "2px" }}>
                      {strikeResults.competitorName || "Unknown Product"}
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    {strikeResults.competitorPrice && (
                      <div style={{ fontWeight: 700, fontSize: "1rem", color: "#ef4444" }}>
                        ₹{strikeResults.competitorPrice.toLocaleString()}
                      </div>
                    )}
                    <div style={{ fontSize: "0.65rem", color: "var(--text4)" }}>
                      {strikeResults.goldenMatches?.length ?? 0} golden filters matched · {strikeResults.totalApiCalls} API calls · {strikeResults.elapsed}s
                    </div>
                  </div>
                </div>
              </div>

              {/* Golden Filter Matches */}
              {strikeResults.goldenMatches?.length > 0 && (
                <div style={{ marginBottom: "1rem" }}>
                  <div style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--text2)", marginBottom: "0.5rem" }}>
                    Competitor's Golden Filter Specs:
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                    {strikeResults.goldenMatches.map((m, idx) => (
                      <div key={idx} style={{
                        background: "rgba(251, 191, 36, 0.1)",
                        border: "1px solid rgba(251, 191, 36, 0.25)",
                        borderRadius: "6px",
                        padding: "6px 10px",
                        fontSize: "0.75rem",
                      }}>
                        <span style={{ color: "var(--text3)" }}>{m.filterName}:</span>{" "}
                        <strong style={{ color: "var(--amber)" }}>{m.competitorValue}</strong>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Counter Filters */}
              {strikeResults.counterFilters?.length > 0 ? (
                <>
                  <div style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--text2)", marginBottom: "0.5rem" }}>
                    Counter Filters ({strikeResults.wins} wins, {strikeResults.untapped} untapped):
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    {strikeResults.counterFilters.map((cf, idx) => (
                      <div key={idx} style={{
                        display: "flex", alignItems: "center", gap: "12px",
                        background: cf.wouldWin
                          ? "rgba(16, 185, 129, 0.08)"
                          : cf.isUntapped
                          ? "rgba(251, 191, 36, 0.08)"
                          : "rgba(255,255,255,0.02)",
                        border: `1px solid ${cf.wouldWin ? "rgba(16, 185, 129, 0.25)" : cf.isUntapped ? "rgba(251, 191, 36, 0.25)" : "var(--border)"}`,
                        borderRadius: "8px",
                        padding: "0.75rem 1rem",
                      }}>
                        <div style={{
                          width: "32px", height: "32px", borderRadius: "50%",
                          background: cf.wouldWin ? "rgba(16, 185, 129, 0.15)" : cf.isUntapped ? "rgba(251, 191, 36, 0.15)" : "rgba(255,255,255,0.05)",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: "0.9rem", flexShrink: 0,
                        }}>
                          {cf.wouldWin ? "✅" : cf.isUntapped ? "★" : "→"}
                        </div>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: "0.8rem" }}>
                            Set <strong>{cf.filterName}</strong> = <strong style={{ color: "var(--green)" }}>{cf.counterValue}</strong>
                            <span style={{ color: "var(--text4)", fontSize: "0.7rem", marginLeft: "6px" }}>
                              (competitor has: {cf.competitorValue})
                            </span>
                          </div>
                          <div style={{ fontSize: "0.7rem", color: "var(--text3)", marginTop: "2px" }}>
                            {cf.isUntapped
                              ? "🏆 Zero competitors — untapped niche!"
                              : cf.wouldWin
                              ? `🏆 You'd be L1! Min price: ₹${cf.resultMinPrice?.toLocaleString()}, ${cf.resultTotal} products`
                              : `Min price: ₹${cf.resultMinPrice?.toLocaleString() ?? "?"}, ${cf.resultTotal} products`}
                          </div>
                        </div>
                        <div style={{
                          fontSize: "0.65rem", fontWeight: 700, padding: "3px 8px",
                          borderRadius: "4px",
                          background: cf.wouldWin ? "rgba(16, 185, 129, 0.2)" : cf.isUntapped ? "rgba(251, 191, 36, 0.2)" : "rgba(255,255,255,0.05)",
                          color: cf.wouldWin ? "var(--green)" : cf.isUntapped ? "var(--amber)" : "var(--text4)",
                        }}>
                          {cf.wouldWin ? "WIN" : cf.isUntapped ? "UNTAPPED" : "NO WIN"}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              ) : strikeResults.goldenMatches?.length === 0 ? (
                <div className="empty" style={{ marginTop: "1rem" }}>
                  <div className="empty-icon">⚠️</div>
                  <div className="empty-text">
                    Could not match any of the competitor's specs to golden filters.<br />
                    <span style={{ color: "var(--text4)", fontSize: ".8rem" }}>
                      The product page may have different spec names than the category filters.
                    </span>
                  </div>
                </div>
              ) : (
                <div className="empty" style={{ marginTop: "1rem" }}>
                  <div className="empty-icon">🎯</div>
                  <div className="empty-text">
                    No counter filters available — the competitor matches all golden filter values.
                  </div>
                </div>
              )}

              <button
                className="chain-hunt-trigger"
                onClick={handleSurgicalStrike}
                style={{ marginTop: "1.5rem", background: "linear-gradient(135deg, #ef4444, #dc2626)" }}
              >
                🔄 Re-analyze
              </button>
            </div>
          )}
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
                              
                              {/* Competitor Insights */}
                              {path.competitorInsights && (
                                <div style={{
                                  marginTop: "1.25rem",
                                  padding: "1rem",
                                  background: "var(--surface1)",
                                  borderRadius: "8px",
                                  border: "1px solid var(--border)",
                                }}>
                                  <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "0.75rem" }}>
                                    <span style={{ fontSize: "1.1rem" }}>🕵️</span>
                                    <span style={{ fontWeight: 600, fontSize: "0.85rem", color: "var(--text1)" }}>Competitor Insights</span>
                                  </div>
                                  <div style={{ fontSize: "0.75rem", color: "var(--text2)", marginBottom: "1rem", fontStyle: "italic" }}>
                                    {path.competitorInsights.message}
                                  </div>
                                  
                                  {(path.competitorInsights.l2 || path.competitorInsights.l3) && (
                                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                                      {path.competitorInsights.l2 && (
                                        <div style={{ padding: "0.75rem", background: "rgba(255,255,255,0.03)", borderRadius: "6px", border: "1px solid rgba(255,255,255,0.05)", overflow: "hidden" }}>
                                          <div style={{ fontSize: "0.65rem", color: "var(--amber)", fontWeight: 700, textTransform: "uppercase", marginBottom: "4px" }}>L2 Product</div>
                                          <div style={{ fontSize: "0.8rem", color: "var(--text1)", fontWeight: 600, marginBottom: "2px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={path.competitorInsights.l2.name}>{path.competitorInsights.l2.name}</div>
                                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "6px" }}>
                                            <span style={{ fontSize: "0.7rem", color: "var(--text3)", background: "rgba(255,255,255,0.1)", padding: "2px 6px", borderRadius: "4px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "50%" }}>{path.competitorInsights.l2.brand || "Unknown Brand"}</span>
                                            <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "#ef4444" }}>₹{path.competitorInsights.l2.price.toLocaleString()}</span>
                                          </div>
                                        </div>
                                      )}
                                      {path.competitorInsights.l3 && (
                                        <div style={{ padding: "0.75rem", background: "rgba(255,255,255,0.03)", borderRadius: "6px", border: "1px solid rgba(255,255,255,0.05)", overflow: "hidden" }}>
                                          <div style={{ fontSize: "0.65rem", color: "var(--amber)", fontWeight: 700, textTransform: "uppercase", marginBottom: "4px" }}>L3 Product</div>
                                          <div style={{ fontSize: "0.8rem", color: "var(--text1)", fontWeight: 600, marginBottom: "2px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={path.competitorInsights.l3.name}>{path.competitorInsights.l3.name}</div>
                                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "6px" }}>
                                            <span style={{ fontSize: "0.7rem", color: "var(--text3)", background: "rgba(255,255,255,0.1)", padding: "2px 6px", borderRadius: "4px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "50%" }}>{path.competitorInsights.l3.brand || "Unknown Brand"}</span>
                                            <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "#ef4444" }}>₹{path.competitorInsights.l3.price.toLocaleString()}</span>
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>
                              )}
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
