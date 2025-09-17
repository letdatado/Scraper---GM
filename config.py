OUTPUT_CSV = "OUTPUT.csv"
HEADLESS = True                 # Set False to watch it run
RATE_LIMIT_SEC = 0.8
MAX_PER_CITY = 400              # Safety cap per city
MAX_IDLE_ROUNDS = 6             # Stop scrolling if nothing new after these rounds
DEBUG_SHOTS = False             # Save debug screenshots

# =======================
# Live terminal preview
# =======================
SHOW_TERMINAL_PREVIEW = True
TERMINAL_PREVIEW_MAX = 40
TERMINAL_COLUMNS = ["name", "rating", "phone", "website", "lat", "lon"]
COL_WIDTHS = {"name": 38, "rating": 6, "phone": 18, "website": 30, "lat": 10, "lon": 11}
DEFAULT_ZOOM = 12  # city-level