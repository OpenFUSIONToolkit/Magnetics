// Header gear menu — the single home for GLOBAL appearance preferences, so the
// header stays uncluttered and future prefs don't each grow a new loose button.
//
// To add a new global appearance preference:
//   1. store.ts   — add its value + apply*() + set*() (mirror `fontScale`).
//   2. here       — add one <div className="settings-row"> with its control.
// No header edits, no new icons.
import { useEffect, useRef, useState } from "react";
import { useStore, FONT_SCALES, type FontSizeKey } from "../store";
import ThemeToggle from "./ThemeToggle";

const SIZE_PRESETS: { key: FontSizeKey; label: string }[] = [
  { key: "S", label: "S" },
  { key: "M", label: "M" },
  { key: "L", label: "L" },
  { key: "XL", label: "XL" },
];

export default function SettingsMenu() {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const fontScale = useStore((s) => s.fontScale);
  const setFontScale = useStore((s) => s.setFontScale);

  // Close on outside click / Escape while open.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="settings-menu" ref={menuRef}>
      <button
        type="button"
        className={`icon-btn${open ? " open" : ""}`}
        onClick={() => setOpen((v) => !v)}
        title="Settings"
        aria-label="Settings"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {/* gear */}
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>

      {open && (
        <div className="settings-menu-popover" role="menu" aria-label="Appearance settings">
          <h4>Appearance</h4>

          <div className="settings-row">
            <span className="settings-label">Theme</span>
            <ThemeToggle />
          </div>

          <div className="settings-row">
            <span className="settings-label">Text size</span>
            <div className="seg" role="group" aria-label="Text size">
              {SIZE_PRESETS.map(({ key, label }) => {
                const active = fontScale === FONT_SCALES[key];
                return (
                  <button
                    key={key}
                    type="button"
                    className={`seg-btn${active ? " active" : ""}`}
                    onClick={() => setFontScale(FONT_SCALES[key])}
                    aria-pressed={active}
                    title={`${label} text`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
