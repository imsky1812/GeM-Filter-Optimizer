export default function ChainHuntResults({
  chainStatus,
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
            </div>
          </div>
        )}

        {chainStatus === "done" && chainResults && (
          <>
            <div className="text-xs-subtle margin-bottom-16">
              ⚡ Sequential Chain Elimination
            </div>

            {(() => {
              const hasPaths = !!(chainResults.winningPaths && chainResults.winningPaths.length > 0);
              const isWin = chainResults.status === "WIN";
              const selectedPath = hasPaths
                ? (chainResults.winningPaths[chainPathIdx] || chainResults.winningPaths[0])
                : null;

              const headlineTone = isWin ? "success" : hasPaths ? "amber" : "danger";
              const headlineIcon = isWin ? "✓" : hasPaths ? "⚠" : "✗";
              const headlineText = isWin
                ? "You can be L1 for this category."
                : hasPaths
                ? `Best floor reachable: ₹${(chainResults.bestAchievablePrice ?? 0).toLocaleString()} — above your price of ₹${priceNum.toLocaleString()}.`
                : `No path found — all golden filters exhausted at ₹${priceNum.toLocaleString()}.`;

              return (
                <>
                  <div className={`chain-headline chain-headline-${headlineTone}`}>
                    <span className="chain-headline-icon">{headlineIcon}</span>
                    <span>{headlineText}</span>
                  </div>

                  {selectedPath && (
                    <div className="chain-active-filters margin-top-12">
                      {Object.entries(selectedPath.activeFilters || {}).map(([key, val]) => {
                        const gf = scrapedData?.filters?.find(f => f.filterKey === key);
                        return (
                          <div key={key} className="chain-filter-chip">
                            {gf?.filterName || key}: <strong>{val}</strong>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {chainResults.winningPaths && chainResults.winningPaths.length > 1 && (
                    <div className="chain-path-tabs margin-top-12">
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
                  )}

                  {hasPaths && (
                    <details className="chain-detail-toggle margin-top-16">
                      <summary className="chain-detail-summary">View elimination steps</summary>

                      <div className="chain-summary margin-top-16">
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
                          <div className={chainResults.status === "WIN" ? "chain-stat-val color-success" : "chain-stat-val color-amber"}>
                            {chainResults.status === "WIN" ? "✓ WIN" : "⚠ PARTIAL"}
                          </div>
                          <div className="chain-stat-lbl">Status</div>
                        </div>
                      </div>

                      {!isWin && (
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
                        </div>
                      )}

                      <div className="chain-timeline">
                        {(selectedPath?.iterations || []).map((step, idx) => (
                          <div key={idx} className="chain-step">
                            <div className="chain-node chain-node-blocker">{idx + 1}</div>
                            <div className="chain-blocker-card">
                              <div className="chain-blocker-header">
                                <div className="chain-blocker-tag">⛔ Competitors at Floor Price</div>
                                <div className="chain-blocker-price">₹{step.prevMinPrice?.toLocaleString()}</div>
                              </div>
                              <div className="chain-blocker-name">
                                Current market minimum price
                              </div>
                              <div className="chain-filter-action">
                                <div className="chain-filter-icon">🎯</div>
                                <div className="chain-filter-text">
                                  Apply <strong>"{step.filterApplied?.filterName}"</strong> = <strong>"{step.filterApplied?.value}"</strong>
                                </div>
                              </div>
                              {step.result === "LATERAL" ? (
                                <div className="chain-new-l1-lateral">
                                  → Pool narrowed to <strong>{step.newTotal}</strong> products
                                  <span className="chain-badge">LATERAL</span>
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

                        {selectedPath && (
                          <div className="chain-step chain-step-final">
                            <div className={`chain-node ${selectedPath.isUntapped ? "chain-node-untapped" : selectedPath.status === "PARTIAL" ? "chain-node-partial" : "chain-node-victory"}`}>
                              {selectedPath.status === "PARTIAL" ? "⚠" : "✓"}
                            </div>
                            <div className="chain-victory-card" data-status={selectedPath.status === "PARTIAL" ? "PARTIAL" : "WIN"}>
                              <div className="chain-victory-header">
                                <div className="chain-victory-tag">
                                  {selectedPath.isUntapped
                                    ? "🏆 Untapped Niche"
                                    : selectedPath.status === "PARTIAL"
                                        ? "⚠ Stuck - Cannot Reach Target"
                                        : "🏆 You Are L1!"}
                                </div>
                                <div className="chain-victory-price">
                                  {selectedPath.isUntapped
                                    ? "No Competitors"
                                    : `Max Price Reached: ₹${selectedPath.nicheMinPrice?.toLocaleString() ?? "?"}`}
                                </div>
                              </div>
                              <div className="chain-victory-detail">
                                {selectedPath.status === "PARTIAL" ? (
                                  <>
                                    After <strong>{(selectedPath.iterations || []).length} elimination{(selectedPath.iterations || []).length !== 1 ? "s" : ""}</strong>,
                                    the highest price floor reachable is <strong>₹{selectedPath.nicheMinPrice?.toLocaleString() ?? "?"}</strong>.
                                    No further filters can raise the price above your target of <strong>₹{priceNum.toLocaleString()}</strong>.
                                  </>
                                ) : (
                                  <>
                                    After <strong>{(selectedPath.iterations || []).length} elimination{(selectedPath.iterations || []).length !== 1 ? "s" : ""}</strong>,
                                    your product at <strong>₹{priceNum.toLocaleString()}</strong> is now the cheapest.
                                    {!selectedPath.isUntapped && selectedPath.nicheMinPrice && (
                                      <> Price gap: <strong>₹{(selectedPath.nicheMinPrice - priceNum).toLocaleString()}</strong></>
                                    )}
                                    {selectedPath.totalProducts > 0 && (
                                      <> · <strong>{selectedPath.totalProducts}</strong> products in niche</>
                                    )}
                                  </>
                                )}
                              </div>

                              {selectedPath.competitorInsights && (
                                <div className="competitor-insights-container">
                                  <div className="competitor-insights-header">
                                    <span className="competitor-insights-icon">🕵️</span>
                                    <span className="competitor-insights-title">Competitor Insights</span>
                                  </div>
                                  <div className="competitor-insights-msg">
                                    {selectedPath.competitorInsights.message}
                                  </div>

                                  {(selectedPath.competitorInsights.l2 || selectedPath.competitorInsights.l3) && (
                                    <div className="competitor-insights-grid">
                                      {selectedPath.competitorInsights.l2 && (
                                        <div
                                          className="competitor-insights-card"
                                          onClick={() => onFetchCompetitorSpecs(selectedPath.competitorInsights.l2, "L2")}
                                        >
                                          <div className="competitor-insights-card-header">
                                            <span>L2 Product</span>
                                            <span className="competitor-insights-card-hint">Click to view specs</span>
                                          </div>
                                          <div className="competitor-insights-card-title" title={selectedPath.competitorInsights.l2.name}>
                                            {selectedPath.competitorInsights.l2.name}
                                          </div>
                                          <div className="competitor-insights-card-footer">
                                            <span className="competitor-insights-card-brand">
                                              {selectedPath.competitorInsights.l2.brand || "Unknown Brand"}
                                            </span>
                                            <span className="competitor-insights-card-price">
                                              ₹{selectedPath.competitorInsights.l2.price.toLocaleString()}
                                            </span>
                                          </div>
                                        </div>
                                      )}
                                      {selectedPath.competitorInsights.l3 && (
                                        <div
                                          className="competitor-insights-card"
                                          onClick={() => onFetchCompetitorSpecs(selectedPath.competitorInsights.l3, "L3")}
                                        >
                                          <div className="competitor-insights-card-header">
                                            <span>L3 Product</span>
                                            <span className="competitor-insights-card-hint">Click to view specs</span>
                                          </div>
                                          <div className="competitor-insights-card-title" title={selectedPath.competitorInsights.l3.name}>
                                            {selectedPath.competitorInsights.l3.name}
                                          </div>
                                          <div className="competitor-insights-card-footer">
                                            <span className="competitor-insights-card-brand">
                                              {selectedPath.competitorInsights.l3.brand || "Unknown Brand"}
                                            </span>
                                            <span className="competitor-insights-card-price">
                                              ₹{selectedPath.competitorInsights.l3.price.toLocaleString()}
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
                        )}
                      </div>
                    </details>
                  )}
                </>
              );
            })()}

            <button className="chain-hunt-trigger margin-top-24" onClick={onChainHunt}>
              🔄 Re-run Chain Hunt
            </button>
          </>
        )}
      </div>
    </div>
  );
}
