import { useEffect, useState } from "react";
import { Sun, Moon } from "@phosphor-icons/react";

function getInitialTheme() {
  // Black by default -- only an explicit prior toggle switches it to light.
  const stored = localStorage.getItem("theme");
  return stored === "light" ? "light" : "dark";
}

export default function Header() {
  const [theme, setTheme] = useState(getInitialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  return (
    <div className="hdr">
      <div>
        <div className="hdr-eyebrow-row">
          <span className="hdr-eyebrow">GeM India · Rank Engine</span>
          <span className="hdr-dots" aria-hidden="true" />
        </div>
        <h1>
          Find Your <em>L1 Rank</em>. Every Time.
        </h1>
        <p className="hdr-sub">
          Paste a category URL and your price. We surface the exact{" "}
          <strong>filter combinations</strong> that make you the{" "}
          <strong>cheapest listing</strong> buyers see.
        </p>
      </div>
      <button
        type="button"
        className="theme-toggle"
        onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
        aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      >
        {theme === "dark" ? <Sun size={18} weight="bold" /> : <Moon size={18} weight="bold" />}
      </button>
    </div>
  );
}
