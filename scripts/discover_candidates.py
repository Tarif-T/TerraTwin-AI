"""Background worker for explicit app discovery runs."""

import argparse
import re

from terratwin.config import ROOT
from terratwin.discovery import execute

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-f0-9]{32}", args.run):
        parser.error("Run ID must be a generated 32-character hexadecimal identifier")
    execute(ROOT, ROOT / "data/processed/discovery" / args.run)
