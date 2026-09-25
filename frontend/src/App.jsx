import { useState, useEffect, useRef } from "react";
import { ArrowLeft } from "@phosphor-icons/react";
import "./index.css";

// Import sub-components
import Header from "./components/Header.jsx";
import UrlInput from "./components/UrlInput.jsx";
import PriceInput from "./components/PriceInput.jsx";
import SurgicalStrike from "./components/SurgicalStrike.jsx";
import ChainHuntResults from "./components/ChainHuntResults.jsx";
import CompetitorSpecsModal from "./components/CompetitorSpecsModal.jsx";
import StepIndicator from "./components/StepIndicator.jsx";
import ToolChoice from "./components/ToolChoice.jsx";
import Landing from "./components/Landing.jsx";
import usePointerSpotlight from "./usePointerSpotlight.js";

const BACKEND_URL = "/api";

// Error bodies aren't always JSON (e.g. a proxy's HTML 502 page), so fall
// back to the status code instead of surfacing a JSON parse error.
async function readError(res, fallback) {
  try {
    const err = await res.json();
    const detail = typeof err.detail === "object" ? err.detail?.message : err.detail;
    return detail || fallback;
  } catch {
    return `${fallback} (HTTP ${res.status})`;
  }
}

const withProtocol = (url) => {
  const trimmed = url.trim();
  return trimmed.startsWith("http://") || trimmed.startsWith("https://")
    ? trimmed
    : "https://" + trimmed;
};

export default function App() {
  usePointerSpotlight(); // cursor glow, landing and wizard alike
  const [view, setView] = useState("landing"); // "landing" | "app"
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

  // Wizard step state
  const [currentStep, setCurrentStep] = useState(1);
  const [furthestStep, setFurthestStep] = useState(1);
  const [activeTool, setActiveTool] = useState(null); // null | "chainHunt" | "strike"

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

  // In-flight requests. Starting a request aborts the previous one of the
  // same kind, and starting over aborts all of them, so a slow earlier
  // response (a chain hunt takes minutes) can't land on top of newer state.
  const scrapeRequest = useRef(null);
  const chainRequest = useRef(null);
  const strikeRequest = useRef(null);

  const beginRequest = (ref) => {
    ref.current?.abort();
    ref.current = new AbortController();
    return ref.current.signal;
  };

  const abortRequest = (ref) => {
    ref.current?.abort();
    ref.current = null;
  };

  const goToStep = (step) => {
    setCurrentStep(step);
    setFurthestStep((f) => Math.max(f, step));
  };

  const handleStartOver = () => {
    abortRequest(scrapeRequest);
    abortRequest(chainRequest);
    abortRequest(strikeRequest);
    setGemUrl("");
    setSellerPrice("");
    setScrapedData(null);
    setScrapeStatus("idle");
    setScrapeError("");
    setChainStatus("idle");
    setChainResults(null);
    setChainError("");
    setChainPathIdx(0);
    setStrikeUrl("");
    setStrikeStatus("idle");
    setStrikeResults(null);
    setStrikeError("");
    setMandatoryFilters([]);
    setActiveTool(null);
    setCurrentStep(1);
    setFurthestStep(1);
    setSelectedCompetitor(null);
    setCompetitorSpecs(null);
    setIsFetchingSpecs(false);
    setCompetitorSpecsError("");
  };

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
      if (!res.ok) throw new Error(await readError(res, "Failed to fetch product specifications"));

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
    // Re-scraping resets both tools, so their pending responses are stale too
    abortRequest(chainRequest);
    abortRequest(strikeRequest);
    const signal = beginRequest(scrapeRequest);

    setScrapeStatus("loading");
    setScrapeError("");
    setScrapedData(null);
    setChainStatus("idle");
    setChainResults(null);
    setStrikeStatus("idle");
    setStrikeResults(null);
    setFurthestStep(1);

    const normalizedUrl = withProtocol(gemUrl);
    if (normalizedUrl !== gemUrl.trim()) setGemUrl(normalizedUrl);

    try {
      const res = await fetch(`${BACKEND_URL}/scrape`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: normalizedUrl, location: selectedLocation }),
        signal,
      });
      if (!res.ok) throw new Error(await readError(res, "Backend error"));
      const parsed = await res.json();
      setScrapedData(parsed);
      setScrapeStatus("done");
      goToStep(2);
    } catch (e) {
      if (e.name === "AbortError") return;
      setScrapeError(e.message || "Failed to scrape");
      setScrapeStatus("error");
    }
  };

  // The scrape resolves short category aliases to the real category URL, so
  // later steps must use what came back, not what was typed.
  const categoryUrlForRequest = () => scrapedData?.url || withProtocol(gemUrl);

  const goldenFiltersForRequest = () =>
    scrapedData
      ? scrapedData.filters.filter((f) => f.isGolden && f.filterKey !== "mse_applicable")
      : [];

  const handleSurgicalStrike = async () => {
    if (!strikeUrl.trim() || !gemUrl.trim() || !priceNum) return;
    const signal = beginRequest(strikeRequest);
    setActiveTool("strike");
    goToStep(4);
    setStrikeStatus("loading");
    setStrikeResults(null);
    setStrikeError("");

    try {
      const res = await fetch(`${BACKEND_URL}/surgical-strike`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_url: strikeUrl.trim(),
          category_url: categoryUrlForRequest(),
          target_price: priceNum,
          golden_filters: goldenFiltersForRequest(),
          location: selectedLocation,
        }),
        signal,
      });
      if (!res.ok) throw new Error(await readError(res, "Surgical strike failed"));
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setStrikeResults(data);
      setStrikeStatus("done");
    } catch (e) {
      if (e.name === "AbortError") return;
      setStrikeError(e.message || "Surgical strike failed");
      setStrikeStatus("error");
    }
  };

  const handleChainHunt = async () => {
    if (!gemUrl.trim() || !priceNum) return;
    const signal = beginRequest(chainRequest);
    setActiveTool("chainHunt");
    goToStep(4);
    setChainStatus("loading");
    setChainResults(null);
    setChainError("");
    setChainPathIdx(0);

    try {
      const res = await fetch(`${BACKEND_URL}/chain-hunt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category_url: categoryUrlForRequest(),
          target_price: priceNum,
          golden_filters: goldenFiltersForRequest(),
          location: selectedLocation,
          mandatory_filters: mandatoryFilters,
          excluded_filter_keys: ["mse_applicable"],
        }),
        signal,
      });
      if (!res.ok) throw new Error(await readError(res, "Chain hunt failed"));
      const data = await res.json();
      setChainResults(data);
      setChainStatus("done");
    } catch (e) {
      if (e.name === "AbortError") return;
      setChainError(e.message || "Chain hunt failed");
      setChainStatus("error");
    }
  };

  // Price range info for the category
  const minCatPrice = scrapedData
    ? Math.min(...scrapedData.products.map((p) => p.price))
    : 0;

  if (view === "landing") {
    return <Landing onLaunch={() => setView("app")} />;
  }

  return (
    <div className={`app${currentStep === 4 ? " app-wide" : ""}`}>
      <Header onHome={() => setView("landing")} />

      <StepIndicator
        currentStep={currentStep}
        furthestStep={furthestStep}
        onStepClick={setCurrentStep}
      />

      {currentStep === 1 && (
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
      )}

      {currentStep === 2 && scrapedData && (
        <PriceInput
          sellerPrice={sellerPrice}
          setSellerPrice={setSellerPrice}
          scrapedData={scrapedData}
          minCatPrice={minCatPrice}
          priceNum={priceNum}
          onContinue={() => goToStep(3)}
          mandatoryFilters={mandatoryFilters}
          setMandatoryFilters={setMandatoryFilters}
          isFilterDropdownOpen={isFilterDropdownOpen}
          setIsFilterDropdownOpen={setIsFilterDropdownOpen}
          hoveredFilterKey={hoveredFilterKey}
          setHoveredFilterKey={setHoveredFilterKey}
        />
      )}

      {currentStep === 3 && scrapedData && priceNum > 0 && (
        <ToolChoice
          onChooseChainHunt={handleChainHunt}
          chainStatus={chainStatus}
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

      {currentStep === 4 && priceNum > 0 && (
        <>
          <div className="step4-toolbar">
            <button className="btn-back" onClick={() => setCurrentStep(3)}>
              <ArrowLeft size={15} weight="bold" /> Back
            </button>
            <button className="btn" onClick={handleStartOver}>
              Start over
            </button>
          </div>

          {activeTool === "chainHunt" && (
            <ChainHuntResults
              chainStatus={chainStatus}
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

          {activeTool === "strike" && (
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
        </>
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
