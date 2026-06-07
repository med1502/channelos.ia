"""
ChannelOS — Niche profiles configuration
Each niche defines audience, angles, affiliates, languages, and Azure TTS voices.
"""

NICHES = {
    "ai_entrepreneurs": {
        "name": "AI Tools for Entrepreneurs",
        "audience": "Solo founders, SMB owners, side hustlers looking to grow with AI",
        "angles": ["time savings", "cost reduction", "revenue growth", "competitive edge"],
        "affiliates": ["Notion AI", "HubSpot", "Buffer", "Mailchimp", "Make.com"],
        "languages": ["EN", "FR"],
        "voices": {
            "EN": "en-US-AndrewMultilingualNeural",
            "FR": "fr-FR-HenriNeural",
        },
        "hashtags_en": ["#AITools", "#Entrepreneur", "#SmallBusiness", "#Productivity"],
        "hashtags_fr": ["#OutilsIA", "#Entrepreneur", "#PME", "#Productivité"],
    },
    "ai_ecommerce": {
        "name": "AI for E-commerce",
        "audience": "Shopify/WooCommerce store owners, dropshippers, online retailers",
        "angles": ["increase conversions", "automate store", "reduce ad spend", "boost AOV"],
        "affiliates": ["Shopify", "Klaviyo", "Gorgias", "Intelligems", "Tidio"],
        "languages": ["EN"],
        "voices": {"EN": "en-US-AvaMultilingualNeural"},
        "hashtags_en": ["#Ecommerce", "#Shopify", "#AITools", "#OnlineStore", "#DropShipping"],
        "hashtags_fr": [],
    },
    "ai_freelancers": {
        "name": "AI for Freelancers & Creators",
        "audience": "Freelancers, content creators, digital nomads, agency owners",
        "angles": ["replace manual work", "10x output", "land better clients", "charge more"],
        "affiliates": ["Jasper", "Descript", "Canva Pro", "Notion AI", "Zapier"],
        "languages": ["EN", "FR"],
        "voices": {
            "EN": "en-US-BrianMultilingualNeural",
            "FR": "fr-FR-DeniseNeural",
        },
        "hashtags_en": ["#Freelance", "#AITools", "#ContentCreator", "#SideHustle"],
        "hashtags_fr": ["#Freelance", "#OutilsIA", "#Créateur", "#TravailIndépendant"],
    },
    "ai_startups": {
        "name": "AI for Startups & Investors",
        "audience": "Early-stage founders, angel investors, VC-backed teams",
        "angles": ["funding signals", "AI advantage", "build faster", "reduce burn"],
        "affiliates": ["Linear", "Notion AI", "Clay", "Runway", "OpenAI API"],
        "languages": ["EN"],
        "voices": {"EN": "en-US-AndrewMultilingualNeural"},
        "hashtags_en": ["#Startup", "#VentureCapital", "#AIFounder", "#TechStartup"],
        "hashtags_fr": [],
    },
    "ai_finance": {
        "name": "AI & Personal Finance",
        "audience": "Young professionals, investors, people optimizing their money with AI",
        "angles": ["save money", "invest smarter", "automate finances", "beat inflation"],
        "affiliates": ["Trade Republic", "Revolut", "Notion AI", "YNAB"],
        "languages": ["EN", "FR"],
        "voices": {
            "EN": "en-US-AvaMultilingualNeural",
            "FR": "fr-FR-DeniseNeural",
        },
        "hashtags_en": ["#PersonalFinance", "#AIInvesting", "#MoneyTips", "#FinancialFreedom"],
        "hashtags_fr": ["#FinancePersonnelle", "#Investissement", "#OutilsIA", "#Argent"],
    },
}

DEFAULT_NICHE = "ai_entrepreneurs"


def get_niche(key: str) -> dict:
    return NICHES.get(key, NICHES[DEFAULT_NICHE])


def list_niches() -> list[tuple[str, str]]:
    return [(k, v["name"]) for k, v in NICHES.items()]
