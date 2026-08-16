import { createContext, useContext, useEffect, useState } from "react";

// Applies data-theme="light" | "dark" on <html>, which flips every CSS
// variable defined in index.css. Persisted so a reload keeps your choice,
// and defaults to the OS-level preference on first visit.
const ThemeContext = createContext(null);

function getInitialTheme() {
  const saved = localStorage.getItem("pwssap_theme");
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("pwssap_theme", theme);
  }, [theme]);

  const toggleTheme = () => setTheme(t => (t === "light" ? "dark" : "light"));

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

// Small context file — keeping the provider and its hook together here is
// clearer than splitting into a third file for one hook.
// eslint-disable-next-line react-refresh/only-export-components
export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
