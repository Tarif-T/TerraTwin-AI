import argparse
from pathlib import Path

from terratwin.config import ROOT
from terratwin.ingest.manifest import load_manifest


def main():
    parser = argparse.ArgumentParser(description="Validate source manifest records (offline)")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/metadata/sources.csv")
    args = parser.parse_args()
    try:
        records = load_manifest(args.manifest)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Blocked: {error}\n")
    print(
        f"Validated {len(records)} manifest records; "
        "remote link/rights verification remains manual."
    )


if __name__ == "__main__":
    main()
