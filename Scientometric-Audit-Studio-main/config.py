"""
Global configuration and directory definitions for Scholarly Reference Validation System.
"""
from pathlib import Path
import os
import sys

# Base paths
BASE_DIR = Path(__file__).resolve().parent
venv_name = ".venv312" if sys.version_info[:2] == (3, 12) else ".venv"
site_packages = BASE_DIR / venv_name / "Lib" / "site-packages"
if site_packages.exists() and str(site_packages) not in sys.path:
    sys.path.insert(0, str(site_packages))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "input"
INTERMEDIATE_DIR = DATA_DIR / "intermediate"
OUTPUT_DIR = DATA_DIR / "output"

CACHE_DIR = BASE_DIR / "cache"
CROSSREF_CACHE_DIR = CACHE_DIR / "crossref"
OPENALEX_CACHE_DIR = CACHE_DIR / "openalex"
SCOPUS_CACHE_DIR = CACHE_DIR / "scopus"
DOI_CACHE_DIR = CACHE_DIR / "doi"

# Ensure runtime directories exist
for p in [INPUT_DIR, INTERMEDIATE_DIR, OUTPUT_DIR, CROSSREF_CACHE_DIR, OPENALEX_CACHE_DIR, SCOPUS_CACHE_DIR, DOI_CACHE_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# Load environment variables
load_dotenv(BASE_DIR / ".env")

# API Keys & Endpoints
ELSEVIER_API_KEY = os.getenv("ELSEVIER_API_KEY", "").strip()
CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO", "researcher@iitd.ac.in").strip()
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "researcher@iitd.ac.in").strip()

# HTTP & Rate Limiting Settings
REQUEST_TIMEOUT = 15.0  # seconds
MAX_RETRIES = 3
BACKOFF_FACTOR = 1.5
USER_AGENT = f"ScholarlyRefValidator/1.0 (mailto:{CROSSREF_MAILTO})"

# Default input file
DEFAULT_INPUT_CSV = INPUT_DIR / "scopus_export.csv"
if not DEFAULT_INPUT_CSV.exists():
    # Fallback to any scopus csv in root if needed
    candidates = list(BASE_DIR.glob("scopus_export_*.csv"))
    if candidates:
        DEFAULT_INPUT_CSV = candidates[0]

# Matching weights (calibrated defaults)
WEIGHT_TITLE = 0.40
WEIGHT_AUTHOR = 0.25
WEIGHT_JOURNAL = 0.15
WEIGHT_YEAR = 0.10
WEIGHT_VOLUME_PAGE = 0.10

# Thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.85
MEDIUM_CONFIDENCE_THRESHOLD = 0.65
WRONG_DOI_THRESHOLD = 0.45

# LLM Bibliometric Intelligence Settings
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL", "llama3:latest").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
ENABLE_LLM_FALLBACK = os.getenv("ENABLE_LLM_FALLBACK", "true").strip().lower() in ("true", "1", "yes")

