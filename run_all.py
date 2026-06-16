"""Run all production scrapers in sequence."""
import sys

from scrapers import ecda_data_gov, ecda_upcoming, lifesg_fees, myfirstskool

SCRAPERS = [
    ("ecda_data_gov", ecda_data_gov.run),
    ("ecda_upcoming", ecda_upcoming.run),
    ("lifesg_fees", lifesg_fees.run),
    ("myfirstskool", myfirstskool.run),
]


def main() -> None:
    failed = []
    for name, run in SCRAPERS:
        print(f"\n{'='*60}")
        print(f"Running {name}")
        print("=" * 60)
        try:
            run()
        except Exception as e:
            print(f"ERROR in {name}: {e}", file=sys.stderr)
            failed.append(name)

    if failed:
        print(f"\nFailed scrapers: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)

    print("\nAll scrapers completed successfully.")


if __name__ == "__main__":
    main()
