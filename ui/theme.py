# ─── Theme: Colors & Tints ─────────────────────────────────────────────────────

C = {
    "bg":       "#0a0a0f",
    "sidebar":  "#111118",
    "card":     "#16161f",
    "hover":    "#1e1e2e",
    "border":   "#2a2a3d",
    "text":     "#e8e8f0",
    "muted":    "#8888aa",
    "faint":    "#44445a",
    # ── Accent colours ────────────────────────────────────────────────────────
    "cyan":     "#00f5ff",
    "green":    "#30d158",
    "purple":   "#bf5af2",
    "orange":   "#ff9f0a",
    "pink":     "#ff375f",
    "blue":     "#0a84ff",
    "teal":     "#00c7a8",
    "lime":     "#a8e63d",
    "gold":     "#ffd60a",
    "rose":     "#ff6b9d",
    "indigo":   "#7c5cfc",
    "sky":      "#38bdf8",
}

TINTS = {
    "#00f5ff": {"bg": "#062d30", "mid": "#0a4a4e", "bdr": "#0d6b70"},
    "#30d158": {"bg": "#082a12", "mid": "#0f4020", "bdr": "#185c2e"},
    "#bf5af2": {"bg": "#2a1040", "mid": "#3d1860", "bdr": "#5a2580"},
    "#ff9f0a": {"bg": "#2e1e00", "mid": "#4a3000", "bdr": "#6b4500"},
    "#ff375f": {"bg": "#300a14", "mid": "#4e1020", "bdr": "#701830"},
    "#0a84ff": {"bg": "#001830", "mid": "#002850", "bdr": "#003d78"},
    "#00c7a8": {"bg": "#042820", "mid": "#084038", "bdr": "#0c5c50"},
    "#a8e63d": {"bg": "#1a2a00", "mid": "#2a4200", "bdr": "#3c5e00"},
    "#ffd60a": {"bg": "#2a2000", "mid": "#423200", "bdr": "#5e4800"},
    "#ff6b9d": {"bg": "#2e0a1a", "mid": "#4a1030", "bdr": "#6b1844"},
    "#7c5cfc": {"bg": "#180a38", "mid": "#281258", "bdr": "#3c1e7c"},
    "#38bdf8": {"bg": "#001e30", "mid": "#00304c", "bdr": "#00456e"},
}


def t(accent, level="bg"):
    """Return the tinted color for a given accent and level (bg / mid / bdr)."""
    return TINTS.get(accent, {}).get(level, "#1a1a2e")
