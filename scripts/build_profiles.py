import argparse
import logging
from pathlib import Path

from terratwin.config import ROOT
from terratwin.pipeline import build_profiles


def main():
    parser = argparse.ArgumentParser(
        description="Build measured profiles from audited local raster jobs"
    )
    parser.add_argument("--config", type=Path, default=ROOT / "config/pipeline.yaml")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        profiles = build_profiles(args.config)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Blocked: {error}\n")
    logging.info("Prepared %d measured profiles", len(profiles))


if __name__ == "__main__":
    main()
