"""
params.py

This module centralizes all region-specific knobs and parameters:
- Cities + exact map centers (for geolocation spoof & viewport anchoring)
- Keywords for boolean search 
- UI strings (cookies, "Search this area")
- Locale words/units for parsing ratings & reviews
- Region-aware UI helpers and parsing helpers

Exports used by scraper.py:
CITIES, CITY_CENTER_LOOKUP, KEYWORDS, SEARCH_THIS_AREA_TEXTS, COOKIE_ACCEPT_TEXTS,
REVIEW_WORDS, STAR_WORDS,
dismiss_signin_or_promos(), click_next_page_if_present(),
_parse_rating_from_string(), _review_word_pattern(), _parse_reviews_from_string()
"""

from __future__ import annotations
import re
import unicodedata

# =========================================================
# Cities along with their Countries and the city centers.
# =========================================================
CITIES_DATA = [
    # Germany
    {"name": "Berlin, Germany", "lat": 52.5200, "lon": 13.4050},
    {"name": "Munich, Germany", "lat": 48.1351, "lon": 11.5820},
    {"name": "Hamburg, Germany", "lat": 53.5511, "lon": 9.9937},
    {"name": "Cologne, Germany", "lat": 50.9375, "lon": 6.9603},
    {"name": "Frankfurt, Germany", "lat": 50.1109, "lon": 8.6821},
    # France
    {"name": "Paris, France", "lat": 48.8566, "lon": 2.3522},
    {"name": "Marseille, France", "lat": 43.2965, "lon": 5.3698},
    {"name": "Lyon, France", "lat": 45.7640, "lon": 4.8357},
    {"name": "Toulouse, France", "lat": 43.6047, "lon": 1.4442},
    {"name": "Nice, France", "lat": 43.7102, "lon": 7.2620},
    # Italy
    {"name": "Rome, Italy", "lat": 41.9028, "lon": 12.4964},
    {"name": "Milan, Italy", "lat": 45.4642, "lon": 9.1900},
    {"name": "Naples, Italy", "lat": 40.8518, "lon": 14.2681},
    {"name": "Turin, Italy", "lat": 45.0703, "lon": 7.6869},
    {"name": "Palermo, Italy", "lat": 38.1157, "lon": 13.3615},
    # Spain
    {"name": "Madrid, Spain", "lat": 40.4168, "lon": -3.7038},
    {"name": "Barcelona, Spain", "lat": 41.3851, "lon": 2.1734},
    {"name": "Valencia, Spain", "lat": 39.4699, "lon": -0.3763},
    {"name": "Seville, Spain", "lat": 37.3891, "lon": -5.9845},
    {"name": "Zaragoza, Spain", "lat": 41.6488, "lon": -0.8891},
]

# Back-compat derived exports
CITIES = [c["name"] for c in CITIES_DATA]
CITY_CENTER_LOOKUP = {c["name"].lower(): (c["lat"], c["lon"]) for c in CITIES_DATA}

# =========================================================
# KEYWORDS for cafés (EN + DE + FR + IT + ES); deduped & expanded
# =========================================================
KEYWORDS = [
    # English & general
    "salon", "saloon", "beauty salon", "hair salon",
    "hairdresser", "hair dresser", "hair stylist", "hairstylist",
    "hair studio", "haircut", "hair cut",
    "barber", "barbershop", "barber shop", "barbering",
    "men's salon", "ladies salon", "unisex salon",
    "beauty parlour", "beauty parlor",
    "spa", "day spa",
    "nail salon", "nail bar", "mani pedi", "blow dry bar",

    # German
    "Friseur", "Friseurin", "Friseursalon", "Haarsalon", "Haarstudio",
    "Herrenfriseur", "Damenfriseur",
    "Barbier", "Barbershop",
    "Schönheitssalon", "Kosmetiksalon", "Kosmetikstudio",
    "Nagelstudio", "Spa", "Wellness",

    # French
    "salon de coiffure", "coiffeur", "coiffeuse",
    "barbier", "barbershop",
    "salon de beauté", "institut de beauté", "centre de beauté",
    "esthéticienne", "esthétique",
    "onglerie", "manucure", "pédicure", "spa",

    # Italian
    "parrucchiere", "parrucchiera",
    "salone di parrucchiere", "salone di bellezza",
    "barbiere", "barberia",
    "centro estetico", "estetista",
    "salone unisex", "salone uomo", "salone donna",
    "centro benessere", "spa",
    "nail bar", "salone unghie", "manicure", "pedicure",

    # Spanish (incl. Catalan variants)
    "peluquería", "peluqueria", 
    "peluquero", "peluquera",
    "barbería", "barberia", "barbero",
    "salón de belleza", "salon de belleza",
    "centro de estética", "centro de estetica", "estética", "estetica",
    "spa", "balneario",
    "salón de uñas", "salon de uñas", "salon de unas",
    "manicura", "pedicura", "nail bar",

    # Catalan
    "perruqueria", "barberia",
    "saló de bellesa", "centre d'estètica", "estètica",
    "saló d'ungles", "manicura", "pedicura", "spa",
]

# =========================================================
# UI strings (cookies, "Search this area")
# =========================================================
SEARCH_THIS_AREA_TEXTS = [
    # English
    "Search this area", "Search in this area",
    # German
    "In diesem Bereich suchen", "In diesem Gebiet suchen",
    # French
    "Rechercher dans cette zone", "Rechercher dans la zone",
    # Italian
    "Cerca in quest'area", "Cerca in questa zona",
    # Spanish / Catalan
    "Buscar en esta zona", "Buscar en esta área",
    "Cerca en aquesta zona",
]

COOKIE_ACCEPT_TEXTS = [
    # English
    "Accept all", "Accept", "I agree", "Agree", "Accept cookies", "Allow all", "Got it", "OK",

    # German
    "Alle akzeptieren", "Akzeptieren", "Ich stimme zu", "Zustimmen",

    # French
    "Tout accepter", "Accepter", "J’accepte", "J'accepte", "D’accord", "D'accord",

    # Italian
    "Accetta tutto", "Accetta", "Accetto", "Sono d'accordo",

    # Spanish / Catalan
    "Aceptar todo", "Aceptar", "Estoy de acuerdo", "De acuerdo",
    "Acceptar tot", "D’acord", "D'acord",
]

# =========================================================
# Locale vocabulary for parsing ratings & reviews
# =========================================================
REVIEW_WORDS = (
    # English
    "review", "reviews",
    # German
    "bewertung", "bewertungen", "rezension", "rezensionen",
    # French
    "avis", "évaluation", "évaluations", "note", "notes",
    # Italian
    "recensione", "recensioni", "valutazione", "valutazioni",
    # Spanish / Catalan
    "reseña", "reseñas", "opinión", "opiniones", "valoración", "valoraciones",
)

STAR_WORDS = (
    # English
    "star", "stars",
    # German
    "stern", "sterne",
    # French
    "étoile", "étoiles",
    # Italian
    "stella", "stelle",
    # Spanish / Catalan
    "estrella", "estrellas",
)

# Map compact count units to multipliers
COUNT_UNITS = {
    # English
    "k": 1_000, "K": 1_000,
    "m": 1_000_000, "M": 1_000_000,

    # German (spelled/abbr)
    "tausend": 1_000, "Tausend": 1_000, "Tsd.": 1_000, "Tsd": 1_000,
    "Million": 1_000_000, "Millionen": 1_000_000, "Mio.": 1_000_000, "Mio": 1_000_000,

    # French
    "million": 1_000_000, "millions": 1_000_000,

    # Italian
    "mille": 1_000, "mila": 1_000,
    "milione": 1_000_000, "milioni": 1_000_000,

    # Spanish / Catalan
    "mil": 1_000,
    "millón": 1_000_000, "millones": 1_000_000,
    "milió": 1_000_000, "milions": 1_000_000,
}

# =========================================================
# Compiled regex (single definitions, reused everywhere)
# =========================================================

# Star words (as a single alternation) for rating parser
_STAR_WORDS_ALT = r"(?:stars?|stern(?:e)?|étoiles?|stella(?:e)?|estrellas?)"

# Review words alternation (used by multiple parsers)
_REVIEW_WORDS_ALT = (
    r"(?:"
    r"reviews?"                               # EN
    r"|bewertung(?:en)?|rezension(?:en)?"     # DE
    r"|avis|évaluations?|notes?"              # FR
    r"|recensioni?|valutazioni?"              # IT
    r"|reseñas?|opiniones?|valoraciones?"     # ES
    r")"
)

# Compact/spelled unit alternation
_UNITS_ALT = (
    r"(?:K|k|M|m"
    r"|tausend|Tausend|Tsd\.?|Million(?:en)?|Mio\.?"
    r"|million|millions"
    r"|mille|mila|milione|milioni"
    r"|mil|millón|millones|milió|milions"
    r")"
)

# Compiled patterns
RATING_RE = re.compile(
    rf"([0-5](?:[.,]\d)?)\s*(?:/|[\s])?\s*5?(?:\s*{_STAR_WORDS_ALT})?",
    re.IGNORECASE,
)
COMPACT_NUM_UNIT_RE = re.compile(
    rf"(\d+(?:[.,]\d+)?)\s*{_UNITS_ALT}",
    re.IGNORECASE,
)
EXPLICIT_NUM_REV_RE = re.compile(
    rf"([\d\s.,]+)\s*{_REVIEW_WORDS_ALT}",
    re.IGNORECASE,
)
PAREN_NUM_RE = re.compile(r"\(([\d\s.,]+)\)")
BIG_NUM_RE = re.compile(r"(\d[\d\s.,]{2,})")

# =========================================================
# Shared low-level helpers (digits & numbers)
# =========================================================
def _to_ascii_digits(s: str) -> str:
    """Convert Unicode digits (Arabic-Indic etc.) to ASCII 0-9."""
    out = []
    for ch in s or "":
        try:
            if unicodedata.category(ch) == "Nd":
                out.append(str(unicodedata.digit(ch)))
            else:
                out.append(ch)
        except Exception:
            out.append(ch)
    return "".join(out)

def _parse_compact_count(num: str, unit: str) -> int | None:
    """Parse compact/spelled counts like '1.2K' / '1,2 Mio.' / '2 mila' / '1 millón' → int."""
    if not num or not unit:
        return None
    mult = COUNT_UNITS.get(unit.strip())
    if not mult:
        return None
    num_norm = _to_ascii_digits(num).replace(",", ".")
    try:
        return int(round(float(num_norm) * mult))
    except Exception:
        return None

def _parse_plain_int(num: str) -> int | None:
    """Parse '1,234' / '1.234' / '1 234' → int."""
    if not num:
        return None
    cleaned = re.sub(r"[^\d]", "", _to_ascii_digits(num))
    return int(cleaned) if cleaned else None

# =========================================================
# Region-aware UI helpers
# =========================================================
DISMISS_BUTTON_SELECTORS = [
    # English
    'button:has-text("No thanks")',
    'button:has-text("Not now")',
    'button:has-text("Skip")',
    'button:has-text("Close")',
    'button:has-text("Dismiss")',

    # German
    'button:has-text("Nein danke")',
    'button:has-text("Nicht jetzt")',
    'button:has-text("Später")',
    'button:has-text("Überspringen")',
    'button:has-text("Schließen")',
    'button:has-text("Ablehnen")',

    # French
    'button:has-text("Non merci")',
    'button:has-text("Pas maintenant")',
    'button:has-text("Plus tard")',
    'button:has-text("Ignorer")',
    'button:has-text("Fermer")',
    'button:has-text("Refuser")',

    # Italian
    'button:has-text("No grazie")',
    'button:has-text("Non ora")',
    'button:has-text("Più tardi")',
    'button:has-text("Ignora")',
    'button:has-text("Chiudi")',
    'button:has-text("Rifiuta")',

    # Spanish / Catalan
    'button:has-text("No, gracias")',
    'button:has-text("Ahora no")',
    'button:has-text("Más tarde")',
    'button:has-text("Omitir")',
    'button:has-text("Cerrar")',
    'button:has-text("Rechazar")',
    'button:has-text("Ara no")',
    'button:has-text("Més tard")',
    'button:has-text("Tanca")',
]

NEXT_BUTTON_SELECTORS = [
    # English
    'button[aria-label*="Next"]',
    'button:has-text("Next")',
    # German
    'button:has-text("Weiter")',
    'button:has-text("Nächste")',
    'button:has-text("Nächste Seite")',
    # French
    'button:has-text("Suivant")',
    'button:has-text("Suivante")',
    'button:has-text("Page suivante")',
    # Italian
    'button:has-text("Avanti")',
    'button:has-text("Successivo")',
    'button:has-text("Pagina successiva")',
    # Spanish / Catalan
    'button:has-text("Siguiente")',
    'button:has-text("Página siguiente")',
    'button:has-text("Següent")',
]

def dismiss_signin_or_promos(page) -> None:
    for sel in DISMISS_BUTTON_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0:
                btn.click(timeout=1200)
        except Exception:
            pass

def click_next_page_if_present(page) -> bool:
    for sel in NEXT_BUTTON_SELECTORS:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                el.click(timeout=1200)
                try:
                    page.wait_for_selector('[role="progressbar"]', timeout=3000, state="detached")
                except Exception:
                    pass
                return True
        except Exception:
            pass
    return False

# =========================================================
# Parsing (ratings & reviews)
# =========================================================
def _parse_rating_from_string(s: str) -> str | None:
    """Return rating as 'X.Y' if present in localized string."""
    if not s:
        return None
    s_norm = _to_ascii_digits(s)
    m = RATING_RE.search(s_norm)
    if m:
        try:
            return f"{float(m.group(1).replace(',', '.')):.1f}"
        except Exception:
            return None
    # Fallback: if any star word exists, pick first 0–5 floatish number
    if any(w in s_norm.lower() for w in STAR_WORDS):
        m2 = re.search(r"([0-5](?:[.,]\d)?)", s_norm)
        if m2:
            try:
                return f"{float(m2.group(1).replace(',', '.')):.1f}"
            except Exception:
                return None
    return None

def _review_word_pattern() -> str:
    """Back-compat: return the review word alternation as a plain regex string."""
    return _REVIEW_WORDS_ALT

def _parse_reviews_from_string(s: str) -> int | None:
    """Return review count (int) from EN/DE/FR/IT/ES localized strings."""
    if not s:
        return None
    s_norm = _to_ascii_digits(s)

    # 1) compact/spelled units + review word nearby
    km = COMPACT_NUM_UNIT_RE.search(s_norm)
    if km and any(w in s_norm.lower() for w in REVIEW_WORDS):
        c = _parse_compact_count(km.group(1), km.group(2))
        if c is not None:
            return c

    # 2) explicit "1,234 reviews" / "1.234 Bewertungen" / "1 234 avis" / "1.234 recensioni" / "1.234 reseñas"
    m = EXPLICIT_NUM_REV_RE.search(s_norm)
    if m:
        c = _parse_plain_int(m.group(1))
        if c is not None:
            return c

    # 3) parentheses near ratings: "(1,234)"
    pm = PAREN_NUM_RE.search(s_norm)
    if pm:
        c = _parse_plain_int(pm.group(1))
        if c is not None:
            return c

    # 4) compact count without review word, but with a unit somewhere
    km2 = COMPACT_NUM_UNIT_RE.search(s_norm)
    if km2:
        c = _parse_compact_count(km2.group(1), km2.group(2))
        if c is not None:
            return c

    # 5) last resort: any large-ish number (avoid 4.5 ratings)
    for token in BIG_NUM_RE.findall(s_norm):
        c = _parse_plain_int(token)
        if c and c >= 10:
            return c

    return None
 