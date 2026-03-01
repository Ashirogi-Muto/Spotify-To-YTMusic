import os
from pathlib import Path
from dotenv import load_dotenv

# Paths
BASE_DIR = Path(__file__).parent.parent.resolve()

# Load .env file for credentials persistence
load_dotenv(BASE_DIR / ".env")

DB_PATH = BASE_DIR / "migration.db"
YTMUSIC_AUTH_FILE = BASE_DIR / "headers_auth.json"

# Credentials
SPOTIPY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.environ.get("SPOTIPY_REDIRECT_URI", "http://localhost:8080/callback")

# Tool Metadata
TOOL_VERSION = "1.0.0"

# Rate Limiter Settings (YT Music Only)
YTM_MAX_RETRIES = 3
YTM_RATE_LIMIT_DELAY = 0.5  # 2 requests per sec = 1 request every 0.5s
YTM_JITTER_MAX = 0.3        # Max 300ms jitter

# Matching Thresholds
MATCH_SEMANTIC = 0.85
MATCH_LOW_CONFIDENCE = 0.75

# Extraction Settings
BATCH_SIZE = 50
