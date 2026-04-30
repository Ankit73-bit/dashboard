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
    "cyan":     "#00f5ff",
    "green":    "#30d158",
    "purple":   "#bf5af2",
    "orange":   "#ff9f0a",
    "pink":     "#ff375f",
    "blue":     "#0a84ff",
}

TINTS = {
    "#00f5ff": {"bg": "#062d30", "mid": "#0a4a4e", "bdr": "#0d6b70"},
    "#30d158": {"bg": "#082a12", "mid": "#0f4020", "bdr": "#185c2e"},
    "#bf5af2": {"bg": "#2a1040", "mid": "#3d1860", "bdr": "#5a2580"},
    "#ff9f0a": {"bg": "#2e1e00", "mid": "#4a3000", "bdr": "#6b4500"},
    "#ff375f": {"bg": "#300a14", "mid": "#4e1020", "bdr": "#701830"},
    "#0a84ff": {"bg": "#001830", "mid": "#002850", "bdr": "#003d78"},
}


def t(accent, level="bg"):
    """Return the tinted color for a given accent and level (bg / mid / bdr)."""
    return TINTS.get(accent, {}).get(level, "#1a1a2e")
