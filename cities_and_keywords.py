CITIES = [
    "Riyadh, Saudi Arabia",
    "Jeddah, Saudi Arabia",
    "Mecca, Saudi Arabia",
    "Medina, Saudi Arabia",
    "Dammam, Saudi Arabia",
    "Kuwait City, Kuwait",
    "Al Ahmadi, Kuwait",
    "Salmiya, Kuwait",
    "Muscat, Oman",
    "Salalah, Oman",
    "Sohar, Oman",
    "Manama, Bahrain",
    "Riffa, Bahrain",
    "Doha, Qatar",
    "Al Rayyan, Qatar",
    "Dubai, UAE",
    "Abu Dhabi, UAE",
    "Sharjah, UAE",
    "Ajman, UAE",
    "Ras Al Khaimah, UAE",
]

# --- Your keywords (kept verbatim) ---
KEYWORDS = [
    "cafe","café","coffee shop","coffeeshop","coffeehouse","coffee house","espresso bar",
    "tea house","teahouse","tea room","tearoom","bistro","brasserie","snack bar","coffee bar",
    "مقهى","كافيه","كوفي شوب","بيت الشاي","صالون شاي","قهوة","café","bistrot","bistro","café","kafe"
]
EXACT_BOOLEAN_QUERY = " OR ".join(f"\"{t}\"" for t in KEYWORDS)

# UI text variants across locales
SEARCH_THIS_AREA_TEXTS = [
    "Search this area",
    "ابحث في هذه المنطقة",
    "البحث في هذه المنطقة",
    "ค้นหาบริเวณนี้",
]
COOKIE_ACCEPT_TEXTS = [
    "Accept all", "Accept", "I agree", "AGREE",
    "قبول الكل", "أوافق", "موافق",
    "ยอมรับทั้งหมด", "ยอมรับ", "ตกลง",
]
