import { useState, useEffect } from "react";
import "./index.css";

// Import sub-components
import Header from "./components/Header.jsx";
import UrlInput from "./components/UrlInput.jsx";
import PriceInput from "./components/PriceInput.jsx";
import SurgicalStrike from "./components/SurgicalStrike.jsx";
import ChainHuntResults from "./components/ChainHuntResults.jsx";
import CompetitorSpecsModal from "./components/CompetitorSpecsModal.jsx";

const BACKEND_URL = "/api";

export default function App() {
  const [gemUrl, setGemUrl] = useState("");
  const [sellerPrice, setSellerPrice] = useState("");
  const [scrapedData, setScrapedData] = useState(null);
  const [scrapeStatus, setScrapeStatus] = useState("idle");
  const [scrapeError, setScrapeError] = useState("");
  const [locations, setLocations] = useState(["All India"]);
  const [selectedLocation, setSelectedLocation] = useState("All India");

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
  
  // Competitor Specs Modal State
  const [selectedCompetitor, setSelectedCompetitor] = useState(null);
  const [competitorSpecs, setCompetitorSpecs] = useState(null);
  const [isFetchingSpecs, setIsFetchingSpecs] = useState(false);
  const [competitorSpecsError, setCompetitorSpecsError] = useState("");

  const handleFetchCompetitorSpecs = async (competitor, role) => {
    if (!competitor.url) {
      alert("Product URL not available. Ensure you run the Chain Hunt to get product URLs.");
      return;
    }
    
    setSelectedCompetitor({ ...competitor, role });
    setCompetitorSpecs(null);
    setIsFetchingSpecs(true);
    setCompetitorSpecsError("");
    
    try {
      const res = await fetch(`${BACKEND_URL}/product-specs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_url: competitor.url }),
      });
      
      if (!res.ok) {
        throw new Error("Failed to fetch product specifications");
      }
      
      const data = await res.json();
      setCompetitorSpecs(data.specs || {});
    } catch (e) {
      setCompetitorSpecsError(e.message || "Failed to fetch specs");
    } finally {
      setIsFetchingSpecs(false);
    }
  };

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

  return (
    <div className="app">
      <Header />

      <UrlInput
        gemUrl={gemUrl}
        setGemUrl={setGemUrl}
        selectedLocation={selectedLocation}
        setSelectedLocation={setSelectedLocation}
        locations={locations}
        scrapeStatus={scrapeStatus}
        onScrape={handleScrape}
        scrapeError={scrapeError}
        scrapedData={scrapedData}
      />

      {scrapedData && (
        <PriceInput
          sellerPrice={sellerPrice}
          setSellerPrice={setSellerPrice}
          scrapedData={scrapedData}
          minCatPrice={minCatPrice}
          priceNum={priceNum}
          chainStatus={chainStatus}
          onChainHunt={handleChainHunt}
          mandatoryFilters={mandatoryFilters}
          setMandatoryFilters={setMandatoryFilters}
          isFilterDropdownOpen={isFilterDropdownOpen}
          setIsFilterDropdownOpen={setIsFilterDropdownOpen}
          hoveredFilterKey={hoveredFilterKey}
          setHoveredFilterKey={setHoveredFilterKey}
        />
      )}

      {scrapedData && priceNum > 0 && (
        <SurgicalStrike
          strikeUrl={strikeUrl}
          setStrikeUrl={setStrikeUrl}
          strikeStatus={strikeStatus}
          setStrikeStatus={setStrikeStatus}
          strikeResults={strikeResults}
          strikeError={strikeError}
          onSurgicalStrike={handleSurgicalStrike}
          priceNum={priceNum}
        />
      )}

      {chainStatus !== "idle" && (
        <ChainHuntResults
          chainStatus={chainStatus}
          setChainStatus={setChainStatus}
          chainResults={chainResults}
          chainError={chainError}
          onChainHunt={handleChainHunt}
          priceNum={priceNum}
          chainPathIdx={chainPathIdx}
          setChainPathIdx={setChainPathIdx}
          scrapedData={scrapedData}
          onFetchCompetitorSpecs={handleFetchCompetitorSpecs}
        />
      )}

      <CompetitorSpecsModal
        selectedCompetitor={selectedCompetitor}
        setSelectedCompetitor={setSelectedCompetitor}
        competitorSpecs={competitorSpecs}
        isFetchingSpecs={isFetchingSpecs}
        competitorSpecsError={competitorSpecsError}
        scrapedData={scrapedData}
      />
    </div>
  );
}
