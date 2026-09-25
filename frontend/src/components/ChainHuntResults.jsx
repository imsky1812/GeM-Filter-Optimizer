import "./Results.css";
import { useState } from "react";
import {
  Lightning,
  CheckCircle,
  Warning,
  XCircle,
  Lightbulb,
  ArrowClockwise,
  CaretLeft,
  CaretRight,
  ArrowRight,
} from "@phosphor-icons/react";

const money = (n) => (n == null ? "—" : `₹${n.toLocaleString()}`);

/** GeM filter names trail a long parenthetical spec range; the title keeps it. */
const shortName = (s) => (s || "").replace(/\s*\([^)]*\)\s*$/, "");

const filterLine = (activeFilters, filters) =>
  Object.entries(activeFilters || {})
    .map(([key, val]) => {
      const gf = filters?.find((f) => f.filterKey === key);
      return `${shortName(gf?.filterName || key)}: ${val}`;
    })
    .join("  ·  ");

/** One elimination step: the filter applied, and what it did to the floor. */
function Step({ step, index, isLast }) {
  const lifted =
    step.newMinPrice != null && step.prevMinPrice != null && step.newMinPrice > step.prevMinPrice;

  return (
    <li className="res-step">
      <span className="res-step-rail" aria-hidden="true">
        <span className="res-step-node">{index + 1}</span>
        {!isLast && <span className="res-step-line" />}
      </span>

      <div className="res-step-body">
        <div className="res-step-filter">
          <span className="res-step-name" title={step.filterApplied?.filterName}>
            {shortName(step.filterApplied?.filterName)}
          </span>
          <ArrowRight size={13} weight="bold" className="res-step-arrow" />
          <span className="res-step-value">{step.filterApplied?.value}</span>
        </div>

        <dl className="res-step-effect">
          <div>
            <dt>Floor</dt>
            <dd className={lifted ? "is-up" : ""}>
              {money(step.newMinPrice)}
              {lifted && <span className="res-delta">+{(step.newMinPrice - step.prevMinPrice).toLocaleString()}</span>}
            </dd>
          </div>
          <div>
            <dt>Products</dt>
            <dd>{step.newTotal?.toLocaleString() ?? "—"}</dd>
          </div>
          <div>
            <dt>Sellers</dt>
            <dd>{step.sellerCount ?? "—"}</dd>
          </div>
        </dl>
      </div>
    </li>
  );
}

function CompetitorCard({ role, competitor, onOpen }) {
  if (!competitor) return null;
  // GeM prefixes listing titles with the seller name, which we already show below.
  const brand = competitor.brand || "";
  const name =
    brand && competitor.name?.startsWith(brand)
      ? competitor.name.slice(brand.length).replace(/^[\s\-–—]+/, "")
      : competitor.name;
  return (
    <button type="button" className="res-rival" onClick={() => onOpen(competitor, role)}>
      <span className="res-rival-role">{role}</span>
      <span className="res-rival-name" title={competitor.name}>{name}</span>
      <span className="res-rival-meta">
        <span className="res-rival-brand">{brand || "Unknown seller"}</span>
        <span className="res-rival-price">{money(competitor.price)}</span>
      </span>
    </button>
  );
}

export default function ChainHuntResults({
  chainStatus,
  chainResults,
  chainError,
  onChainHunt,
  priceNum,
  chainPathIdx,
  setChainPathIdx,
  scrapedData,
  onFetchCompetitorSpecs,
}) {
  const [showAllPaths, setShowAllPaths] = useState(false);
  if (chainStatus === "idle") return null;

  if (chainStatus === "loading") {
    return (
      <div className="card fade-in fade-in-d2">
        <div className="chain-loading">
          <span className="spin spin-amber" />
          <div className="chain-loading-title">
            <Lightning size={16} weight="fill" className="inline-icon" /> Hunting your L1 path
          </div>
          <div className="chain-loading-sub">
            Eliminating blockers one by one, re-checking the market against GeM after
            every filter change.
          </div>
          <div className="chain-loading-bar"><div className="chain-loading-fill" /></div>
          <ol className="run-phases">
            <li className="run-phase is-on"><span className="tag">scan</span><span className="txt">Indexing products and golden filters</span></li>
            <li className="run-phase is-on"><span className="tag">hunt</span><span className="txt">Combining filters up to four deep, in memory</span></li>
            <li className="run-phase is-on"><span className="tag">verify</span><span className="txt">Re-checking the best candidates against GeM live</span></li>
            <li className="run-phase"><span className="tag">result</span><span className="txt">Ranking the paths that clear your price</span></li>
          </ol>
        </div>
      </div>
    );
  }

  if (chainStatus === "error") {
    return (
      <div className="card fade-in fade-in-d2">
        <div className="err-box">
          {chainError}
          <div className="flex-row-gap-16">
            <button className="btn btn-primary flex-1" onClick={onChainHunt}>Retry</button>
          </div>
        </div>
      </div>
    );
  }

  if (!chainResults) return null;

  const paths = chainResults.winningPaths || [];
  const unconfirmed = chainResults.unconfirmedPaths || [];
  const hasPaths = paths.length > 0;
  const isWin = chainResults.status === "WIN";
  const path = hasPaths ? paths[chainPathIdx] || paths[0] : null;
  const steps = path?.iterations || [];
  const gap = path?.nicheMinPrice != null ? path.nicheMinPrice - priceNum : null;

  const HeadIcon = isWin ? CheckCircle : hasPaths ? Warning : XCircle;
  const tone = isWin ? "win" : hasPaths ? "partial" : "none";
  const headline = isWin
    ? "Your price is the cheapest in this niche."
    : hasPaths
    ? `Best floor these filters reach is ${money(chainResults.bestAchievablePrice)} — someone still undercuts your ${money(priceNum)}.`
    : `No filter combination makes you L1 at ${money(priceNum)}.`;

  return (
    <div className="card fade-in fade-in-d2">
      {/* ── The answer ─────────────────────────────────────────── */}
      <header className="res-head" data-tone={tone}>
        <HeadIcon size={20} weight="fill" className="res-head-icon" />
        <h2 className="res-headline">{headline}</h2>
      </header>

      {path && (
        <dl className="res-summary">
          <div>
            <dt>Your price</dt>
            <dd>{money(priceNum)}</dd>
          </div>
          <div>
            <dt>Next listing</dt>
            <dd>{money(path.nicheMinPrice)}</dd>
          </div>
          {gap != null && (
            <div>
              <dt>Gap</dt>
              <dd className={gap > 0 ? "is-up" : ""}>{gap > 0 ? `+${gap.toLocaleString()}` : gap.toLocaleString()}</dd>
            </div>
          )}
          <div>
            <dt>In niche</dt>
            <dd>{path.totalProducts?.toLocaleString() ?? "—"}</dd>
          </div>
          <div>
            <dt>Sellers</dt>
            <dd>{path.sellerCount ?? "—"}</dd>
          </div>
        </dl>
      )}

      {/* ── Which path ─────────────────────────────────────────── */}
      {hasPaths && (
        <section className="res-paths">
          <div className="res-paths-bar">
            <span className="res-paths-label">
              Path <strong>{chainPathIdx + 1}</strong> of {paths.length}
              <span className="res-paths-steps">{steps.length} filter{steps.length !== 1 ? "s" : ""}</span>
            </span>
            <div className="res-paths-nav">
              <button
                type="button" className="res-icon-btn" aria-label="Previous path"
                disabled={chainPathIdx === 0}
                onClick={() => setChainPathIdx(Math.max(0, chainPathIdx - 1))}
              >
                <CaretLeft size={14} weight="bold" />
              </button>
              <button
                type="button" className="res-icon-btn" aria-label="Next path"
                disabled={chainPathIdx >= paths.length - 1}
                onClick={() => setChainPathIdx(Math.min(paths.length - 1, chainPathIdx + 1))}
              >
                <CaretRight size={14} weight="bold" />
              </button>
              {paths.length > 1 && (
                <button type="button" className="res-text-btn" onClick={() => setShowAllPaths((v) => !v)}>
                  {showAllPaths ? "Hide" : "All paths"}
                </button>
              )}
            </div>
          </div>

          {showAllPaths && (
            <ul className="res-path-list">
              {paths.map((p, i) => (
                <li key={i}>
                  <button
                    type="button"
                    className="res-path-row"
                    aria-current={i === chainPathIdx}
                    onClick={() => { setChainPathIdx(i); setShowAllPaths(false); }}
                  >
                    <span className="res-path-n">{i + 1}</span>
                    <span className="res-path-filters">
                      {filterLine(p.activeFilters, scrapedData?.filters)}
                    </span>
                    <span className="res-path-floor">{money(p.nicheMinPrice)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* ── How it got there ───────────────────────────────────── */}
      {steps.length > 0 && (
        <section className="res-section">
          <h3 className="res-section-title">Elimination steps</h3>
          <ol className="res-steps">
            {steps.map((step, i) => (
              <Step key={i} step={step} index={i} isLast={i === steps.length - 1} />
            ))}
          </ol>
          {path?.isUntapped && (
            <p className="res-note">No competitors remain in this niche at all — it's untapped.</p>
          )}
        </section>
      )}

      {/* ── Who you'd be up against ────────────────────────────── */}
      {path?.competitorInsights && (path.competitorInsights.l2 || path.competitorInsights.l3) && (
        <section className="res-section">
          <h3 className="res-section-title">
            Who you'd sit above
            <span className="res-section-note">Click a listing for its live specs</span>
          </h3>
          <div className="res-rivals">
            <CompetitorCard role="L2" competitor={path.competitorInsights.l2} onOpen={onFetchCompetitorSpecs} />
            <CompetitorCard role="L3" competitor={path.competitorInsights.l3} onOpen={onFetchCompetitorSpecs} />
          </div>
        </section>
      )}

      {/* ── When nothing clears the price ──────────────────────── */}
      {!isWin && chainResults.bestAchievablePrice && (
        <p className="res-advice">
          <Lightbulb size={15} weight="fill" />
          List below <strong>{money(chainResults.bestAchievablePrice)}</strong> to take L1 — that's the
          highest floor these filters can reach.
        </p>
      )}

      {/* ── Leads GeM wouldn't confirm ─────────────────────────── */}
      {unconfirmed.length > 0 && (
        <section className="res-section">
          <h3 className="res-section-title">
            {unconfirmed.length} lead{unconfirmed.length !== 1 ? "s" : ""} GeM didn't confirm
            <span className="res-section-note">Worth checking by hand</span>
          </h3>
          <p className="res-note">
            GeM's search returned nothing for these combinations, most likely because its index
            doesn't accept the literal filter text — not because the niche is empty.
          </p>
          <ul className="res-lead-list">
            {unconfirmed.map((lead, i) => (
              <li key={i} className="res-lead">
                <span className="res-lead-filters">
                  {filterLine(lead.activeFilters, scrapedData?.filters)}
                </span>
                <span className="res-lead-meta">
                  {lead.totalProducts} local match{lead.totalProducts !== 1 ? "es" : ""}
                  {lead.nicheMinPrice != null && ` · floor ~${money(lead.nicheMinPrice)}`}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ── Provenance ─────────────────────────────────────────── */}
      <footer className="res-foot">
        <span className="res-foot-meta">
          {chainResults.totalPaths} path{chainResults.totalPaths !== 1 ? "s" : ""} ·{" "}
          {chainResults.totalApiCalls} requests · {chainResults.goldenFilterCount} golden filters ·{" "}
          {chainResults.elapsed}s · market floor {money(chainResults.marketMinPrice)}
        </span>
        <button type="button" className="res-text-btn" onClick={onChainHunt}>
          <ArrowClockwise size={14} weight="bold" /> Run again
        </button>
      </footer>
    </div>
  );
}
