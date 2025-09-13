# Google Maps Café Scraper (Playwright, Python)

Scrapes Businesses (for exmaple, cafes) from **Google Maps** for a list of a given cities using a **single boolean query**.  

Outputs a CSV with: city, name, address, phone, website, rating, number of reviews, latitude, longitude, Google Maps URL, and social links.

> ⚠️ **Use responsibly.** Automated scraping may violate a site's Terms of Service. This project is for educational/research purposes.

---

## Features

- ✅ **One boolean search per city** (with your multilingual keywords)
- ✅ Robust **lat/lon** extraction (handles multiple URL/metadata patterns)
- ✅ Locale-agnostic **rating** and **review count** parsing  
  (supports English + Other languages, handles `1.2K`, `(1,234)`, `ألف`/`مليون` numerals etc)
- ✅ Live **terminal preview** (first N rows) + heartbeat progress
- ✅ Per-city **health summary** (how many rows had rating/reviews/website/phone/coords)
- ✅ **CSV** output that appends safely as it goes

---

## Requirements

- **Python** 3.9+ (3.10+ recommended)
- **Playwright** for Python
- **Chromium** installed via Playwright

---

## Choosing Cities and Keywords
Please check the `cities_and_keywords.py` file to list the cities and keywords of choice.

---

## Handling Congifurations
Consider `config.py` file to modify configuration params such as the name of output file, maximum number of locations per city, etc.

---

## Setup

```bash
# 1) Create and activate a virtual environment
python -m venv .venv
# Windows PowerShell
. .\.venv\Scripts\Activate.ps1
# macOS/Linux
# source .venv/bin/activate

# 2) Install dependencies
pip install -r requirements.txt

# 3) Install the browser runtime for Playwright
playwright install chromium

# 4) Run
python scraper.py
```


---

## How It Works (high level)

1. Open Google Maps → type the city to center the map.

2. Run a single boolean query (your keywords) scoped to that city.

3. Scroll the sidebar to gather place result URLs (with a fallback “Search this area” click).

4. Visit each place page and extract: Name, Address, Phone, Website, Rating and Reviews (locale-aware), Lat/Lon (from URL patterns / meta image / links), and Social links (Facebook/Instagram/X/TikTok/YouTube/LINE).

5. Stream a live table to the terminal, write batches to CSV, and print a health summary.


---

Troubleshooting

- No results / stuck on consent: the script tries to accept cookies and dismiss prompts.
If needed, set HEADLESS = False to observe and adjust timeouts/selectors.

- Few results despite many places:

  -  Increase MAX_PER_CITY.

  -  Let it click “Search this area” (included).

  -  Ensure your network isn’t blocking requests.

- Encoding issues on Windows: use the UTF-8 commands above.

- Duplicate rows across runs: delete google_maps_cafes.csv before re-running, or add your own cross-run dedupe.

---

## Legal & Ethics

- Review the Google Maps Terms of Service before scraping.

- Respect robots, rate limits, and applicable laws in your jurisdiction.

---

## License

MIT