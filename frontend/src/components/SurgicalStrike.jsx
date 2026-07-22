import { Target, ArrowClockwise, CheckCircle, Star, ArrowRight, Warning, Trophy } from "@phosphor-icons/react";

export default function SurgicalStrike({
  strikeUrl,
  setStrikeUrl,
  strikeStatus,
  setStrikeStatus,
  strikeResults,
  strikeError,
  onSurgicalStrike,
  priceNum
}) {
  return (
    <div className="card fade-in fade-in-d2">
      <div className="card-hdr">
        <div className="step-num step-num-strike"><Target size={16} weight="fill" /></div>
        <div>
          <div className="card-title">Surgical Strike</div>
          <div className="card-desc">
            Paste a competitor's listing. We'll find the golden filters that box them out.
          </div>
        </div>
      </div>

      <div className="strike-input-group">
        <input
          type="text"
          value={strikeUrl}
          onChange={(e) => setStrikeUrl(e.target.value)}
          placeholder="Paste competitor's GeM product URL (e.g. mkp.gem.gov.in/.../product-detail/...)"
          onKeyDown={(e) => e.key === "Enter" && onSurgicalStrike()}
          className="flex-1"
          id="strike-url-input"
        />
        <button
          className="chain-hunt-trigger strike-submit-btn"
          onClick={onSurgicalStrike}
          disabled={!strikeUrl.trim() || strikeStatus === "loading"}
        >
          {strikeStatus === "loading" ? (
            <>
              <span className="spin" /> Analyzing...
            </>
          ) : (
            <><Target size={16} weight="bold" /> Analyze Competitor</>
          )}
        </button>
      </div>

      {/* Loading */}
      {strikeStatus === "loading" && (
        <div className="strike-loading-container">
          <span className="spin spin-amber" />
          <div className="strike-loading-text">
            Fetching competitor specs and matching against golden filters...
          </div>
        </div>
      )}

      {/* Error */}
      {strikeStatus === "error" && (
        <div className="err-box">
          {strikeError}
          <div className="flex-row-gap-16">
            <button className="btn btn-primary flex-1" onClick={onSurgicalStrike}>
              Retry
            </button>
            <button className="btn flex-1" onClick={() => setStrikeStatus("idle")}>
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Results */}
      {strikeStatus === "done" && strikeResults && (
        <div className="strike-results-wrap">
          {/* Competitor Info Header */}
          <div className="competitor-info-header">
            <div className="flex-space-between-align-center">
              <div>
                <div className="card-desc text-uppercase-tracking">
                  Target Competitor
                </div>
                <div className="strike-competitor-name">
                  {strikeResults.competitorName || "Unknown Product"}
                </div>
              </div>
              <div className="text-right">
                {strikeResults.competitorPrice && (
                  <div className="strike-competitor-price">
                    ₹{strikeResults.competitorPrice.toLocaleString()}
                  </div>
                )}
                <div className="text-xs-subtle">
                  {strikeResults.goldenMatches?.length ?? 0} golden filters matched · {strikeResults.totalApiCalls} API calls · {strikeResults.elapsed}s
                </div>
              </div>
            </div>
          </div>

          {/* Golden Filter Matches */}
          {strikeResults.goldenMatches?.length > 0 && (
            <div className="margin-bottom-16">
              <div className="section-sub-header">
                Their Golden Specs
              </div>
              <div className="chips-container">
                {strikeResults.goldenMatches.map((m, idx) => (
                  <div key={idx} className="chip-item chip-item-amber" style={{ "--stagger-i": idx }}>
                    <span className="chip-label">{m.filterName}:</span>{" "}
                    <strong className="chip-value">{m.competitorValue}</strong>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Counter Filters */}
          {strikeResults.counterFilters?.length > 0 ? (
            <>
              <div className="section-sub-header">
                Counter Filters ({strikeResults.wins} wins, {strikeResults.untapped} untapped):
              </div>
              <div className="flex-column-gap-8">
                {strikeResults.counterFilters.map((cf, idx) => (
                  <div
                    key={idx}
                    className="counter-filter-row"
                    data-win={cf.wouldWin ? "true" : "false"}
                    data-untapped={cf.isUntapped ? "true" : "false"}
                    style={{ "--stagger-i": idx }}
                  >
                    <div
                      className="counter-icon"
                      data-win={cf.wouldWin ? "true" : "false"}
                      data-untapped={cf.isUntapped ? "true" : "false"}
                    >
                      {cf.wouldWin ? (
                        <CheckCircle size={16} weight="fill" />
                      ) : cf.isUntapped ? (
                        <Star size={16} weight="fill" />
                      ) : (
                        <ArrowRight size={14} weight="bold" />
                      )}
                    </div>
                    <div className="counter-info">
                      <div className="counter-info-main">
                        Set <strong>{cf.filterName}</strong> = <strong className="color-success">{cf.counterValue}</strong>
                        <span className="counter-competitor-value">
                          (competitor has: {cf.competitorValue})
                        </span>
                      </div>
                      <div className="counter-info-sub">
                        {cf.isUntapped ? (
                          <><Trophy size={13} weight="fill" className="inline-icon" /> Zero competitors. Untapped niche!</>
                        ) : cf.wouldWin ? (
                          <><Trophy size={13} weight="fill" className="inline-icon" /> You'd be L1! Min price: ₹{cf.resultMinPrice?.toLocaleString()}, {cf.resultTotal} products</>
                        ) : (
                          `Min price: ₹${cf.resultMinPrice?.toLocaleString() ?? "?"}, ${cf.resultTotal} products`
                        )}
                      </div>
                    </div>
                    <div className={`counter-badge ${cf.wouldWin ? "counter-badge-win" : cf.isUntapped ? "counter-badge-untapped" : "counter-badge-no"}`}>
                      {cf.wouldWin ? "WIN" : cf.isUntapped ? "UNTAPPED" : "NO WIN"}
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : strikeResults.goldenMatches?.length === 0 ? (
            <div className="empty margin-top-16">
              <div className="empty-icon"><Warning size={28} weight="fill" /></div>
              <div className="empty-text">
                No spec matches found.<br />
                <span className="empty-subtext">
                  Their listing likely uses different spec names than this category's filters.
                </span>
              </div>
            </div>
          ) : (
            <div className="empty margin-top-16">
              <div className="empty-icon"><Target size={28} weight="fill" /></div>
              <div className="empty-text">
                They match every golden filter. No counter-move available.
              </div>
            </div>
          )}

          <button
            className="strike-btn margin-top-24"
            onClick={onSurgicalStrike}
          >
            <ArrowClockwise size={16} weight="bold" /> Re-analyze
          </button>
        </div>
      )}
    </div>
  );
}
