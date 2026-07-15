export default function UrlInput({
  gemUrl,
  setGemUrl,
  selectedLocation,
  setSelectedLocation,
  locations,
  scrapeStatus,
  onScrape,
  scrapeError,
  scrapedData
}) {
  return (
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
          onKeyDown={(e) => e.key === "Enter" && onScrape()}
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
          onClick={onScrape}
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
          <span className="card-desc">
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
  );
}
