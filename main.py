#!/usr/bin/env python3
"""
University Brand Monitor
========================
Usage:
  python main.py crawl                     # all schools, all sources
  python main.py crawl --school wgu        # one school
  python main.py crawl --source reddit     # one source only
  python main.py analyze                   # run sentiment analysis (free, offline)
  python main.py status                    # show mention counts
  python main.py dashboard                 # open Streamlit dashboard

Sources: reddit, niche, trustpilot, sitejabber, bbb, quora
"""

import argparse
import subprocess
import sys

from config import SCHOOLS
from database import init_db, get_mention_count, total_unanalyzed

SOURCES = ["reddit", "niche", "trustpilot", "sitejabber", "bbb", "quora"]


def cmd_crawl(args):
    init_db()
    schools = list(SCHOOLS.keys()) if args.school == "all" else [args.school]

    import scrapers.reddit      as reddit_scraper
    import scrapers.niche       as niche_scraper
    import scrapers.trustpilot  as trustpilot_scraper
    import scrapers.sitejabber  as sitejabber_scraper
    import scrapers.bbb         as bbb_scraper
    import scrapers.quora       as quora_scraper

    scraper_map = {
        "reddit":      ("Reddit",      reddit_scraper),
        "niche":       ("Niche.com",   niche_scraper),
        "trustpilot":  ("Trustpilot",  trustpilot_scraper),
        "sitejabber":  ("Sitejabber",  sitejabber_scraper),
        "bbb":         ("BBB",         bbb_scraper),
        "quora":       ("Quora",       quora_scraper),
    }

    run_sources = SOURCES if args.source == "all" else [args.source]

    for school_key in schools:
        name = SCHOOLS[school_key]["name"]
        print(f"\n{'─' * 55}")
        print(f"  {name}")
        print(f"{'─' * 55}")

        for source_key in run_sources:
            label, scraper = scraper_map[source_key]
            print(f"  [{label}]")
            try:
                scraper.run(school_key)
            except Exception as e:
                print(f"    Error: {e}")

    print("\nCrawl complete. Run `python3 main.py analyze` next.")


def cmd_analyze(_args):
    init_db()
    import analyzer
    total = analyzer.run(batch_size=50)
    print(f"\nDone. {total} mentions analyzed.")
    print("Run `python main.py dashboard` to view results.")


def cmd_status(_args):
    init_db()
    counts = get_mention_count()
    pending = total_unanalyzed()

    print(f"\n{'School':<22} {'Source':<18} {'Mentions':>8}")
    print("─" * 52)
    for (school_key, source), n in sorted(counts.items()):
        label = SCHOOLS.get(school_key, {}).get("short", school_key)
        print(f"{label:<22} {source:<18} {n:>8,}")

    total = sum(counts.values())
    print("─" * 52)
    print(f"{'TOTAL':<40} {total:>8,}")
    print(f"\nPending analysis: {pending:,}")


def cmd_dashboard(_args):
    subprocess.run([sys.executable, "-m", "streamlit", "run", "dashboard.py"], check=False)


def main():
    parser = argparse.ArgumentParser(
        description="University Brand Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    crawl_p = sub.add_parser("crawl", help="Crawl review sites and Reddit")
    crawl_p.add_argument(
        "--school",
        default="all",
        choices=list(SCHOOLS.keys()) + ["all"],
        help="Which school to crawl (default: all)",
    )
    crawl_p.add_argument(
        "--source",
        default="all",
        choices=["all"] + SOURCES,
        help="Which source to crawl (default: all)",
    )

    sub.add_parser("analyze", help="Run Claude sentiment analysis on new mentions")
    sub.add_parser("status", help="Show mention counts and analysis queue")
    sub.add_parser("dashboard", help="Launch the Streamlit dashboard")

    args = parser.parse_args()

    if args.command == "crawl":
        cmd_crawl(args)
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "dashboard":
        cmd_dashboard(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
