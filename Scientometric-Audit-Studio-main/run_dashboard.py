"""
Single-command launcher for the Scientometric Validation Dashboard (FastAPI + React).
Usage:
    python run_dashboard.py
    python run_dashboard.py --port 8000
    python run_dashboard.py --host 0.0.0.0 --port 8000
"""
import sys
import argparse
from pathlib import Path

# Add project root and appropriate .venv site-packages to path
BASE_DIR = Path(__file__).resolve().parent
venv_name = ".venv312" if sys.version_info[:2] == (3, 12) else ".venv"
site_packages = BASE_DIR / venv_name / "Lib" / "site-packages"
if site_packages.exists() and str(site_packages) not in sys.path:
    sys.path.insert(0, str(site_packages))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import uvicorn
from src.web.server import app

def main():
    parser = argparse.ArgumentParser(description="Scientometric Validation Dashboard Server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    print("\n" + "=" * 65)
    print("[*] SCHOLARLY REFERENCE VALIDATION STUDIO (FASTAPI + REACT)")
    print("=" * 65)
    print(f"  * Local Web Dashboard: http://localhost:{args.port}")
    print(f"  * Interactive API Docs: http://localhost:{args.port}/docs")
    print(f"  * REST API Base URL:   http://localhost:{args.port}/api")
    print("=" * 65 + "\n")

    uvicorn.run("src.web.server:app", host=args.host, port=args.port, reload=args.reload)

if __name__ == "__main__":
    main()
