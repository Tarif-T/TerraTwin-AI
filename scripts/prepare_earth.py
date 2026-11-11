import argparse
from pathlib import Path

from terratwin.config import ROOT, read_yaml
from terratwin.datasets import load_catalog
from terratwin.ingest.earth_loader import load_nasadem
from terratwin.ingest.manifest import load_manifest
from terratwin.pipeline import Job, PipelineConfig


def main():
    parser = argparse.ArgumentParser(
        description="Validate local NASADEM inputs and catalog polygons"
    )
    parser.add_argument("--sites", type=Path, default=ROOT / "data/catalog/earth_sites.geojson")
    parser.add_argument("--config", type=Path, default=ROOT / "config/pipeline.yaml")
    args = parser.parse_args()
    try:
        catalog = load_catalog(args.sites)
        if not catalog:
            raise ValueError("No verified Earth ROI polygons in catalog")
        sources = load_manifest(ROOT / "data/metadata/sources.csv")
        config = PipelineConfig.model_validate(read_yaml(args.config))
        selected = [
            Job.model_validate(job)
            for job in config.jobs
            if sources[job["source_id"]].planetary_body == "Earth"
        ]
        if not selected:
            raise ValueError("No local NASADEM jobs configured")
        for job in selected:
            load_nasadem(
                ROOT / job.raster_path, ROOT / job.interpretation_path, sources[job.source_id]
            )
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Blocked: {error}\n")
    print(f"Validated {len(selected)} Earth inputs. Run scripts/build_profiles.py for extraction.")


if __name__ == "__main__":
    main()
