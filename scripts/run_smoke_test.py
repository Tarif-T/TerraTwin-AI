"""App smoke test is valid before data arrival; --release enforces scientific acceptance."""

import argparse

from streamlit.testing.v1 import AppTest

from terratwin.config import ROOT, load_scoring
from terratwin.datasets import load_prepared
from terratwin.scoring.engine import rank_candidates


def main():
    parser = argparse.ArgumentParser(
        description="Smoke-test the offline app and optional release data"
    )
    parser.add_argument(
        "--release", action="store_true", help="Require real references and >=10 Earth sites"
    )
    args = parser.parse_args()
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    if app.exception:
        parser.exit(1, f"App failed: {app.exception}\n")
    print("PASS: app renders without an exception")
    if args.release:
        try:
            references, sites, _ = load_prepared()
            config = load_scoring()
            good = [
                p
                for p in references
                if p.qa_pass and p.valid_cell_fraction >= config.minimum_valid_cell_fraction
            ]
            if {p.body for p in good} != {"Mars", "Moon"}:
                raise ValueError("Release requires verified Mars and Moon references")
            if (
                len(
                    {
                        p.site_id
                        for p in sites
                        if p.qa_pass and p.valid_cell_fraction >= config.minimum_valid_cell_fraction
                    }
                )
                < 10
            ):
                raise ValueError("Release requires at least ten QA-approved Earth sites")
            for reference in good:
                if sum(r["eligible"] for r in rank_candidates(reference, sites, config)) < 10:
                    raise ValueError("Release requires ten eligible sites per reference")
        except (ValueError, OSError, KeyError) as error:
            parser.exit(1, f"Release blocked: {error}\n")
        print("PASS: scientific dataset count and ranking gates")


if __name__ == "__main__":
    main()
