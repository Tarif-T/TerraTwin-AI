"""Validate local planetary jobs before running the complete build."""

import argparse
from pathlib import Path

from terratwin.config import ROOT, read_yaml
from terratwin.ingest.manifest import load_manifest
from terratwin.ingest.pds_loader import load_pds
from terratwin.pipeline import Job, PipelineConfig


def main():
    parser = argparse.ArgumentParser(
        description="Validate original labels and local Mars/Moon rasters"
    )
    parser.add_argument("--config", type=Path, default=ROOT / "config/pipeline.yaml")
    args = parser.parse_args()
    try:
        config = PipelineConfig.model_validate(read_yaml(args.config))
        sources = load_manifest(ROOT / "data/metadata/sources.csv")
        jobs = [Job.model_validate(job) for job in config.jobs]
        selected = [job for job in jobs if sources[job.source_id].planetary_body != "Earth"]
        if not selected:
            raise ValueError(
                "No verified planetary jobs; MOLA and LOLA rasters and labels are required"
            )
        for job in selected:
            load_pds(ROOT / job.raster_path, ROOT / job.interpretation_path, sources[job.source_id])
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Blocked: {error}\n")
    print(
        f"Validated {len(selected)} planetary inputs. Run scripts/build_profiles.py for extraction."
    )


if __name__ == "__main__":
    main()
