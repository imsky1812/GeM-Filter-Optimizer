import { CaretDown, CheckCircle, MapPin, ArrowRight } from "@phosphor-icons/react";

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
          <div className="card-title">Category URL</div>
          <div className="card-desc">
            Drop in a category link from mkp.gem.gov.in.
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
          <span className="select-arrow"><CaretDown size={12} weight="bold" /></span>
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
              Scanning...
            </>
          ) : (
            <>Scan Category <ArrowRight size={15} weight="bold" /></>
          )}
        </button>
      </div>
      {scrapeStatus === "loading" && (
        <div className="loading">
          <span className="spin spin-muted" />
          Reading the category · pulling golden filters
          <br />
          <span className="card-desc">
            Fetching live data from GeM
          </span>
        </div>
      )}
      {scrapeError && <div className="err-box">{scrapeError}</div>}
      {scrapeStatus === "done" && scrapedData && (
        <div className="info-box">
          <CheckCircle size={14} weight="fill" className="inline-icon" />{" "}
          <strong>{scrapedData.filters.length} golden filters</strong> found across{" "}
          <strong>{scrapedData.totalResults.toLocaleString()} products</strong>
          {scrapedData.location && scrapedData.location !== "All India" && (
            <span className="loc-badge"><MapPin size={11} weight="fill" /> {scrapedData.location}</span>
          )}
        </div>
      )}
    </div>
  );
}
