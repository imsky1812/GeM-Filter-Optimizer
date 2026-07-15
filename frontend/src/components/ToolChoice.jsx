import { useState } from "react";
import SurgicalStrike from "./SurgicalStrike.jsx";

export default function ToolChoice({
  onChooseChainHunt,
  chainStatus,
  strikeUrl,
  setStrikeUrl,
  strikeStatus,
  setStrikeStatus,
  strikeResults,
  strikeError,
  onSurgicalStrike,
  priceNum,
}) {
  const [strikeExpanded, setStrikeExpanded] = useState(false);

  return (
    <div className="card fade-in">
      <div className="card-hdr">
        <div>
          <div className="card-title">Choose an analysis</div>
          <div className="card-desc">
            Pick what you want to find out about this category
          </div>
        </div>
      </div>

      <button
        type="button"
        className="tool-choice-card tool-choice-primary"
        onClick={onChooseChainHunt}
        disabled={chainStatus === "loading"}
      >
        <div className="tool-choice-icon">⚡</div>
        <div className="tool-choice-body">
          <div className="tool-choice-title">Sequential Chain Hunt</div>
          <div className="tool-choice-desc">
            Find filter combinations that make your product the cheapest (L1) in this category.
          </div>
        </div>
        <div className="tool-choice-arrow">→</div>
      </button>

      {!strikeExpanded ? (
        <button
          type="button"
          className="tool-choice-card tool-choice-secondary"
          onClick={() => setStrikeExpanded(true)}
        >
          <div className="tool-choice-icon">🎯</div>
          <div className="tool-choice-body">
            <div className="tool-choice-title">Analyze a specific competitor</div>
            <div className="tool-choice-desc">
              Paste a competitor's product URL to find filters that exclude them.
            </div>
          </div>
          <div className="tool-choice-arrow">→</div>
        </button>
      ) : (
        <SurgicalStrike
          strikeUrl={strikeUrl}
          setStrikeUrl={setStrikeUrl}
          strikeStatus={strikeStatus}
          setStrikeStatus={setStrikeStatus}
          strikeResults={strikeResults}
          strikeError={strikeError}
          onSurgicalStrike={onSurgicalStrike}
          priceNum={priceNum}
        />
      )}
    </div>
  );
}
