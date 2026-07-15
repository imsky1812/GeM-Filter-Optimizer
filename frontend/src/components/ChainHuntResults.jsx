export default function ChainHuntResults({
  chainStatus,
  setChainStatus,
  chainResults,
  chainError,
  onChainHunt,
  priceNum,
  chainPathIdx,
  setChainPathIdx,
  scrapedData,
  onFetchCompetitorSpecs
}) {
  if (chainStatus === "idle") return null;

  return (
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
          <div className="err-box margin-top-16">
            {chainError}
            <div className="flex-row-gap-16">
              <button className="btn btn-primary flex-1" onClick={onChainHunt}>
                Retry
              </button>
              <button className="btn flex-1" onClick={() => setChainStatus("idle")}>
                ← Back
              </button>
            </div>
          </div>
        )}

        {chainStatus === "done" && chainResults && (
          <>
            <div className="flex-space-between-align-center margin-bottom-16">
              <button
                onClick={() => setChainStatus("idle")}
                className="btn-back"
              >
                <span>←</span> Back
              </button>
              <div className="text-xs-subtle">
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
                <div className={
                  chainResults.status === "WIN"
                    ? "chain-stat-val color-success"
                    : chainResults.status === "PARTIAL"
                    ? "chain-stat-val color-amber"
                    : "chain-stat-val color-danger"
                }>
                  {chainResults.status === "WIN" ? "✓ WIN" : chainResults.status === "PARTIAL" ? "⚠ STUCK" : "✗ FAIL"}
                </div>
                <div className="chain-stat-lbl">Status</div>
              </div>
            </div>

            {/* ── STUCK / NO L1 PATH BANNER ── */}
            {chainResults.status !== "WIN" && (
              <div className="stuck-banner">
                <div className="stuck-banner-header">
                  <div className="stuck-banner-icon">🚫</div>
                  <div>
                    <div className="stuck-banner-title">
                      No Path to L1 at ₹{priceNum.toLocaleString()}
                    </div>
                    <div className="stuck-banner-desc">
                      All golden filters exhausted — no combination can make your product the cheapest.
                    </div>
                  </div>
                </div>

                <div className="stuck-stats">
                  <div className="stuck-stat">
                    <div className="stuck-stat-label">Your Price</div>
                    <div className="stuck-stat-value">₹{priceNum.toLocaleString()}</div>
                  </div>
                  <div className="stuck-stat">
                    <div className="stuck-stat-label">Best Achievable Floor</div>
                    <div className="stuck-stat-value color-amber">
                      ₹{(chainResults.bestAchievablePrice ?? 0).toLocaleString()}
                    </div>
                  </div>
                  <div className="stuck-stat">
                    <div className="stuck-stat-label">Gap (Unreachable)</div>
                    <div className="stuck-stat-value color-danger">
                      ₹{(priceNum - (chainResults.bestAchievablePrice ?? 0)).toLocaleString()}
                    </div>
                  </div>
                </div>

                {chainResults.bestAchievablePrice && (
                  <div className="stuck-advice">
                    <span>💡</span>
                    <span>
                      To become L1 in this category, you would need to list your product
                      below <strong className="color-amber">
                        ₹{chainResults.bestAchievablePrice.toLocaleString()}
                      </strong> (the highest price floor achievable through spec filters).
                    </span>
                  </div>
                )}
              </div>
            )}

            {(!chainResults.winningPaths || chainResults.winningPaths.length === 0) ? (
              <div className="empty margin-top-16">
                <div className="empty-icon">🔍</div>
                <div className="empty-text">
                  No filter combinations found.<br />
                  <span className="empty-subtext">
                    The current L1 products cannot be bypassed with available golden filters.
                    Try lowering your price or check if additional filter options exist.
                  </span>
                </div>
              </div>
            ) : (
              <>
                {/* Path selector tabs */}
                <div className="chain-subtitle margin-bottom-12">
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
                      {path.isUntapped && <span className="color-amber text-xs">★</span>}
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
                        <div key={idx} className="chain-step">
                          {/* Node circle */}
                          <div className="chain-node chain-node-blocker">{idx + 1}</div>

                          {/* Blocker card */}
                          <div className="chain-blocker-card">
                            <div className="chain-blocker-header">
                              <div className="chain-blocker-tag">⛔ Competitors at Floor Price</div>
                              <div className="chain-blocker-price">₹{step.prevMinPrice?.toLocaleString()}</div>
                            </div>
                            <div className="chain-blocker-name">
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
                              <div className="chain-new-l1-lateral">
                                → Pool narrowed to <strong>{step.newTotal}</strong> products
                                <span className="chain-badge">
                                  LATERAL
                                </span>
                              </div>
                            ) : step.newMinPrice !== null && step.newMinPrice !== undefined && (
                              <div className="chain-new-l1">
                                → Price floor raised to: <strong>₹{step.newMinPrice?.toLocaleString()}</strong>
                                <span className="chain-badge-text">
                                  {step.newTotal} products remain
                                </span>
                              </div>
                            )}
                            {step.result === "UNTAPPED" && (
                              <div className="chain-new-l1 color-amber">
                                → Niche is now <strong>untapped</strong> — zero competitors!
                              </div>
                            )}
                          </div>
                        </div>
                      ))}

                      {/* Victory/Partial card */}
                      <div className="chain-step chain-step-final">
                        <div className={`chain-node ${path.isUntapped ? "chain-node-untapped" : path.status === "PARTIAL" ? "chain-node-partial" : "chain-node-victory"}`}>
                          {path.status === "PARTIAL" ? "⚠" : "✓"}
                        </div>
                        <div className="chain-victory-card" data-status={path.status === "PARTIAL" ? "PARTIAL" : "WIN"}>
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
                            <div className="competitor-insights-container">
                              <div className="competitor-insights-header">
                                <span className="competitor-insights-icon">🕵️</span>
                                <span className="competitor-insights-title">Competitor Insights</span>
                              </div>
                              <div className="competitor-insights-msg">
                                {path.competitorInsights.message}
                              </div>
                              
                              {(path.competitorInsights.l2 || path.competitorInsights.l3) && (
                                <div className="competitor-insights-grid">
                                  {path.competitorInsights.l2 && (
                                    <div 
                                      className="competitor-insights-card"
                                      onClick={() => onFetchCompetitorSpecs(path.competitorInsights.l2, "L2")}
                                    >
                                      <div className="competitor-insights-card-header">
                                        <span>L2 Product</span>
                                        <span className="competitor-insights-card-hint">Click to view specs</span>
                                      </div>
                                      <div className="competitor-insights-card-title" title={path.competitorInsights.l2.name}>
                                        {path.competitorInsights.l2.name}
                                      </div>
                                      <div className="competitor-insights-card-footer">
                                        <span className="competitor-insights-card-brand">
                                          {path.competitorInsights.l2.brand || "Unknown Brand"}
                                        </span>
                                        <span className="competitor-insights-card-price">
                                          ₹{path.competitorInsights.l2.price.toLocaleString()}
                                        </span>
                                      </div>
                                    </div>
                                  )}
                                  {path.competitorInsights.l3 && (
                                    <div 
                                      className="competitor-insights-card"
                                      onClick={() => onFetchCompetitorSpecs(path.competitorInsights.l3, "L3")}
                                    >
                                      <div className="competitor-insights-card-header">
                                        <span>L3 Product</span>
                                        <span className="competitor-insights-card-hint">Click to view specs</span>
                                      </div>
                                      <div className="competitor-insights-card-title" title={path.competitorInsights.l3.name}>
                                        {path.competitorInsights.l3.name}
                                      </div>
                                      <div className="competitor-insights-card-footer">
                                        <span className="competitor-insights-card-brand">
                                          {path.competitorInsights.l3.brand || "Unknown Brand"}
                                        </span>
                                        <span className="competitor-insights-card-price">
                                          ₹{path.competitorInsights.l3.price.toLocaleString()}
                                        </span>
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
                  className="chain-hunt-trigger margin-top-24"
                  onClick={onChainHunt}
                >
                  🔄 Re-run Chain Hunt
                </button>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
