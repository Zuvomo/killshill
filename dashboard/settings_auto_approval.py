"""
Auto-Approval System Configuration
Add these settings to your Django settings.py file
"""

# Auto-Approval Configuration
ENABLE_AUTO_APPROVAL = True

# Minimum thresholds for auto-approval
AUTO_APPROVAL_MIN_CONFIDENCE = 70  # Minimum confidence score (0-100)
AUTO_APPROVAL_MIN_FOLLOWERS = 1000  # Minimum follower count
AUTO_APPROVAL_MAX_VARIANCE = 0.3  # Maximum variance between submitted and actual followers (30%)

# Platform API Keys (optional but recommended for better verification)
# Twitter API v2
TWITTER_BEARER_TOKEN = ''  # Your Twitter Bearer Token
TWITTER_API_KEY = ''  # Your Twitter API Key
TWITTER_API_SECRET = ''  # Your Twitter API Secret

# YouTube Data API
YOUTUBE_API_KEY = ''  # Your YouTube Data API Key

# Telegram Bot API
TELEGRAM_BOT_TOKEN = ''  # Your Telegram Bot Token (optional)

# Instagram Basic Display API
INSTAGRAM_ACCESS_TOKEN = ''  # Instagram Access Token (optional)

# TikTok API
TIKTOK_ACCESS_TOKEN = ''  # TikTok API Access Token (optional)

# Notification Settings
SEND_BATCH_NOTIFICATIONS = True  # Send batch processing notifications to admins
DEFAULT_FROM_EMAIL = 'noreply@killshill.com'  # Email sender

# Celery Configuration for Background Processing
# Add these to your Celery configuration
CELERY_BEAT_SCHEDULE = {
    'process-auto-approvals': {
        'task': 'dashboard.tasks.schedule_auto_approval_batch',
        'schedule': 3600.0,  # Every hour
    },
    'cleanup-old-rejections': {
        'task': 'dashboard.tasks.cleanup_old_rejections',
        'schedule': 604800.0,  # Weekly
    },
}

# Cache Configuration (recommended for verification caching)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'killshill_auto_approval',
        'TIMEOUT': 3600,  # 1 hour cache timeout
    }
}

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'auto_approval_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/auto_approval.log',
            'maxBytes': 15728640,  # 15MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'dashboard.services': {
            'handlers': ['auto_approval_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'dashboard.tasks': {
            'handlers': ['auto_approval_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Rate Limiting (to prevent API abuse)
AUTO_APPROVAL_RATE_LIMIT = {
    'requests_per_minute': 60,  # Max API requests per minute
    'requests_per_hour': 1000,  # Max API requests per hour
    'concurrent_processing': 5,  # Max concurrent processing
}

# Security Settings
AUTO_APPROVAL_SECURITY = {
    'max_submissions_per_user_per_day': 10,  # Prevent spam
    'require_email_verification': True,  # Require verified email
    'blacklisted_domains': [  # Blocked domains
        'example-spam-domain.com',
        'suspicious-site.net',
    ],
    'min_account_age_days': 1,  # Minimum user account age
}

# Verification Weights (for score calculation)
VERIFICATION_WEIGHTS = {
    'verification_confidence': 0.4,
    'follower_accuracy': 0.25,
    'account_age': 0.15,
    'platform_verification': 0.1,
    'engagement_quality': 0.1
}

# Platform-specific configurations
PLATFORM_CONFIGS = {
    'Twitter': {
        'min_confidence': 60,
        'min_followers': 500,
        'max_variance': 0.3,
        'require_verification': False,
    },
    'YouTube': {
        'min_confidence': 65,
        'min_followers': 1000,
        'max_variance': 0.25,
        'require_verification': False,
    },
    'Telegram': {
        'min_confidence': 50,
        'min_followers': 100,
        'max_variance': 0.4,
        'require_verification': False,
    },
    'TikTok': {
        'min_confidence': 60,
        'min_followers': 10000,
        'max_variance': 0.3,
        'require_verification': False,
    },
    'Instagram': {
        'min_confidence': 65,
        'min_followers': 1000,
        'max_variance': 0.3,
        'require_verification': False,
    },
    'Discord': {
        'min_confidence': 40,  # Limited verification available
        'min_followers': 100,
        'max_variance': 0.5,
        'require_verification': False,
    },
}