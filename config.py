import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id]
OWNER_ID = int(os.getenv('OWNER_ID', '0'))

# Database Configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///reports.db')

# Report Configuration
REPORT_INTERVAL = 10  # seconds
MAX_REPORTS_PER_ACCOUNT = 50  # max reports before cooldown
COOLDOWN_TIME = 3600  # 1 hour cooldown