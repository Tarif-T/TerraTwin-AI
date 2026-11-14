"""Register carefully scoped transcriptions of inspected primary-source claims.

Transcriptions are identified as such; their hashes are not publisher checksums.
No source is represented as an independent expert approval of this application.
"""

import json
from datetime import datetime, timezone

from terratwin.config import ROOT
from terratwin.ingest.manifest import sha256_file
from terratwin.science import EvidenceBundle, Observation, ScientificSource


def prepare():
    now = datetime.now(timezone.utc).isoformat()
    folder = ROOT / "data/metadata/evidence/science"
    folder.mkdir(exist_ok=True)
    sources, observations = [], []

    def source(key, title, url, attribution, claims):
        parsed = [Observation.model_validate(dict(**claim, source_ids=[key])) for claim in claims]
        path = folder / f"{key}.json"
        snapshot = dict(
            source_url=url,
            title=title,
            verified_utc=now,
            capture_method="Structured transcription of primary page inspected with web "
            "research; not original HTML",
            claims=[o.model_dump(mode="json") for o in parsed],
        )
        path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        sources.append(
            ScientificSource(
                source_id=key,
                title=title,
                url=url,
                snapshot_path=path.relative_to(ROOT).as_posix(),
                snapshot_sha256=sha256_file(path),
                snapshot_type="structured_transcription",
                accessed_utc=now,
                attribution=attribution,
            )
        )
        observations.extend(parsed)

    def claim(
        key, subject, domain, quantity, value, unit, statistic, scope, status, interpretation
    ):
        return dict(
            observation_id=key,
            subject_id=subject,
            domain=domain,
            quantity=quantity,
            value=value,
            unit=unit,
            statistic=statistic,
            scope=scope,
            status=status,
            interpretation=interpretation,
        )

    source(
        "NASA_MOON_FACTS",
        "NASA Moon Fact Sheet",
        "https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html",
        "NASA GSFC/NSSDC",
        [
            claim(
                "moon_gravity",
                "body:Moon",
                "environment",
                "surface_gravity_m_s2",
                1.62,
                "m/s2",
                "body_mean",
                "body",
                "reported",
                "Body reference gravity, not an ROI surface measurement.",
            ),
            claim(
                "earth_gravity",
                "body:Earth",
                "environment",
                "surface_gravity_m_s2",
                9.8,
                "m/s2",
                "body_mean",
                "body",
                "reported",
                "Earth reference gravity; local geographic variations are not resolved.",
            ),
            claim(
                "moon_pressure",
                "body:Moon",
                "environment",
                "surface_pressure_pa",
                3e-10,
                "Pa",
                "night_body_context",
                "body",
                "reported",
                "Night exosphere pressure from 3e-15 bar; not an annual local "
                "atmosphere observation.",
            ),
        ],
    )
    source(
        "NASA_MARS_FACTS",
        "NASA Mars Fact Sheet",
        "https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
        "NASA GSFC/NSSDC",
        [
            claim(
                "mars_gravity",
                "body:Mars",
                "environment",
                "surface_gravity_m_s2",
                3.73,
                "m/s2",
                "body_mean",
                "body",
                "reported",
                "NASA table mean surface gravity, not a terrain-dependent local estimate.",
            ),
            claim(
                "mars_pressure",
                "body:Mars",
                "environment",
                "surface_pressure_pa",
                636,
                "Pa",
                "mean_radius_context",
                "body",
                "reported",
                "6.36 mbar at mean radius; seasonally variable and not a Jezero MEDA measurement.",
            ),
        ],
    )
    source(
        "NASA_JEZERO_GEOLOGY",
        "NASA Jezero crater discoveries",
        "https://www.nasa.gov/missions/mars-2020-perseverance/perseverance-rover/nasas-perseverance-makes-new-discoveries-in-mars-jezero-crater/",
        "NASA/JPL-Caltech Perseverance science",
        [
            claim(
                "jezero_materials",
                "mars_jezero_60km_v1",
                "geology",
                "geologic_material_categories",
                ["igneous"],
                "category",
                "reported_presence",
                "study_region",
                "reported",
                "Crater-floor igneous rocks; no ROI mineral percentages inferred.",
            ),
        ],
    )
    source(
        "NASA_JEZERO_DELTA",
        "NASA Perseverance explores the Jezero crater delta",
        "https://science.nasa.gov/resource/perseverance-explores-the-jezero-crater-delta/",
        "NASA/JPL-Caltech Perseverance science",
        [
            claim(
                "jezero_delta_materials",
                "mars_jezero_60km_v1",
                "geology",
                "geologic_material_categories",
                ["sedimentary"],
                "category",
                "reported_presence",
                "study_region",
                "reported",
                "Published delta sedimentary-rock context; no whole-ROI material "
                "proportions inferred.",
            )
        ],
    )
    source(
        "NASA_MARE_GEOLOGY",
        "NASA Mare Tranquillitatis basaltic setting",
        "https://science.nasa.gov/image-detail/20100528/",
        "NASA/GSFC/LRO",
        [
            claim(
                "mare_materials",
                "moon_tranquillitatis_pit_60km_v1",
                "geology",
                "geologic_material_categories",
                ["igneous"],
                "category",
                "reported_presence",
                "study_region",
                "reported",
                "The mare is a basaltic lava setting; regional context, not "
                "mineral abundances at the pit.",
            ),
        ],
    )
    source(
        "LROC_TRANQUILLITATIS_PIT",
        "LROC Pits Atlas: Mare Tranquillitatis Pit",
        "https://lroc.im-ldi.com/atlases/pits/3",
        "NASA/GSFC/Arizona State University LROC",
        [
            claim(
                "mare_pit_depth",
                "moon_tranquillitatis_pit_60km_v1",
                "caves",
                "pit_depth_m",
                105,
                "m",
                "stereo_model_depth_below_funnel",
                "named_site",
                "reported",
                "LROC stereo-model inner pit depth below funnel; not conduit "
                "length or total access depth.",
            ),
        ],
    )
    source(
        "NASA_LUNAR_CONDUIT",
        "NASA radar evidence for a lunar cave conduit",
        "https://science.nasa.gov/solar-system/moon/new-evidence-adds-to-findings-hinting-at-network-of-caves-on-moon/",
        "NASA LRO / Mini-RF science",
        [
            claim(
                "mare_subsurface_setting",
                "moon_tranquillitatis_pit_60km_v1",
                "caves",
                "subsurface_setting_categories",
                ["volcanic_subsurface"],
                "category",
                "reported_presence",
                "named_site",
                "reported",
                "Published orbital evidence supports a conduit associated with "
                "the pit; traversability and stability are unverified.",
            ),
        ],
    )
    source(
        "NPS_SKULL_CAVE",
        "National Park Service: Skull Cave",
        "https://www.nps.gov/places/skull-cave.htm",
        "US National Park Service",
        [
            claim(
                "skull_length",
                "earth_lava_beds",
                "caves",
                "cave_length_m",
                177,
                "m",
                "reported_passage_length",
                "named_site",
                "reported",
                "NPS length for named Skull Cave in Lava Beds; not the size of "
                "the whole region or a lunar pit depth.",
            ),
            claim(
                "skull_ice",
                "earth_lava_beds",
                "resources",
                "water_ice_presence",
                "reported_ice_floor",
                "state",
                "reported_presence",
                "named_site",
                "reported",
                "NPS describes an ice floor in Skull Cave. No current ice mass, "
                "extraction permit, yield or feasibility is established.",
            ),
            claim(
                "lava_subsurface_setting",
                "earth_lava_beds",
                "caves",
                "subsurface_setting_categories",
                ["volcanic_subsurface"],
                "category",
                "reported_presence",
                "named_site",
                "reported",
                "Named Lava Beds cave is a lava-tube setting. Cave geometry is "
                "distinct from the kilometre-scale surface profile.",
            ),
        ],
    )
    source(
        "NPS_MUSHPOT_CAVE",
        "National Park Service: Mushpot Cave",
        "https://www.nps.gov/places/mushpot-cave.htm",
        "US National Park Service",
        [
            claim(
                "mushpot_length",
                "earth_lava_beds",
                "caves",
                "cave_length_m",
                235,
                "m",
                "reported_passage_length",
                "named_site",
                "reported",
                "NPS reports 235 m for named Mushpot Cave. It is a separate cave "
                "from Skull; lengths must not be conflated.",
            ),
        ],
    )
    source(
        "NASA_BRAILLE_BASELINE",
        "NASA BRAILLE Lava Beds field-site context",
        "https://www.nasa-braille.org/about-braille/the-field-site/lava-tubes",
        "NASA BRAILLE science team; original references retained on project page",
        [
            claim(
                "lava_materials",
                "earth_lava_beds",
                "geology",
                "geologic_material_categories",
                ["igneous"],
                "category",
                "reported_presence",
                "study_region",
                "reported",
                "Published volcanic lava-tube field site; regional material "
                "context does not replace the centroid geological map.",
            ),
            claim(
                "lava_known_baseline",
                "earth_lava_beds",
                "novelty",
                "analog_publication_status",
                "known_baseline",
                "state",
                "published_usage",
                "study_region",
                "reported",
                "NASA BRAILLE already uses this cave region as an analog; it is a "
                "baseline, not a newly discovered analog.",
            ),
        ],
    )
    source(
        "NASA_HAUGHTON_BASELINE",
        "NASA Haughton field-test baseline report",
        "https://ntrs.nasa.gov/api/citations/20110008151/downloads/20110008151.pdf",
        "NASA NTRS; published field-test study",
        [
            claim(
                "haughton_materials",
                "baseline:haughton",
                "geology",
                "geologic_setting_categories",
                ["impact", "polar_desert"],
                "category",
                "reported_presence",
                "named_site",
                "reported",
                "Known impact/polar-desert analog baseline. No nearby ArcticDEM "
                "ROI is automatically relabeled as the crater.",
            ),
        ],
    )
    bundle = EvidenceBundle(version="science_v1", sources=sources, observations=observations)
    (ROOT / "data/metadata/science_evidence.json").write_text(
        bundle.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Registered {len(sources)} primary-source transcriptions "
        f"and {len(observations)} observations"
    )


if __name__ == "__main__":
    prepare()
