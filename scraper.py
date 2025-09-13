import re
import csv
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote_plus, urlsplit, unquote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from cities_and_keywords import CITIES, KEYWORDS, SEARCH_THIS_AREA_TEXTS, COOKIE_ACCEPT_TEXTS
from config import OUTPUT_CSV, HEADLESS, RATE_LIMIT_SEC, MAX_PER_CITY, MAX_IDLE_ROUNDS, DEBUG_SHOTS


# =======================
# Live terminal preview
# =======================
SHOW_TERMINAL_PREVIEW = True
TERMINAL_PREVIEW_MAX = 40
TERMINAL_COLUMNS = ["name", "rating", "phone", "website", "lat", "lon"]
COL_WIDTHS = {"name": 38, "rating": 6, "phone": 18, "website": 30, "lat": 10, "lon": 11}


EXACT_BOOLEAN_QUERY = " OR ".join(f"\"{t}\"" for t in KEYWORDS)


def _clip(s, w):
    s = (s or "").strip()
    return s if len(s) <= w else (s[: max(0, w - 1)] + "…")

def _domain_or_url(u: str):
    try:
        netloc = urlsplit(u or "").netloc
        return netloc or (u or "")
    except Exception:
        return u

def print_table_header(city):
    if not SHOW_TERMINAL_PREVIEW:
        return
    print(f"\n▶ Live results for {city} (showing first {TERMINAL_PREVIEW_MAX}):", flush=True)
    header = " | ".join(f"{h.upper():{COL_WIDTHS[h]}}" for h in TERMINAL_COLUMNS)
    rule = "-+-".join("-" * COL_WIDTHS[h] for h in TERMINAL_COLUMNS)
    print(header, flush=True)
    print(rule, flush=True)

def print_table_row(d):
    if not SHOW_TERMINAL_PREVIEW:
        return
    row_vals = {
        "name": d.get("name", ""),
        "rating": d.get("rating", ""),
        "phone": d.get("phone", ""),
        "website": _domain_or_url(d.get("website", "")),
        "lat": d.get("lat", ""),
        "lon": d.get("lon", ""),
    }
    line = " | ".join(_clip(str(row_vals[h]), COL_WIDTHS[h]).ljust(COL_WIDTHS[h]) for h in TERMINAL_COLUMNS)
    print(line, flush=True)

# =======================
# Helpers
# =======================
def debug_shot(page, name):
    if not DEBUG_SHOTS:
        return
    try:
        page.screenshot(path=f"debug_{name}.png", full_page=True)
    except Exception:
        pass

def _valid_latlon(lat, lon):
    try:
        lat = float(lat); lon = float(lon)
        return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0
    except Exception:
        return False

def _extract_latlon_from_text(txt: str):
    if not txt:
        return (None, None)
    s = unquote(txt)

    m = re.search(r"/@(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?),", s)
    if m and _valid_latlon(m.group(1), m.group(2)):
        return (float(m.group(1)), float(m.group(2)))

    m = re.search(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)", s)
    if m and _valid_latlon(m.group(1), m.group(2)):
        return (float(m.group(1)), float(m.group(2)))

    m = re.search(r"center=(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)", s)
    if m and _valid_latlon(m.group(1), m.group(2)):
        return (float(m.group(1)), float(m.group(2)))

    m = re.search(r"[?&]ll=(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)", s)
    if m and _valid_latlon(m.group(1), m.group(2)):
        return (float(m.group(1)), float(m.group(2)))

    return (None, None)

def parse_coords_from_page(page):
    lat, lon = _extract_latlon_from_text(page.url)
    if _valid_latlon(lat, lon):
        return lat, lon
    try:
        og = page.locator('meta[property="og:image"]').first
        if og.count() > 0:
            content = og.get_attribute("content") or ""
            lat, lon = _extract_latlon_from_text(content)
            if _valid_latlon(lat, lon):
                return lat, lon
    except Exception:
        pass
    try:
        hrefs = page.eval_on_selector_all('a[href*="/maps/"]', "els => els.map(e => e.href)")
        for h in hrefs:
            lat, lon = _extract_latlon_from_text(h)
            if _valid_latlon(lat, lon):
                return lat, lon
    except Exception:
        pass
    return (None, None)

def click_if_exists(page, selector: str, timeout_ms: int = 1500):
    try:
        el = page.locator(selector).first
        if el.count() > 0:
            el.click(timeout=timeout_ms)
            return True
    except Exception:
        pass
    return False

def accept_cookies_if_prompted(page):
    if click_if_exists(page, '#L2AGLb', 2000):
        return
    for txt in COOKIE_ACCEPT_TEXTS:
        if click_if_exists(page, f'button:has-text("{txt}")', 2000):
            return
    click_if_exists(page, 'button[aria-label*="Accept"]', 2000)

def dismiss_signin_or_promos(page):
    for sel in [
        'button:has-text("No thanks")',
        'button:has-text("Not now")',
        'button:has-text("Skip")',
        'button:has-text("لا شكراً")',
        'button:has-text("ليس الآن")',
        'button:has-text("خلال وقت لاحق")',
        'button:has-text("ข้าม")',
        'button:has-text("ภายหลัง")',
    ]:
        click_if_exists(page, sel, 1200)

def wait_for_results_ready(page, timeout=25000):
    try:
        page.wait_for_selector(
            '[role="feed"] [role="article"], div.Nv2PK, a[href*="/maps/place/"]',
            timeout=timeout
        )
    except PlaywrightTimeout:
        pass
    try:
        page.wait_for_selector('[role="progressbar"]', timeout=3000, state="detached")
    except Exception:
        pass
    time.sleep(0.5)

def center_on_city(page, city: str):
    search = page.locator("input#searchboxinput")
    search.click()
    search.fill(city)
    page.keyboard.press("Enter")
    wait_for_results_ready(page, timeout=20000)

def run_boolean_query(page, city: str, boolean_query: str):
    full_query = f'({boolean_query}) in {city}'
    search = page.locator("input#searchboxinput")
    search.click()
    search.press("Control+A")
    search.fill(full_query)
    page.keyboard.press("Enter")
    wait_for_results_ready(page, timeout=25000)
    for txt in SEARCH_THIS_AREA_TEXTS:
        if click_if_exists(page, f'button:has-text("{txt}")', 1500):
            wait_for_results_ready(page, timeout=15000)
            break

def fallback_direct_search(page, city: str, boolean_query: str):
    url = f"https://www.google.com/maps/search/{quote_plus('(' + boolean_query + ')' + ' in ' + city)}"
    page.goto(url, timeout=60000)
    wait_for_results_ready(page, timeout=25000)

def get_results_scrollbox(page):
    for sel in [
        'div.m6QErb[aria-label]',  # common scrollbox
        'div[role="feed"]',
        'div.m6QErb',
    ]:
        el = page.locator(sel).first
        if el.count() > 0:
            return el
    return None

def collect_current_place_urls(page):
    urls = set()
    try:
        hrefs = page.eval_on_selector_all(
            '[role="feed"] [role="article"] a[href*="/maps/place/"]',
            "els => els.map(e => e.href)"
        )
        for h in hrefs:
            urls.add(h.split("&")[0])
    except Exception:
        pass
    try:
        hrefs = page.eval_on_selector_all(
            'div.Nv2PK a[href*="/maps/place/"]',
            "els => els.map(e => e.href)"
        )
        for h in hrefs:
            urls.add(h.split("&")[0])
    except Exception:
        pass
    if not urls:
        try:
            hrefs = page.eval_on_selector_all(
                'a[href*="/maps/place/"]',
                "els => els.map(e => e.href)"
            )
            for h in hrefs:
                urls.add(h.split("&")[0])
        except Exception:
            pass
    return urls

def click_next_page_if_present(page):
    for sel in [
        'button[aria-label*="Next"]',
        'button:has-text("Next")',
        'button:has-text("التالي")',
        'button:has-text("التالي ›")',
        'button:has-text("التالي›")',
        'button:has-text("ถัดไป")',
    ]:
        if click_if_exists(page, sel, 1200):
            wait_for_results_ready(page, timeout=15000)
            return True
    return False

def scroll_and_collect_place_urls(page, cap: int = MAX_PER_CITY):
    urls = set()
    idle_rounds = 0
    last_count = 0

    scrollbox = get_results_scrollbox(page)
    if scrollbox is None:
        return list(collect_current_place_urls(page))[:cap]

    for _ in range(200):  # upper bound
        urls |= collect_current_place_urls(page)

        if len(urls) >= cap:
            break

        if len(urls) == last_count:
            idle_rounds += 1
        else:
            idle_rounds = 0
            last_count = len(urls)

        if idle_rounds > 1:
            for txt in SEARCH_THIS_AREA_TEXTS:
                if click_if_exists(page, f'button:has-text("{txt}")', 1200):
                    wait_for_results_ready(page, timeout=10000)
                    idle_rounds = 0
                    break

        if idle_rounds >= MAX_IDLE_ROUNDS:
            if click_next_page_if_present(page):
                idle_rounds = 0
                continue
            else:
                break

        try:
            scrollbox.evaluate("el => el.scrollBy(0, el.scrollHeight)")
        except Exception:
            page.mouse.wheel(0, 1800)

        time.sleep(1.1)

    return list(urls)[:cap]

def safe_text(locator, default=""):
    try:
        if locator.count() > 0:
            txt = locator.first.inner_text().strip()
            if txt:
                return txt
    except Exception:
        pass
    return default

# -------- Rating/Reviews (locale-agnostic with K/M/ألف/مليون) --------
REVIEW_WORDS = (
    "review", "reviews",                # English
    "مراجعة", "مراجعات", "التعليقات", "تقييمات",  # Arabic
)
STAR_WORDS = (
    "star", "stars",    # English
    "نجوم", "نجمة",     # Arabic
)

# Map unit words to multipliers (for compact counts)
COUNT_UNITS = {
    "k": 1_000, "K": 1_000,
    "m": 1_000_000, "M": 1_000_000,
    # Arabic
    "ألف": 1_000, "الف": 1_000, "آلاف": 1_000,
    "مليون": 1_000_000, "مليُون": 1_000_000,
}

def _to_ascii_digits(s: str) -> str:
    """Convert any Unicode digits (e.g., Arabic-Indic) to ASCII 0-9."""
    out_chars = []
    for ch in s or "":
        try:
            if unicodedata.category(ch) == "Nd":
                out_chars.append(str(unicodedata.digit(ch)))
            else:
                out_chars.append(ch)
        except Exception:
            out_chars.append(ch)
    return "".join(out_chars)

def _parse_compact_count(num: str, unit: str) -> int | None:
    """Parse '1.2 K' / '1,2K' / '١٫٢ ألف' → int."""
    if not num or not unit:
        return None
    unit = unit.strip()
    if unit not in COUNT_UNITS:
        return None
    # normalize decimal separators
    num = _to_ascii_digits(num).replace(",", ".")
    try:
        val = float(num) * COUNT_UNITS[unit]
        return int(round(val))
    except Exception:
        return None

def _parse_plain_int(num: str) -> int | None:
    """Parse '1,234' / '1.234' / '1 234' / '١٬٢٣٤' → int."""
    if not num:
        return None
    num_ascii = _to_ascii_digits(num)
    # drop spaces and common group separators
    cleaned = re.sub(r"[^\d]", "", num_ascii)
    return int(cleaned) if cleaned else None

def _parse_rating_from_string(s: str):
    if not s:
        return None
    s_norm = _to_ascii_digits(s)
    # Accept 4.5 / 4,5 / "4.5 stars"/"4,5 نجوم"
    m = re.search(r"([0-5](?:[.,]\d)?)\s*(?:/|[\s])?\s*5?(?:\s*(?:stars?|نجوم|نجمة))?", s_norm, re.IGNORECASE)
    if m:
        val = m.group(1).replace(",", ".")
        try:
            return f"{float(val):.1f}"
        except Exception:
            return None
    if any(w in s_norm.lower() for w in STAR_WORDS):
        m2 = re.search(r"([0-5](?:[.,]\d)?)", s_norm)
        if m2:
            val = m2.group(1).replace(",", ".")
            try:
                return f"{float(val):.1f}"
            except Exception:
                return None
    return None

def _parse_reviews_from_string(s: str):
    """Return review count (int) parsed from various localized formats."""
    if not s:
        return None
    s_norm = _to_ascii_digits(s)

    # 1) "1.2K reviews" / "١٫٢ ألف مراجعات" / "1.2M reviews"
    km = re.search(r"(\d+(?:[.,]\d+)?)\s*(K|k|M|m|ألف|الف|آلاف|مليون|مليُون)", s_norm)
    if km and any(w in s_norm.lower() for w in REVIEW_WORDS):
        c = _parse_compact_count(km.group(1), km.group(2))
        if c is not None:
            return c

    # 2) Explicit number + review word: "1,234 reviews" / "١٬٢٣٤ مراجعات"
    m = re.search(r"([\d\s.,]+)\s*(?:reviews?|مراجعات|مراجعة|التعليقات|تقييمات)", s_norm, re.IGNORECASE)
    if m:
        c = _parse_plain_int(m.group(1))
        if c is not None:
            return c

    # 3) Parentheses format near ratings: "(1,234)"
    pm = re.search(r"\(([\d\s.,]+)\)", s_norm)
    if pm:
        c = _parse_plain_int(pm.group(1))
        if c is not None:
            return c

    # 4) Compact count without review word but with K/M unit somewhere
    km2 = re.search(r"(\d+(?:[.,]\d+)?)\s*(K|k|M|m|ألف|الف|آلاف|مليون|مليُون)", s_norm)
    if km2:
        c = _parse_compact_count(km2.group(1), km2.group(2))
        if c is not None:
            return c

    # 5) Last-resort: a biggish number in the string (avoid picking rating 4.5)
    any_num = re.findall(r"(\d[\d\s.,]{2,})", s_norm)  # numbers with length >=3 incl. separators
    for token in any_num:
        c = _parse_plain_int(token)
        if c and c >= 10:  # heuristic: review counts are usually >=10
            return c

    return None

def extract_rating_reviews(page):
    rating, reviews = None, None

    # 1) Aria-labels in the details area
    selectors = [
        'div[role="main"] [aria-label]',
        'div[role="main"] button[aria-label]',
        'div[role="main"] div[aria-label]',
        'div[role="main"] span[aria-label]',
    ]
    labels = []
    for sel in selectors:
        try:
            labels += page.eval_on_selector_all(sel, "els => els.map(e => e.getAttribute('aria-label'))")
        except Exception:
            pass

    for s in labels:
        if rating is None:
            rating = _parse_rating_from_string(s)
        if reviews is None:
            reviews = _parse_reviews_from_string(s)
        if rating and reviews:
            break

    # 2) Visible texts near the header (short nodes)
    if rating is None or reviews is None:
        try:
            texts = page.eval_on_selector_all(
                'div[role="main"] *',
                "els => els.map(e => (e.innerText || '').trim()).filter(t => t && t.length <= 120)"
            )
        except Exception:
            texts = []
        for s in texts:
            if rating is None and any(w in s for w in STAR_WORDS):
                rating = rating or _parse_rating_from_string(s)
            if reviews is None:
                candidate = _parse_reviews_from_string(s)
                if candidate:
                    reviews = candidate
            if rating and reviews:
                break

    return rating, reviews

# --------------------------------------------------

def extract_details_from_place(page, place_url: str):
    page.goto(place_url, timeout=60000)
    page.wait_for_selector('h1, h1[class*="DUwDvf"]', timeout=20000)
    time.sleep(RATE_LIMIT_SEC)

    details = {
        "name": "",
        "address": "",
        "phone": "",
        "website": "",
        "rating": "",
        "reviews_count": "",
        "lat": "",
        "lon": "",
        "google_maps_url": place_url,
        "facebook": "",
        "instagram": "",
        "twitter_or_x": "",
        "tiktok": "",
        "youtube": "",
        "line": "",
    }

    # Name
    details["name"] = safe_text(page.locator('h1[class*="DUwDvf"]')) or safe_text(page.locator('h1'))

    # Rating + review count (robust)
    r, rc = extract_rating_reviews(page)
    details["rating"] = r or ""
    details["reviews_count"] = rc if rc is not None else ""

    # Address
    addr = safe_text(page.locator('button[data-item-id="address"]')) \
        or safe_text(page.locator('div[data-item-id="address"]'))
    if not addr:
        try:
            al = page.locator('button[aria-label^="Address:"]').first.get_attribute("aria-label")
            if al:
                addr = al.replace("Address:", "").strip()
        except Exception:
            pass
    details["address"] = addr

    # Phone
    phone = ""
    try:
        phone_btn = page.locator('button[data-item-id^="phone:"]').first
        if phone_btn.count() > 0:
            al = phone_btn.get_attribute("aria-label") or ""
            m = re.search(r"Phone:\s*(.+)$", al)
            phone = m.group(1).strip() if m else safe_text(phone_btn)
    except Exception:
        pass
    if not phone:
        try:
            tel = page.locator('a[href^="tel:"]').first
            if tel.count() > 0:
                phone = (tel.get_attribute("href") or "").replace("tel:", "")
        except Exception:
            pass
    details["phone"] = phone

    # Website
    website = ""
    try:
        site_link = page.locator('a[data-item-id="authority"]').first
        if site_link.count() > 0:
            website = site_link.get_attribute("href") or ""
    except Exception:
        pass
    if not website:
        try:
            site_link = page.locator('a[aria-label^="Website:"]').first
            if site_link.count() > 0:
                website = site_link.get_attribute("href") or ""
        except Exception:
            pass
    details["website"] = website

    # Coords (robust)
    lat, lon = parse_coords_from_page(page)
    details["lat"] = lat if lat is not None else ""
    details["lon"] = lon if lon is not None else ""

    # Socials
    social_map = {
        "facebook": ("facebook.com", "fb.com"),
        "instagram": ("instagram.com",),
        "twitter_or_x": ("twitter.com", "x.com"),
        "tiktok": ("tiktok.com",),
        "youtube": ("youtube.com", "youtu.be"),
        "line": ("line.me",),
    }
    try:
        anchors = page.locator('div[role="main"] a[href^="http"]').all()
    except Exception:
        anchors = []
    for a in anchors:
        try:
            href = a.get_attribute("href") or ""
        except Exception:
            href = ""
        if not href:
            continue
        host = urlsplit(href).netloc.lower()
        for key, host_hints in social_map.items():
            if details[key]:
                continue
            if any(h in host for h in host_hints):
                details[key] = href

    return details

def write_csv_header(path: Path):
    if path.exists():
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "city","name","address","phone","website","rating","reviews_count",
            "lat","lon","google_maps_url","facebook","instagram","twitter_or_x",
            "tiktok","youtube","line"
        ])

def append_rows(path: Path, rows):
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow([
                r.get("city",""), r.get("name",""), r.get("address",""), r.get("phone",""),
                r.get("website",""), r.get("rating",""), r.get("reviews_count",""),
                r.get("lat",""), r.get("lon",""), r.get("google_maps_url",""),
                r.get("facebook",""), r.get("instagram",""), r.get("twitter_or_x",""),
                r.get("tiktok",""), r.get("youtube",""), r.get("line",""),
            ])

# =======================
# Main
# =======================
def main():
    out_path = Path(OUTPUT_CSV)
    write_csv_header(out_path)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
        )
        context = browser.new_context(
            locale="en-US",
            viewport={"width": 1500, "height": 950},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
        )
        page = context.new_page()

        for city in CITIES:
            print(f"\n=== Processing city: {city} ===")
            page.goto("https://www.google.com/maps", timeout=60000)
            accept_cookies_if_prompted(page)
            dismiss_signin_or_promos(page)
            center_on_city(page, city)

            # ONE boolean query per city
            run_boolean_query(page, city, EXACT_BOOLEAN_QUERY)

            # Fallback via direct URL if UI didn’t render results
            if page.locator('[role="feed"], div.Nv2PK, a[href*="/maps/place/"]').count() == 0:
                fallback_direct_search(page, city, EXACT_BOOLEAN_QUERY)

            print("Scrolling results and collecting place URLs…", flush=True)
            urls = scroll_and_collect_place_urls(page, cap=MAX_PER_CITY)
            print(f"Found {len(urls)} place URLs for {city}", flush=True)

            # Live terminal table
            printed_for_city = 0
            print_table_header(city)

            city_rows = []
            seen_keys = set()

            for idx, u in enumerate(urls, 1):
                try:
                    d = extract_details_from_place(page, u)
                    d["city"] = city
                    key = (d.get("name","").lower().strip(), d.get("lat",""), d.get("lon",""))
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    city_rows.append(d)

                    if len(city_rows) % 10 == 0:
                        append_rows(out_path, city_rows)
                        city_rows = []

                    if printed_for_city < TERMINAL_PREVIEW_MAX:
                        print_table_row(d)
                        printed_for_city += 1
                    else:
                        print(f"[{idx}/{len(urls)}] {d.get('name','(no name)')} ({d.get('lat','')},{d.get('lon','')})", flush=True)

                    time.sleep(RATE_LIMIT_SEC)
                except Exception as e:
                    print(f"  -> Skipped due to error: {e}", flush=True)
                    time.sleep(0.4)
                    continue

            if city_rows:
                append_rows(out_path, city_rows)

            if SHOW_TERMINAL_PREVIEW and printed_for_city >= TERMINAL_PREVIEW_MAX and len(urls) > TERMINAL_PREVIEW_MAX:
                print(f"...and {len(urls) - TERMINAL_PREVIEW_MAX} more saved to CSV for {city}.", flush=True)

        browser.close()

if __name__ == "__main__":
    main()
