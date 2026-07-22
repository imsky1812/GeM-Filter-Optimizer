import {
  Lightning,
  CheckCircle,
  Warning,
  XCircle,
  Prohibit,
  Lightbulb,
  ArrowClockwise,
  MagnifyingGlass,
  Trophy,
  Star,
  Target,
} from "@phosphor-icons/react";

// Fixed spread (not randomized per render) so the burst is stable and doesn't
// jitter if the component re-renders while the animation is still playing.
const CONFETTI = [
  { x: -70, y: -55, r: -120, color: "var(--success)" },
  { x: -50, y: -75, r: 200, color: "var(--primary)" },
  { x: -25, y: -85, r: -80, color: "var(--amber)" },
  { x: 0, y: -90, r: 160, color: "var(--success-bright)" },
  { x: 25, y: -85, r: -200, color: "var(--primary-bright)" },
  { x: 50, y: -75, r: 90, color: "var(--amber-bright)" },
  { x: 70, y: -55, r: -160, color: "var(--success)" },
  { x: -40, y: -30, r: 220, color: "var(--primary)" },
  { x: 40, y: -30, r: -140, color: "var(--amber)" },
  { x: -85, y: -20, r: 100, color: "var(--success-bright)" },
  { x: 85, y: -20, r: -100, color: "var(--primary-bright)" },
  { x: 0, y: -40, r: 300, color: "var(--amber-bright)" },
];

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
            <div className="chain-loading-title">
              <Lightning size={16} weight="fill" className="inline-icon" /> Hunting Your L1 Path
            </div>
            <div className="chain-loading-sub">
              Eliminating blockers one by one, re-scraping the market after every
              filter change. Two to five minutes, worth the wait.
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
              <Lightning size={13} weight="fill" className="inline-icon" /> Sequential Chain Elimination
            </div>

            {(() => {
              const hasPaths = !!(chainResults.winningPaths && chainResults.winningPaths.length > 0);
              const isWin = chainResults.status === "WIN";
              const selectedPath = hasPaths
                ? (chainResults.winningPaths[chainPathIdx] || chainResults.winningPaths[0])
                : null;

              const headlineTone = isWin ? "success" : hasPaths ? "amber" : "danger";
              const HeadlineIcon = isWin ? CheckCircle : hasPaths ? Warning : XCircle;
              const headlineText = isWin
                ? "You can take L1 in this category."
                : hasPaths
                ? `Closest floor: ₹${(chainResults.bestAchievablePrice ?? 0).toLocaleString()}. Still above your ₹${priceNum.toLocaleString()}.`
                : `No path to L1 at ₹${priceNum.toLocaleString()}. Every golden filter's been tried.`;

              return (
                <>
                  <div className={`chain-headline chain-headline-${headlineTone}`}>
                    <span className="chain-headline-icon"><HeadlineIcon size={18} weight="fill" /></span>
                    <span>{headlineText}</span>
                  </div>

                  {selectedPath && (
                    <div className="chain-active-filters margin-top-12">
                      {Object.entries(selectedPath.activeFilters || {}).map(([key, val], idx) => {
                        const gf = scrapedData?.filters?.find(f => f.filterKey === key);
                        return (
                          <div key={key} className="chain-filter-chip" style={{ "--stagger-i": idx }}>
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
                          {path.isUntapped && <span className="color-amber text-xs"><Star size={11} weight="fill" /></span>}
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
                            {chainResults.status === "WIN" ? (
                              <><CheckCircle size={16} weight="fill" className="inline-icon" /> WIN</>
                            ) : (
                              <><Warning size={16} weight="fill" className="inline-icon" /> PARTIAL</>
                            )}
                          </div>
                          <div className="chain-stat-lbl">Status</div>
                        </div>
                      </div>

                      {!isWin && (
                        <div className="stuck-banner">
                          <div className="stuck-banner-header">
                            <div className="stuck-banner-icon"><Prohibit size={20} weight="fill" /></div>
                            <div>
                              <div className="stuck-banner-title">
                                No Path to L1 at ₹{priceNum.toLocaleString()}
                              </div>
                              <div className="stuck-banner-desc">
                                Every combination's been tried. None gets you under the floor.
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
                              <span><Lightbulb size={16} weight="fill" /></span>
                              <span>
                                List below{" "}
                                <strong className="color-amber">
                                  ₹{chainResults.bestAchievablePrice.toLocaleString()}
                                </strong>{" "}
                                to take L1. That's the lowest floor filters can reach.
                              </span>
                            </div>
                          )}
                        </div>
                      )}

                      <div className="chain-timeline">
                        {(selectedPath?.iterations || []).map((step, idx) => (
                          <div key={idx} className="chain-step" style={{ "--stagger-i": idx }}>
                            <div className="chain-node chain-node-blocker">{idx + 1}</div>
                            <div className="chain-blocker-card">
                              <div className="chain-blocker-header">
                                <div className="chain-blocker-tag">
                                  <Prohibit size={13} weight="bold" className="inline-icon" /> Competitors at Floor Price
                                </div>
                                <div className="chain-blocker-price">₹{step.prevMinPrice?.toLocaleString()}</div>
                              </div>
                              <div className="chain-blocker-name">
                                Current market minimum price
                              </div>
                              <div className="chain-filter-action">
                                <div className="chain-filter-icon"><Target size={14} weight="fill" /></div>
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
                                  → Niche is now <strong>untapped</strong>. Zero competitors!
                                </div>
                              )}
                            </div>
                          </div>
                        ))}

                        {selectedPath && (
                          <div className="chain-step chain-step-final">
                            <div className={`chain-node ${selectedPath.isUntapped ? "chain-node-untapped" : selectedPath.status === "PARTIAL" ? "chain-node-partial" : "chain-node-victory"}`}>
                              {selectedPath.status === "PARTIAL" ? <Warning size={13} weight="bold" /> : <CheckCircle size={13} weight="bold" />}
                            </div>
                            <div className="chain-victory-card" data-status={selectedPath.status === "PARTIAL" ? "PARTIAL" : "WIN"}>
                              {selectedPath.status !== "PARTIAL" && (
                                <div className="confetti-burst">
                                  {CONFETTI.map((c, idx) => (
                                    <span
                                      key={idx}
                                      className="confetti-piece"
                                      style={{
                                        "--stagger-i": idx,
                                        "--confetti-x": `${c.x}px`,
                                        "--confetti-y": `${c.y}px`,
                                        "--confetti-r": `${c.r}deg`,
                                        "--confetti-color": c.color,
                                      }}
                                    />
                                  ))}
                                </div>
                              )}
                              <div className="chain-victory-header">
                                <div className="chain-victory-tag">
                                  {selectedPath.isUntapped ? (
                                    <><Trophy size={16} weight="fill" className="inline-icon" /> Untapped Niche</>
                                  ) : selectedPath.status === "PARTIAL" ? (
                                    <><Warning size={16} weight="fill" className="inline-icon" /> Stuck. Can't Reach Target</>
                                  ) : (
                                    <><Trophy size={16} weight="fill" className="inline-icon" /> You Are L1!</>
                                  )}
                                </div>
                                <div className="chain-victory-price">
                                  {selectedPath.isUntapped
                                    ? "No Competitors"
                                    : `Ceiling Price: ₹${selectedPath.nicheMinPrice?.toLocaleString() ?? "?"}`}
                                </div>
                              </div>
                              <div className="chain-victory-detail">
                                {selectedPath.status === "PARTIAL" ? (
                                  <>
                                    <strong>{(selectedPath.iterations || []).length} elimination{(selectedPath.iterations || []).length !== 1 ? "s" : ""}</strong> in,
                                    the highest floor reachable is <strong>₹{selectedPath.nicheMinPrice?.toLocaleString() ?? "?"}</strong>.
                                    No filter combination clears your target of <strong>₹{priceNum.toLocaleString()}</strong>.
                                  </>
                                ) : (
                                  <>
                                    <strong>{(selectedPath.iterations || []).length} elimination{(selectedPath.iterations || []).length !== 1 ? "s" : ""}</strong> in,
                                    your <strong>₹{priceNum.toLocaleString()}</strong> is now the cheapest.
                                    {!selectedPath.isUntapped && selectedPath.nicheMinPrice && (
                                      <> Gap: <strong>₹{(selectedPath.nicheMinPrice - priceNum).toLocaleString()}</strong></>
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
                                    <span className="competitor-insights-icon"><MagnifyingGlass size={16} weight="bold" /></span>
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
              <ArrowClockwise size={16} weight="bold" /> Re-run Chain Hunt
            </button>
          </>
        )}
      </div>
    </div>
  );
}
