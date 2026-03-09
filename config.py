import os
import logging
from dotenv import load_dotenv

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# ============================================
# BOT CONFIGURATION
# ============================================

# Bot Token (Required)
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN not set in environment variables!")
    raise ValueError("BOT_TOKEN is required")

# Admin IDs (Optional)
try:
    ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]
    logger.info(f"✅ Admin IDs configured: {ADMIN_IDS}")
except ValueError as e:
    logger.error(f"❌ Invalid ADMIN_IDS format: {e}")
    ADMIN_IDS = []

# Owner ID (Required for owner commands)
try:
    OWNER_ID = int(os.getenv('OWNER_ID', '0'))
    if OWNER_ID == 0:
        logger.warning("⚠️ OWNER_ID not set. Owner commands will be disabled.")
    else:
        logger.info(f"✅ Owner ID configured: {OWNER_ID}")
except ValueError:
    logger.error("❌ Invalid OWNER_ID format")
    OWNER_ID = 0

# ============================================
# DATABASE CONFIGURATION
# ============================================

# Database URL
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///reports.db')

# Fix PostgreSQL URL if needed
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    logger.info("✅ Converted postgres:// to postgresql://")

# Remove any spaces that might have been accidentally added
if ' ' in DATABASE_URL:
    logger.warning("⚠️ DATABASE_URL contains spaces! Removing...")
    DATABASE_URL = DATABASE_URL.replace(' ', '')

logger.info(f"📁 Database: {'PostgreSQL' if 'postgresql' in DATABASE_URL else 'SQLite'}")

# ============================================
# REPORT CONFIGURATION
# ============================================

# Report interval in seconds
try:
    REPORT_INTERVAL = int(os.getenv('REPORT_INTERVAL', '10'))
    if REPORT_INTERVAL < 5:
        logger.warning("⚠️ REPORT_INTERVAL is very low. Minimum recommended is 5 seconds.")
    logger.info(f"⏱️ Report interval: {REPORT_INTERVAL} seconds")
except ValueError:
    REPORT_INTERVAL = 10
    logger.warning("⚠️ Invalid REPORT_INTERVAL, using default: 10 seconds")

# Max reports per account before cooldown
try:
    MAX_REPORTS_PER_ACCOUNT = int(os.getenv('MAX_REPORTS_PER_ACCOUNT', '50'))
    logger.info(f"📊 Max reports per account: {MAX_REPORTS_PER_ACCOUNT}")
except ValueError:
    MAX_REPORTS_PER_ACCOUNT = 50
    logger.warning("⚠️ Invalid MAX_REPORTS_PER_ACCOUNT, using default: 50")

# Cooldown time in seconds (1 hour default)
try:
    COOLDOWN_TIME = int(os.getenv('COOLDOWN_TIME', '3600'))
    logger.info(f"⏰ Cooldown time: {COOLDOWN_TIME} seconds ({COOLDOWN_TIME/3600:.1f} hours)")
except ValueError:
    COOLDOWN_TIME = 3600
    logger.warning("⚠️ Invalid COOLDOWN_TIME, using default: 3600 seconds (1 hour)")

# ============================================
# ADDITIONAL CONFIGURATION
# ============================================

# API credentials for Telethon (if not in main.py)
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')

if not API_ID or not API_HASH:
    logger.warning("⚠️ API_ID or API_HASH not set in config.py. Make sure they're in main.py!")

# Maximum number of accounts per user
try:
    MAX_ACCOUNTS_PER_USER = int(os.getenv('MAX_ACCOUNTS_PER_USER', '10'))
except ValueError:
    MAX_ACCOUNTS_PER_USER = 10

# Maximum number of targets per user
try:
    MAX_TARGETS_PER_USER = int(os.getenv('MAX_TARGETS_PER_USER', '20'))
except ValueError:
    MAX_TARGETS_PER_USER = 20

# Default coins for new users
try:
    DEFAULT_COINS = int(os.getenv('DEFAULT_COINS', '10'))
except ValueError:
    DEFAULT_COINS = 10

# ============================================
# VALIDATION FUNCTION
# ============================================

def validate_config():
    """Validate all configuration settings"""
    errors = []
    warnings = []
    
    # Check required settings
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN is required")
    
    if not API_ID or not API_HASH:
        errors.append("API_ID and API_HASH are required in main.py")
    
    # Check database connection string
    if 'postgresql' in DATABASE_URL:
        if '@' not in DATABASE_URL:
            errors.append("Invalid PostgreSQL connection string")
    
    # Check intervals
    if REPORT_INTERVAL < 1:
        errors.append("REPORT_INTERVAL must be at least 1 second")
    
    if COOLDOWN_TIME < 60:
        warnings.append("COOLDOWN_TIME is less than 60 seconds. This might get accounts banned.")
    
    # Check IDs
    if OWNER_ID == 0:
        warnings.append("OWNER_ID not set. Owner commands will be disabled.")
    
    # Return validation result
    if errors:
        for error in errors:
            logger.error(f"❌ Config error: {error}")
        return False, errors
    
    for warning in warnings:
        logger.warning(f"⚠️ Config warning: {warning}")
    
    return True, warnings

# ============================================
# EXPORT CONFIGURATION
# ============================================

__all__ = [
    'BOT_TOKEN',
    'ADMIN_IDS',
    'OWNER_ID',
    'DATABASE_URL',
    'REPORT_INTERVAL',
    'MAX_REPORTS_PER_ACCOUNT',
    'COOLDOWN_TIME',
    'API_ID',
    'API_HASH',
    'MAX_ACCOUNTS_PER_USER',
    'MAX_TARGETS_PER_USER',
    'DEFAULT_COINS',
    'validate_config'
]

# Auto-validate on import
if __name__ != '__main__':
    is_valid, messages = validate_config()
    if not is_valid:
        logger.error("❌ Configuration validation failed!")