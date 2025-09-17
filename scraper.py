import re
import csv
import time
from pathlib import Path
from urllib.parse import quote_plus, urlsplit, unquote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Region-config & region-aware helpers
from params import (
    CITIES, KEYWORDS,
    SEARCH_THIS_AREA_TEXTS, COOKIE_ACCEPT_TEXTS,
    CITY_CENTER_LOOKUP,
    dismiss_signin_or_promos, click_next_page_if_present,
    _parse_rating_from_string, _parse_reviews_from_string,
    STAR_WORDS,
)


from config import (OUTPUT_CSV, HEADLESS, RATE_LIMIT_SEC, MAX_PER_CITY, 
                    MAX_IDLE_ROUNDS, DEBUG_SHOTS, SHOW_TERMINAL_PREVIEW, 
                    TERMINAL_PREVIEW_MAX, TERMINAL_COLUMNS, COL_WIDTHS, 
                    DEFAULT_ZOOM)


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
        lat = float(lat)
        lon = float(lon)
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


# --- region-aware prompt dismissal imported from params.py ---


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


def normalize_city_key(city):
    return (city or "").strip().lower()


def city_center_from_table(city):
    return CITY_CENTER_LOOKUP.get(normalize_city_key(city))


def goto_center(page, lat, lon, zoom=DEFAULT_ZOOM):
    page.goto(f"https://www.google.com/maps/@{lat},{lon},{zoom}z?hl=en", timeout=60000)
    wait_for_results_ready(page, timeout=20000)
    time.sleep(0.4)


def center_on_city(page, city):
    """
    Prefer static city centers (prevents location bias).
    Fallback to place page → parse coords, then recentre.
    """
    coords = city_center_from_table(city)
    if coords:
        goto_center(page, coords[0], coords[1], DEFAULT_ZOOM)
        return coords

    page.goto(f"https://www.google.com/maps/place/{quote_plus(city)}?hl=en", timeout=60000)
    wait_for_results_ready(page, timeout=20000)
    time.sleep(0.6)
    lat, lon = parse_coords_from_page(page)
    if _valid_latlon(lat, lon):
        goto_center(page, lat, lon, DEFAULT_ZOOM)
        return (lat, lon)
    return (None, None)


def run_boolean_query(page, city, boolean_query, lat=None, lon=None):
    """
    Open a search URL anchored at @lat,lon to avoid re-bias to user's real location.
    """
    query = f"({boolean_query})"
    if _valid_latlon(lat, lon):
        page.goto(
            f"https://www.google.com/maps/search/{quote_plus(query)}/@{lat},{lon},{DEFAULT_ZOOM}z?hl=en",
            timeout=60000
        )
    else:
        page.goto(
            f"https://www.google.com/maps/search/{quote_plus(query + ' near ' + city)}?hl=en",
            timeout=60000
        )
    wait_for_results_ready(page, timeout=25000)

    for txt in SEARCH_THIS_AREA_TEXTS:
        if click_if_exists(page, f'button:has-text("{txt}")', 1500):
            wait_for_results_ready(page, timeout=15000)
            break


def fallback_direct_search(page, city, boolean_query, lat=None, lon=None):
    if _valid_latlon(lat, lon):
        url = f"https://www.google.com/maps/search/{quote_plus('(' + boolean_query + ')')}/@{lat},{lon},{DEFAULT_ZOOM}z?hl=en"
    else:
        url = f"https://www.google.com/maps/search/{quote_plus('(' + boolean_query + ') near ' + city)}?hl=en"
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


# --- region-aware pagination 'Next' imported from params.py ---

def scroll_and_collect_place_urls(page, cap=MAX_PER_CITY):
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


def extract_rating_reviews(page):
    """
    Locale-aware rating & review extraction using region parsers from params.py
    """
    rating, reviews = None, None

    # 1) aria-labels in the details area
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

    # 2) visible texts near the header
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
def extract_details_from_place(page, place_url):
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

    details["name"] = safe_text(page.locator('h1[class*="DUwDvf"]')) or safe_text(page.locator('h1'))

    r, rc = extract_rating_reviews(page)
    details["rating"] = r or ""
    details["reviews_count"] = rc if rc is not None else ""

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

    lat, lon = parse_coords_from_page(page)
    details["lat"] = lat if lat is not None else ""
    details["lon"] = lon if lon is not None else ""

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
            "city", "name", "address", "phone", "website", "rating", "reviews_count",
            "lat", "lon", "google_maps_url", "facebook", "instagram", "twitter_or_x",
            "tiktok", "youtube", "line"
        ])


def append_rows(path: Path, rows):
    if not rows:
        return
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow([
                r.get("city", ""), r.get("name", ""), r.get("address", ""), r.get("phone", ""),
                r.get("website", ""), r.get("rating", ""), r.get("reviews_count", ""),
                r.get("lat", ""), r.get("lon", ""), r.get("google_maps_url", ""),
                r.get("facebook", ""), r.get("instagram", ""), r.get("twitter_or_x", ""),
                r.get("tiktok", ""), r.get("youtube", ""), r.get("line", ""),
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

        # Fresh browser context **per city** with spoofed geolocation (if available)
        for city in CITIES:
            city_latlon = city_center_from_table(city)

            context_kwargs = {
                "locale": "en-US",
                "viewport": {"width": 1500, "height": 950},
                "user_agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/124.0.0.0 Safari/537.36"),
            }
            if city_latlon:
                context_kwargs["geolocation"] = {"latitude": city_latlon[0], "longitude": city_latlon[1]}
                context_kwargs["permissions"] = ["geolocation"]

            context = browser.new_context(**context_kwargs)
            page = context.new_page()

            try:
                print(f"\n=== Processing city: {city} ===")
                page.goto("https://www.google.com/maps?hl=en", timeout=60000)
                accept_cookies_if_prompted(page)
                dismiss_signin_or_promos(page)

                lat, lon = center_on_city(page, city)  # recenters
                if city_latlon and not _valid_latlon(lat, lon):
                    lat, lon = city_latlon

                run_boolean_query(page, city, EXACT_BOOLEAN_QUERY, lat=lat, lon=lon)

                if page.locator('[role="feed"], div.Nv2PK, a[href*="/maps/place/"]').count() == 0:
                    fallback_direct_search(page, city, EXACT_BOOLEAN_QUERY, lat=lat, lon=lon)

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
                        key = (d.get("name", "").lower().strip(), d.get("lat", ""), d.get("lon", ""))
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

            finally:
                context.close()

        browser.close()


if __name__ == "__main__":
    main()
