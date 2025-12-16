SUPPORTED_SEARCH_PLATFORMS = [
    ('Telegram', 'Telegram'),
    ('Twitter', 'X (Twitter)'),
    ('YouTube', 'YouTube'),
    ('TikTok', 'TikTok'),
]

SUPPORTED_SEARCH_CATEGORIES = [
    ('crypto', 'Crypto'),
    ('stocks', 'Stocks'),
    ('forex', 'Forex'),
]

SUPPORTED_PLATFORM_VALUES = {value for value, _ in SUPPORTED_SEARCH_PLATFORMS}
SUPPORTED_CATEGORY_VALUES = {value for value, _ in SUPPORTED_SEARCH_CATEGORIES}
