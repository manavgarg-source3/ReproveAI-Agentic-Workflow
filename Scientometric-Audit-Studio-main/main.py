"""
Main Command Line Interface for Scholarly Reference Validation System.
Usage:
    python main.py phase1
    python main.py phase2
    python main.py test-apis
    python main.py validate --docs 10
    python main.py validate --full
"""
import argparse
import sys
import os
import logging
from pathlib import Path

# Bootstrap paths
BASE_DIR = Path(__file__).resolve().parent
venv_name = ".venv312" if sys.version_info[:2] == (3, 12) else ".venv"
site_packages = BASE_DIR / venv_name / "Lib" / "site-packages"
if site_packages.exists() and str(site_packages) not in sys.path:
    sys.path.insert(0, str(site_packages))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import DEFAULT_INPUT_CSV, OUTPUT_DIR, ELSEVIER_API_KEY
from src.pipeline.phase1_segmentation import run_phase1
from src.pipeline.phase2_doi_extraction import run_phase2
from src.pipeline.runner import PipelineRunner
from src.providers.crossref import CrossrefClient
from src.providers.openalex import OpenAlexClient
from src.providers.scopus import ScopusClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def test_apis() -> None:
    """Tests connectivity to Scopus, Crossref, and OpenAlex."""
    print("\n" + "=" * 60)
    print("TESTING API CONNECTIVITY")
    print("=" * 60)

    # 1. Scopus API
    scopus = ScopusClient()
    if scopus.is_configured():
        print("[1/3] Testing Elsevier Scopus Search API...")
        try:
            res = scopus._search("TITLE-ABS-KEY(machine learning)", count=1)
            rem = scopus.rate_limit_remaining
            print(f"      [SUCCESS] Scopus API connected. Returned {len(res)} results. Rate limit remaining: {rem}")
        except Exception as e:
            print(f"      [FAILURE] Scopus API error: {e}")
    else:
        print("      [WARNING] ELSEVIER_API_KEY is not configured in .env.")

    # 2. Crossref API
    test_doi = "10.14429/djlit.41.6.17069"
    print("[2/3] Testing Crossref REST API...")
    try:
        cr = CrossrefClient()
        work = cr.get_by_doi(test_doi)
        if work and work.get("title"):
            print(f"      [SUCCESS] Crossref connected. Resolved DOI: '{work.get('title')[:60]}...'")
        else:
            print("      [WARNING] Crossref returned empty response.")
    except Exception as e:
        print(f"      [FAILURE] Crossref error: {e}")

    # 3. OpenAlex API
    print("[3/3] Testing OpenAlex API...")
    try:
        oa = OpenAlexClient()
        work = oa.get_by_doi(test_doi)
        if work and work.get("title"):
            print(f"      [SUCCESS] OpenAlex connected. Resolved DOI: '{work.get('title')[:60]}...'")
        else:
            print("      [WARNING] OpenAlex returned empty response.")
    except Exception as e:
        print(f"      [FAILURE] OpenAlex error: {e}")

    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Scholarly Reference Validation System CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: phase1
    subparsers.add_parser("phase1", help="Execute Phase 1 Reference Segmentation")

    # Command: phase2
    subparsers.add_parser("phase2", help="Execute Phase 2 DOI Extraction")

    # Command: test-apis
    subparsers.add_parser("test-apis", help="Test connectivity to Crossref, OpenAlex, and Scopus APIs")

    # Command: validate
    val_parser = subparsers.add_parser("validate", help="Run reference verification pipeline")
    val_parser.add_argument("--docs", type=int, default=None, help="Number of documents to process (e.g. 10)")
    val_parser.add_argument("--refs", type=int, default=None, help="Number of references to process (e.g. 50)")
    val_parser.add_argument("--full", action="store_true", help="Process full dataset")
    val_parser.add_argument("--reset", action="store_true", help="Reset previous checkpoints and run clean validation")

    args = parser.parse_args()

    if args.command == "phase1":
        run_phase1()
    elif args.command == "phase2":
        run_phase2()
    elif args.command == "test-apis":
        test_apis()
    elif args.command == "validate":
        runner = PipelineRunner()
        if args.reset:
            runner.checkpoint.clear()
        if args.full:
            runner.run(resume=not args.reset)
        else:
            docs = args.docs if args.docs is not None else 10
            refs = args.refs
            runner.run(max_documents=docs, max_references=refs, resume=not args.reset)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

