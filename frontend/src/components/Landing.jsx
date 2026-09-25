import { useEffect, useState } from "react";
import "./Landing.css";

/* Landing page — "L1 targeting console".
   Markup is written against Landing.css's class contract; the CTAs open the
   optimizer wizard. Copy follows the design canvas artboards. */

const Arrow = ({ size = 17 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
);

const Tick = ({ size = 16, color = "#22C55E" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color}
       strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20 6 9 17l-5-5" />
  </svg>
);

const TickCircle = ({ size = 13, color = "#22C55E", sw = 2.2, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color}
       strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
    <path d="M9 12l2 2 4-4" /><circle cx="12" cy="12" r="9" />
  </svg>
);

const Nodes = ({ size = 22, color = "#B4B4C2", sw = 1.8, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color}
       strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
    <circle cx="6" cy="6" r="2.6" /><circle cx="6" cy="18" r="2.6" /><circle cx="18" cy="12" r="2.6" />
    <path d="M8.4 7.2 15.6 11M8.4 16.8 15.6 13" />
  </svg>
);

const Scan = ({ size = 22, color = "#B4B4C2", sw = 1.8, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color}
       strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
    <circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4.5" />
    <path d="M12 3v3M12 18v3M21 12h-3M6 12H3" />
  </svg>
);

const Crosshair = ({ size = 22, color = "#B4B4C2", sw = 1.8 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color}
       strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="8" /><path d="M12 2v4M12 18v4M22 12h-4M6 12H2" />
    <circle cx="12" cy="12" r="1.4" fill={color} stroke="none" />
  </svg>
);

const Mark = ({ size = 18, accent = "#F0353F", rays = true }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={accent}
       strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <circle cx="12" cy="12" r="8" />
    <circle cx="12" cy="12" r="3" fill={accent} stroke="none" />
    {rays && <path d="M12 1v4M12 19v4M1 12h4M19 12h4" />}
  </svg>
);

/* Shares the wizard's theme key, so the toggle moves both surfaces. */
function useTheme() {
  const [theme, setTheme] = useState(() =>
    (typeof localStorage !== "undefined" && localStorage.getItem("theme")) === "light" ? "light" : "dark"
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("theme", theme); } catch { /* private mode */ }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
}

const FAQ = [
  {
    q: "What exactly is a golden filter?",
    a: "A specification GeM lets buyers filter by — seat material, print technology, warranty. Buyers narrow to a set of them and then sort by price, so the combination you sit inside decides who you're compared against.",
  },
  {
    q: "Why are some paths marked unconfirmed?",
    a: "GeM's search index rejects certain literal filter values, returning nothing for a niche that demonstrably has products in it. Rather than drop those paths or present them as wins, they're flagged so you can check them by hand on GeM.",
  },
  {
    q: "Which category URLs work?",
    a: "Any canonical GeM category URL ending in /search. Short links from GeM's own homepage are aliases that serve their single-page app; those are followed automatically to the real category when GeM resolves them. Product-detail URLs can't be used — copy the category instead.",
  },
  {
    q: "How long does a run take?",
    a: "A category scan runs about 20 seconds. A chain hunt takes 25–30 seconds and spends roughly 60–80 requests, deliberately paced so GeM's firewall doesn't start rejecting them.",
  },
  {
    q: "Does it change my listing?",
    a: "No. It only reads public GeM data and reports the filter combinations that would put your price at L1. Applying them stays your decision, made in your own seller account.",
  },
];

/* Scroll progress, cursor spotlight and section reveals. All three are
   additive: without JS or with reduced motion the page is complete and
   static, never blank. */
function usePremiumChrome() {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const root = document.querySelector(".lp");
    if (!root) return undefined;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let scrollRaf = 0;
    const onScroll = () => {
      if (scrollRaf) return;
      scrollRaf = requestAnimationFrame(() => {
        scrollRaf = 0;
        const max = document.documentElement.scrollHeight - window.innerHeight;
        setProgress(max > 0 ? Math.min(1, window.scrollY / max) : 0);
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    let observer;
    if (!reduce && "IntersectionObserver" in window) {
      root.dataset.animate = "on";
      observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-in");
              observer.unobserve(entry.target);
            }
          });
        },
        { rootMargin: "0px 0px -10% 0px", threshold: 0.06 }
      );
      root.querySelectorAll(".lp-rise").forEach((el) => observer.observe(el));
    }


    return () => {
      window.removeEventListener("scroll", onScroll);
      observer?.disconnect();
      if (scrollRaf) cancelAnimationFrame(scrollRaf);
    };
  }, []);

  return progress;
}

export default function Landing({ onLaunch }) {
  const [theme, toggleTheme] = useTheme();
  const progress = usePremiumChrome();

  return (
    <div className="lp">
      <div className="lp-glow" aria-hidden="true" />
      <div className="lp-dotfield" aria-hidden="true" />
      <div className="lp-grain" aria-hidden="true" />

      <div className="lp-main">
        {/* ── NAV ───────────────────────────────────────── */}
        <nav className="lp-nav">
          <a href="#top" className="lp-brand">
            <span className="lp-brand-mark"><Mark /></span>
            <span className="lp-brand-name">GeM&nbsp;Filter&nbsp;Optimizer</span>
          </a>
          <div className="lp-nav-links">
            <a href="#what">What is L1</a>
            <a href="#tools">The tools</a>
            <a href="#how">How it works</a>
            <a href="#trust">Why trust it</a>
            <button
              type="button"
              className="lp-theme"
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            >
              {theme === "dark" ? (
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                     strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <circle cx="12" cy="12" r="4.5" />
                  <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
                </svg>
              ) : (
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                     strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
                </svg>
              )}
            </button>
            <button type="button" className="lp-btn lp-btn-primary lp-nav-cta" onClick={onLaunch}>
              Launch optimizer <Arrow size={15} />
            </button>
          </div>
          <span className="lp-progress" aria-hidden="true">
            <i style={{ "--p": progress }} />
          </span>
        </nav>

        {/* ── HERO ──────────────────────────────────────── */}
        <section id="top" className="lp-wrap lp-hero">
          <div>
            <div className="lp-pill">
              <span className="lp-dot lp-live" />
              <span className="lp-pill-label">Government e-Marketplace · Seller intelligence</span>
            </div>
            <h1 className="lp-h1">Be the cheapest<br />listing buyers <span className="acc">see</span>.</h1>
            <p className="lp-lead">
              GeM ranks by price inside a filtered set. This tool finds the golden-filter
              combination that makes your price <strong>L1</strong> — the lowest valid one in
              that niche — then verifies every path against GeM live before it reports it.
            </p>
            <div className="lp-hero-actions">
              <button type="button" className="lp-btn lp-btn-primary lp-btn-lg" onClick={onLaunch}>
                Find your path to L1 <Arrow />
              </button>
              <a href="#how" className="lp-btn lp-btn-ghost lp-btn-lg">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                     strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <polygon points="6 4 20 12 6 20 6 4" fill="currentColor" stroke="none" />
                </svg>
                See how it works
              </a>
            </div>
            <div className="lp-stats">
              <div className="lp-stat">
                <span className="lp-stat-n">~20s</span>
                <span className="lp-stat-l">to scan a category</span>
              </div>
              <span className="lp-div" />
              <div className="lp-stat">
                <span className="lp-stat-n">4 deep</span>
                <span className="lp-stat-l">filter combinations</span>
              </div>
              <span className="lp-div" />
              <div className="lp-stat">
                <span className="lp-stat-n ok">Live-verified</span>
                <span className="lp-stat-l">every reported path</span>
              </div>
            </div>
          </div>

          <div className="lp-console-wrap">
            <div className="lp-window">
              <div className="lp-win-bar">
                <span className="lp-win-dots" aria-hidden="true"><i /><i /><i /></span>
                <span className="lp-win-url">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#22C55E"
                       strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <rect x="4" y="11" width="16" height="10" rx="2" />
                    <path d="M8 11V8a4 4 0 0 1 8 0v3" />
                  </svg>
                  mkp.gem.gov.in/…/search · chain hunt
                </span>
              </div>
              <div className="lp-console">
                <div className="lp-sweep" aria-hidden="true" />
              <div className="lp-cons-head">
                <span className="lp-cons-tag">
                  <Nodes size={16} sw={2} />
                  CHAIN&nbsp;HUNT
                </span>
                <span className="lp-badge win">
                  <span className="bdot" />
                  WIN
                </span>
              </div>

              <div className="lp-cons-price">
                <div className="k">YOUR ACHIEVABLE L1 FLOOR</div>
                <div className="lp-price-row">
                  <span className="lp-price">₹1,249</span>
                  <span className="lp-was">₹1,540</span>
                  <span className="lp-under">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M6 15l6-6 6 6" />
                    </svg>
                    undercuts field
                  </span>
                </div>
              </div>

              <div className="lp-chain">
                <div className="lp-chip"><span>Backrest width · 45–50 cm</span><Tick /></div>
                <div className="lp-chip"><span>Warranty · 3 years</span><Tick /></div>
                <div className="lp-chip"><span>Armrest · adjustable</span><Tick /></div>
              </div>

                <div className="lp-cons-foot">
                  <span className="m">6 sellers cleared · 62 requests</span>
                  <span className="v"><TickCircle /> verified on GeM live</span>
                </div>
              </div>
            </div>
            <div className="lp-cons-tag2">SAMPLE RESULT</div>
          </div>
        </section>

        {/* ── METRICS ───────────────────────────────────── */}
        <section className="lp-wrap">
          <div className="lp-metrics lp-rise">
            <div className="lp-metric">
              <div className="lp-metric-n">600<small> / 47,000</small></div>
              <div className="lp-metric-l">products sampled per category</div>
            </div>
            <div className="lp-metric">
              <div className="lp-metric-n">3</div>
              <div className="lp-metric-l">verdicts: WIN · PARTIAL · STUCK</div>
            </div>
            <div className="lp-metric">
              <div className="lp-metric-n">~25–30s</div>
              <div className="lp-metric-l">to hunt &amp; verify a path</div>
            </div>
            <div className="lp-metric">
              <div className="lp-metric-n acc">Checked</div>
              <div className="lp-metric-l">against GeM, not guessed</div>
            </div>
          </div>
          <div className="lp-tested">
            <span className="h">Hunted in testing</span>
            <ul>
              <li>Revolving chairs</li>
              <li>Computer printers</li>
              <li>Classroom desks</li>
              <li>Desktop computers</li>
              <li>Cotton bed sheets</li>
            </ul>
          </div>
        </section>

        {/* ── WHAT IS L1 ────────────────────────────────── */}
        <section id="what" className="lp-wrap lp-sec lp-rise">
          <div className="lp-split">
            <div>
              <span className="lp-eyebrow">The mechanic</span>
              <h2>Price alone doesn't win. The right filters do.</h2>
              <p>
                Buyers on GeM narrow to a set of specifications, then sort by price. Whoever is
                cheapest <em>inside that filtered set</em> is L1 — the listing they actually
                compare and buy.
              </p>
              <p>
                Pick the right combination of <strong>golden filters</strong> and your existing
                price becomes the lowest valid one in a niche your rivals never tuned for. That
                combination is what this tool hunts down.
              </p>
            </div>
            <div className="lp-setcard">
              <div className="k">A FILTERED SET, SORTED BY PRICE</div>
              <div className="lp-rows">
                <div className="lp-row l1">
                  <span className="rk">L1</span>
                  <span className="rn">Your listing</span>
                  <span className="rp">₹1,249</span>
                </div>
                <div className="lp-row">
                  <span className="rk">L2</span>
                  <span className="rn">Competitor A</span>
                  <span className="rp">₹1,540</span>
                </div>
                <div className="lp-row">
                  <span className="rk">L3</span>
                  <span className="rn">Competitor B</span>
                  <span className="rp">₹1,610</span>
                </div>
                <div className="lp-row dim">
                  <span className="rk">L4</span>
                  <span className="rn">Competitor C</span>
                  <span className="rp">₹1,720</span>
                </div>
              </div>
              <div className="lp-setnote">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#F0353F"
                     strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
                </svg>
                Same price. Better filter niche. You're the one buyers see first.
              </div>
            </div>
          </div>
        </section>

        {/* ── TOOLS ─────────────────────────────────────── */}
        <section id="tools" className="lp-wrap lp-sec lp-rise">
          <div className="lp-sec-head">
            <span className="lp-eyebrow">Three ways to find the slot</span>
            <h2 className="lp-h2">One console, three moves.</h2>
          </div>
          <div className="lp-tools">
            <article className="lp-tool">
              <span className="lp-tool-ic"><Scan /></span>
              <h3>Category Scan</h3>
              <div className="lp-tool-kick">MAP THE BATTLEFIELD</div>
              <p>
                Pulls products and every golden filter through GeM's JSON API — up to 50 pages
                sampled per category, ~600 products from a 47,000-item catalog in around 20 seconds.
              </p>
              <div className="lp-tool-foot">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#82828F"
                     strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M4 12h16M4 6h16M4 18h10" />
                </svg>
                products + filters, indexed
              </div>
            </article>

            <article className="lp-tool feat">
              <span className="lp-tool-ic"><Nodes color="#F0353F" /></span>
              <h3>Chain Hunt</h3>
              <div className="lp-tool-kick">FIND THE PATH</div>
              <p>
                A breadth-first search over golden-filter combinations up to four deep, in memory —
                then live verification of the strongest candidates against GeM. It reports the best
                price floor you can actually reach.
              </p>
              <div className="lp-verdicts">
                <span className="lp-verdict win">WIN</span>
                <span className="lp-verdict partial">PARTIAL</span>
                <span className="lp-verdict stuck">STUCK</span>
              </div>
            </article>

            <article className="lp-tool">
              <span className="lp-tool-ic"><Crosshair /></span>
              <h3>Surgical Strike</h3>
              <div className="lp-tool-kick">COUNTER ONE RIVAL</div>
              <p>
                Paste a competitor's listing URL. It reads their specs, matches them to golden
                filters, and live-tests the counter-values that would quietly exclude them from
                your niche.
              </p>
              <div className="lp-tool-foot">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#82828F"
                     strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" />
                  <path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" />
                </svg>
                one URL in, counters out
              </div>
            </article>
          </div>
        </section>

        {/* ── HOW IT WORKS ──────────────────────────────── */}
        <section id="how" className="lp-how">
          <div className="lp-wrap lp-sec">
            <div className="lp-sec-head">
              <span className="lp-eyebrow">The pipeline</span>
              <h2 className="lp-h2">From category to a checked path.</h2>
            </div>
            <div className="lp-steps lp-rise">
              <div className="lp-step">
                <div className="lp-step-n">01</div>
                <Scan size={24} color="#F5F5F7" sw={1.7} className="lp-step-ic" />
                <h4>Scan the category</h4>
                <p>Paste a canonical GeM category URL. The tool indexes its products and golden filters.</p>
              </div>
              <div className="lp-step">
                <div className="lp-step-n">02</div>
                <Nodes size={24} color="#F5F5F7" sw={1.7} className="lp-step-ic" />
                <h4>Hunt chains in memory</h4>
                <p>A breadth-first search combines filters up to four deep, scoring each path's price floor.</p>
              </div>
              <div className="lp-step">
                <div className="lp-step-n">03</div>
                <TickCircle size={24} color="#F5F5F7" sw={1.7} className="lp-step-ic" />
                <h4>Verify against GeM live</h4>
                <p>The top candidates are re-checked through a real browser, so no path is reported on trust.</p>
              </div>
              <div className="lp-step last">
                <div className="lp-step-n">04</div>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#F0353F"
                     strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"
                     className="lp-step-ic" aria-hidden="true">
                  <path d="M5 3v16l7-4 7 4V3z" />
                </svg>
                <h4>Get checked L1 paths</h4>
                <p>A ranked, verified list of filter combinations that put your price at L1 — ready to apply.</p>
              </div>
            </div>
          </div>
        </section>

        {/* ── RUN LOG ───────────────────────────────────── */}
        <section className="lp-wrap lp-sec lp-rise">
          <div className="lp-split">
            <div>
              <span className="lp-eyebrow">A real run</span>
              <h2>Watch one go.</h2>
              <p>
                This is an actual hunt against GeM's printer category — not a mock. The scan
                samples the catalog, the search combines filters in memory, and every candidate
                worth reporting is re-checked against GeM before it reaches the screen.
              </p>
              <p>
                The numbers move with the category. What doesn't move is the last line: nothing
                is reported as a win until GeM itself returned it.
              </p>
            </div>
            <div className="lp-term">
              <div className="lp-term-bar">
                <span>CHAIN HUNT · computer-printer-v2</span>
                <span>target ₹10,000</span>
              </div>
              <div className="lp-term-body">
                <div className="lp-term-line cmd">
                  <span className="tag">$</span>
                  <span className="txt">hunt --category computer-printer --target 10000</span>
                </div>
                <div className="lp-term-line">
                  <span className="tag">scan</span>
                  <span className="txt">600 products · 11 golden filters indexed</span>
                  <span className="ms">17.7s</span>
                </div>
                <div className="lp-term-line">
                  <span className="tag">hunt</span>
                  <span className="txt">breadth-first, depth 4 · 61 live checks</span>
                  <span className="ms">24.9s</span>
                </div>
                <div className="lp-term-line">
                  <span className="tag">verify</span>
                  <span className="txt">17 paths confirmed · 1 flagged unconfirmed</span>
                </div>
                <div className="lp-term-line done">
                  <span className="tag">result</span>
                  <span className="txt">WIN · floor ₹11,210 · 6 sellers in niche</span>
                </div>
              </div>
            </div>
          </div>
          <p className="lp-term-note">
            Measured on the live GeM catalog. Runs vary with category size and how GeM's index
            is behaving that day.
          </p>
        </section>

        {/* ── TRUST ─────────────────────────────────────── */}
        <section id="trust" className="lp-wrap lp-sec lp-rise">
          <div className="lp-split">
            <div>
              <span className="lp-eyebrow">Why trust the result</span>
              <h2>Checked, not guessed.</h2>
              <p>
                A filter path that looks unbeatable in memory can collapse against GeM's live index.
                So the paths that reach your screen have already survived a real check — and where
                GeM's index behaves strangely, the tool says so instead of hiding it.
              </p>
            </div>
            <div className="lp-trust-list">
              <div className="lp-trust-item">
                <TickCircle size={22} sw={1.9} />
                <div>
                  <h4>Live verification, every path</h4>
                  <p>The in-memory search proposes; a real browser confirms. Reported paths are ones GeM returned.</p>
                </div>
              </div>
              <div className="lp-trust-item">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#B4B4C2"
                     strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
                <div>
                  <h4>WAF-aware fetching</h4>
                  <p>One long-lived headless browser, capped concurrency, staggered requests and cookie refresh — steady, not blocked.</p>
                </div>
              </div>
              <div className="lp-trust-item">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#EAB308"
                     strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M12 9v4M12 17h.01" />
                  <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
                </svg>
                <div>
                  <h4>Unconfirmed leads, surfaced honestly</h4>
                  <p>When GeM's index rejects a literal filter value, that path is flagged for manual review — never silently dropped or oversold.</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── FAQ ───────────────────────────────────────── */}
        <section id="faq" className="lp-wrap lp-sec lp-rise">
          <div className="lp-sec-head">
            <h2 className="lp-h2">Questions worth asking first.</h2>
          </div>
          <div className="lp-faq">
            {FAQ.map(({ q, a }) => (
              <details key={q} className="lp-faq-item">
                <summary className="lp-faq-q">
                  {q}
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
                    <path d="M12 5v14M5 12h14" />
                  </svg>
                </summary>
                <div className="lp-faq-a">{a}</div>
              </details>
            ))}
          </div>
        </section>

        {/* ── FINAL CTA ─────────────────────────────────── */}
        <section id="start" className="lp-wrap" style={{ paddingBottom: "104px" }}>
          <div className="lp-cta-box">
            <div className="lp-cta-inner">
              <div>
                <h2>Find the filter path that puts you at L1.</h2>
                <p>
                  Point it at a category, or at a single competitor. It hunts the combinations,
                  checks them against GeM live, and hands you the ones that win.
                </p>
              </div>
              <button type="button" className="lp-btn lp-btn-primary" onClick={onLaunch}>
                Launch the optimizer <Arrow size={18} />
              </button>
            </div>
          </div>
        </section>

        {/* ── FOOTER ────────────────────────────────────── */}
        <footer className="lp-wrap lp-footer">
          <div className="lp-foot-top">
            <div className="lp-foot-brand">
              <div className="row">
                <span className="lp-brand-mark"><Mark size={16} rays={false} /></span>
                <span className="nm">GeM Filter Optimizer</span>
              </div>
              <p>
                A competitive-analysis instrument. It reads publicly accessible, unauthenticated
                data feeds published on the Government e-Marketplace for information synthesis.
                Users assume adherence to target-domain guidelines.
              </p>
            </div>
            <div className="lp-foot-cols">
              <div className="lp-foot-col">
                <span className="h">Product</span>
                <a href="#what">What is L1</a>
                <a href="#tools">The tools</a>
                <a href="#how">How it works</a>
              </div>
              <div className="lp-foot-col">
                <span className="h">Built with</span>
                <span>FastAPI · Playwright</span>
                <span>React 18 · Vite</span>
                <span>Runs on localhost or Docker</span>
              </div>
            </div>
          </div>
          <div className="lp-foot-bar">
            <span className="c">© 2026 GeM Filter Optimizer</span>
            <span className="t">Built for scale. Created for results.</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
