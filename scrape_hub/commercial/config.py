"""Commercial feature configuration.

Replace placeholder values with your own before deploying.
"""

# ── User Tiers ──────────────────────────────────────────────

TIERS = {
    "free": {
        "name": "免费版",
        "badge": "🆓",
        "searches_per_day": 3,
        "downloads_per_day": 0,
        "preview_limit": 5,        # max items shown per query result
        "price_monthly": 0,
    },
    "basic": {
        "name": "基础版",
        "badge": "⭐",
        "searches_per_day": 30,
        "downloads_per_day": 10,
        "preview_limit": -1,       # -1 = unlimited
        "price_monthly": 29.9,
    },
    "pro": {
        "name": "专业版",
        "badge": "💎",
        "searches_per_day": -1,    # -1 = unlimited
        "downloads_per_day": -1,
        "preview_limit": -1,
        "price_monthly": 99.9,
    },
}

# ── Ads ─────────────────────────────────────────────────────

ADS_ENABLED = True

# Replace with your Google AdSense publisher ID
ADSENSE_CLIENT_ID = "ca-pub-XXXXXXXXXXXXXXXX"

# Replace with your ad unit slot IDs
AD_SLOTS = {
    "header": "XXXXXXXXXX",
    "sidebar": "XXXXXXXXXX",
    "in_content": "XXXXXXXXXX",
}

# ── Payment ─────────────────────────────────────────────────

# Stripe payment links (replace with your own)
PAYMENT_LINKS = {
    "basic_monthly": "https://buy.stripe.com/your_basic_link",
    "pro_monthly": "https://buy.stripe.com/your_pro_link",
}

SUPPORT_EMAIL = "support@scrapehub.com"
