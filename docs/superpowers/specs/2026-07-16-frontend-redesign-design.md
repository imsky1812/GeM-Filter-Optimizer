# Frontend Redesign: Light SaaS Wizard

## Context

The app currently ships a single-page dark "Obsidian Precision" theme (glassmorphic
cards, purple/teal/amber neon accents, JetBrains Mono for numbers) with all steps
(URL input, price input, mandatory filters, Surgical Strike, Chain Hunt results)
visible on the page at once, gated only by whether prior data exists.

Goal: a fresh light, minimal SaaS-style visual language, restructured into a guided
step-by-step wizard so a first-time user is never unsure what to do next, with the
results screen simplified to lead with the headline answer and defer detail.

This is a **visual/structural frontend refactor only** — no backend, API contract,
or algorithm changes. All existing props/handlers in `App.jsx` are reused as-is.

## 1. Visual system

- **Palette:** light background (`--surface: #FAFAFB`, cards `#FFFFFF`), neutral
  gray-900 (`#1A1A1F`) body text, gray-500 secondary text, gray-200 hairline
  borders. No glow/glass effects.
- **Accent:** indigo (`#4F46E5` primary / `#4338CA` hover / `#EEF2FF` tint
  background) for primary actions, links, active step indicator. Chosen for
  continuity with today's purple brand while fitting a light SaaS aesthetic
  (Linear/Stripe-adjacent).
- **Semantic colors** (retuned as light-safe tints — soft colored background +
  darker text, not glowing borders):
  - Success/L1-win: green (`#16A34A` text / `#F0FDF4` bg)
  - Warning/partial/stuck: amber (`#D97706` text / `#FFFBEB` bg)
  - Danger/blocked: red (`#DC2626` text / `#FEF2F2` bg)
- **Typography:** Inter only, all weights. JetBrains Mono is dropped; numeric
  hierarchy (prices, stats) comes from weight/size, not a second typeface.
- **Cards:** white surface, 1px `#E5E7EB` border, `border-radius: 12–16px`
  (existing `--radius`/`--radius-lg` tokens kept), shadow only on hover
  (`0 4px 16px rgba(0,0,0,0.06)`), flat at rest.
- **Spacing/radius tokens:** existing 4px-based `--space-*` and `--radius-*`
  tokens in `index.css` are reused (typeface/theme-agnostic); only the color
  tokens (`--surface-*`, `--ink-*`, `--primary*`, `--glass*`) and font tokens
  are replaced.
- No dark-mode toggle is built — this is a one-way theme replacement, not a
  theme system.

## 2. Flow / information architecture

A 4-step wizard. Exactly one step's content is visible at a time. A slim
progress bar sits above the active step:

```
[✓ 1. Category] ─── [✓ 2. Price] ─── [● 3. Analysis] ─── [ 4. Results ]
```

Completed steps show a checkmark and are clickable to go back and edit;
the current step is highlighted; future steps are dimmed and not clickable.

**Step 1 — Category URL**
Paste GeM category URL + location select → "Scrape" button. Same fields as
today's `UrlInput`. On successful scrape, auto-advances to Step 2.

**Step 2 — Your Price**
Price input (₹). An "Advanced: required specs" disclosure, collapsed by
default, expands to today's mandatory-filter picker (unchanged logic from
`PriceInput`). Primary CTA **"Find my L1 path →"** advances to Step 3
(no network call yet — the call happens once a tool is chosen in Step 3).

**Step 3 — Choose analysis**
Two options:
- Primary, larger, pre-emphasized card: **"Sequential Chain Hunt"** — "Find
  filter combinations that make you the cheapest." Clicking it triggers
  `handleChainHunt` and advances to Step 4 showing Chain Hunt results.
- Secondary, smaller card/link below: **"Analyze a specific competitor"**
  (Surgical Strike) — expands an inline URL field (today's `SurgicalStrike`
  input) since it needs one more input (the competitor's product URL)
  before it can run; submitting triggers `handleSurgicalStrike` and advances
  to Step 4 showing Strike results.

**Step 4 — Results**
Shows whichever tool ran (Chain Hunt or Surgical Strike results, restyled
per section 3 below). Actions: "← Back" returns to Step 3 to run the other
tool or re-run the same one; "Start over" resets all state to Step 1.

## 3. Results simplification (Step 4, Chain Hunt)

Collapsed-by-default view shows only the headline answer:
- One status line in plain language: "✓ You can be L1", "⚠ Best floor is
  ₹X", or "✗ No path found" (maps from `chainResults.status` /
  `bestAchievablePrice`, same data as today).
- The winning (or best partial) path's active filters as a compact chip row
  (from `path.activeFilters`, same as today's `chain-active-filters`).
- If multiple paths exist, a simple tab/select to switch between them
  (same `chainPathIdx` mechanism as today, restyled).
- A single **"View elimination steps →"** disclosure that expands, in
  place, the full step-by-step timeline (`path.iterations`) and the
  competitor insights cards (`path.competitorInsights`) — identical data
  and content to today, just deferred behind one click instead of always
  rendered.

No data fields are removed from the API response or from what can be
displayed — only the default visibility changes.

## 4. Component/technical plan

- `App.jsx`: add `currentStep` state (`1 | 2 | 3 | 4`). Existing handlers
  (`handleScrape`, `handleChainHunt`, `handleSurgicalStrike`) are unchanged
  except each calls `setCurrentStep(n)` on success (scrape → 2, tool run →
  4). A `handleStartOver` resets all state and returns to step 1. Clicking
  a completed step in the progress bar sets `currentStep` back without
  clearing downstream state (so e.g. going back from Step 4 to Step 3
  doesn't lose the price entered in Step 2).
- New `StepIndicator.jsx`: renders the 4-step progress bar described above.
  Props: `currentStep`, `furthestStep` (to know which steps are clickable),
  `onStepClick`.
- New `ToolChoice.jsx`: renders Step 3's two option cards + the inline
  Surgical Strike URL field when that option is expanded. Wraps existing
  `SurgicalStrike` input logic; owns no new network logic itself.
- `UrlInput.jsx`, `PriceInput.jsx`, `SurgicalStrike.jsx`, `ChainHuntResults.jsx`:
  restyled in place (same props/logic/handlers) rather than rewritten —
  keeps the change low-risk since no data-fetching or algorithm code is
  touched. `ChainHuntResults.jsx` gets one structural addition: the
  timeline + competitor insights block is wrapped in a collapsed-by-default
  expand/collapse section.
- `index.css`: color and font tokens in `:root` are replaced (light palette,
  Inter-only). Component-level dark-specific rules (glass/glow effects,
  `.stuck-banner`, `.chain-*` classes etc.) are updated to use the new
  tokens rather than hard-coded dark values. Spacing/radius tokens and
  overall class names are kept so existing components don't need prop
  changes.
- No backend, API contract, or algorithm (`chain_hunt.py`, `scraper.py`,
  `crawler.py`) changes.

## 5. Testing / verification

Frontend-only visual/structural change with no automated test suite today.
Verification is manual, via the `run` skill (start Vite dev server, drive
the full flow in-browser):
- Full happy path: URL → scrape → price → Chain Hunt → results, including
  expanding "View elimination steps".
  - Back-navigation from Step 4 → Step 3 → run Surgical Strike instead;
  Step 3 → Step 2 to edit price without re-scraping.
- "Start over" resets to Step 1 cleanly.
- Stuck/no-path-found case renders the plain-language headline correctly.
- Responsive check at common widths (this app is desktop-first per current
  design; no new mobile-specific layout is in scope unless it already broke
  something obvious).
