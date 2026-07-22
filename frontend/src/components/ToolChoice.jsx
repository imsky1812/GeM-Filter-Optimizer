import { useState } from "react";
import { Lightning, Target, ArrowRight } from "@phosphor-icons/react";
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
          <div className="card-title">Choose Your Move</div>
          <div className="card-desc">
            What do you want to know about this category?
          </div>
        </div>
      </div>

      <button
        type="button"
        className="tool-choice-card tool-choice-primary"
        onClick={onChooseChainHunt}
        disabled={chainStatus === "loading"}
      >
        <div className="tool-choice-icon"><Lightning size={22} weight="fill" /></div>
        <div className="tool-choice-body">
          <div className="tool-choice-title">Sequential Chain Hunt</div>
          <div className="tool-choice-desc">
            Stack filters until you're the cheapest listing in this category.
          </div>
        </div>
        <div className="tool-choice-arrow"><ArrowRight size={18} weight="bold" /></div>
      </button>

      {!strikeExpanded ? (
        <button
          type="button"
          className="tool-choice-card tool-choice-secondary"
          onClick={() => setStrikeExpanded(true)}
        >
          <div className="tool-choice-icon"><Target size={20} weight="fill" /></div>
          <div className="tool-choice-body">
            <div className="tool-choice-title">Target a Competitor</div>
            <div className="tool-choice-desc">
              Paste their listing. We'll find the filters that box them out.
            </div>
          </div>
          <div className="tool-choice-arrow"><ArrowRight size={18} weight="bold" /></div>
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
