# Jezero local environmental evidence

The app now includes real Perseverance MEDA measurements for sols 100 and 101:
five calibrated local air-temperature detector channels and derived pressure.
These observations are separate from body-mean Mars facts and from the 60 km
terrain aggregates. They do not establish climate across the entire ROI.

## Data and provenance

Four original CSV tables and four PDS4 labels were downloaded from the
[NASA PDS MEDA archive](https://atmos.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/).
The captured directory listings and README are also retained. The highest product
version in each captured listing was selected. CSV byte lengths, header order,
table row counts, physical units and publisher MD5 values are checked before use.
Some original labels omit leading hexadecimal zeroes in the MD5; normalization
restores those zeroes before comparing digests. Local SHA256 checksums additionally
register all thirteen original responses in the scientific source registry.

PDS recommends derived products where available and calibrated products otherwise.
Accordingly, this slice uses calibrated ATS and derived PS. Citation:
Rodriguez-Manfredi et al. (2021), MEDA, NASA Planetary Data System, DOI
[10.17189/1522849](https://doi.org/10.17189/1522849).

## Example observed statistics

| Sol | Channel | Observed median | Observed range | Retained samples | Approximate sol-time coverage |
| ---: | --- | ---: | --- | ---: | ---: |
| 100 | ATS_LOCAL_TEMP1 | 213.51 K | 191.47–258.30 K | 102,827 | 57.91% |
| 101 | ATS_LOCAL_TEMP1 | 212.11 K | 191.04–259.11 K | 95,724 | 53.91% |
| 100 | PRESSURE | 759.08 Pa | 753.59–771.08 Pa | 51,195 | 57.67% |
| 101 | PRESSURE | 760.39 Pa | 753.22–770.69 Pa | 47,549 | 53.56% |

The CSV includes all five temperature detectors. The label describes local
temperatures near units mounted at different rover orientations and locations.
They are not automatically equivalent to Earth ERA5 two-metre air temperature.

UTC product spans are retained explicitly. For example, sol 100 ATS spans
2021-05-31T22:23:00.282Z to 2021-06-01T22:06:29.955Z. Median/minimum/maximum
describe available samples within the product, not full-sol statistics or annual
climate. Approximate time coverage counts occupied one-second spacecraft-clock
bins divided by 88,775.244 seconds per Mars sol. Samples occur in every local-time
hour here, but significant sub-hour gaps remain. Occupied hours alone cannot prove
continuous coverage. Hourly charts show medians of observed samples and do not
fill missing values. Observed range and detector spread are not error estimates.

## Uncertainty and compatibility

Both original pressure labels specify `kelvin` for `PRESSURE UNCERTAINTY`, while
pressure itself is in pascals. The pressure-uncertainty fields are blank in this
slice. The app preserves this metadata conflict and leaves uncertainty unknown.
It does not reinterpret the field as a validated pressure error or assign zero.
The ATS labels provide no instrument-uncertainty column. Rover heating, detector
orientation and sampling effects remain limitations needing specialist treatment.

Temporal observations retain UTC bounds, sample count, sampling basis,
measurement method, and optional attributed uncertainty and comparison protocol.
Numerical comparison requires equivalent quantity, units, statistic and scope;
temporal observations must also declare the same nonempty comparison protocol and
sampling basis. A matching protocol identifier documents an explicit curation
decision, not automatic scientific approval.

These rover samples are not included in the environmental ranking score against
Earth's 2015–2024 ERA5 climate means. That requires a defensible matched
height, season and time-sampling protocol. Current environmental scoring remains
body-gravity context; local lunar thermal, illumination and radiation evidence
is still unprepared. Terrain rankings remain unchanged.

## App workflow

Open Research evidence, choose Jezero as Research target, expand Local planetary
environmental measurements, and enable Inspect local measurements. Review the
sensor table, hourly temperature/pressure charts, coverage and source links,
then download the local environment CSV. Lunar targets show that no local
time series is prepared and do not retain a stale Jezero download.

## Reproduce and inspect

```powershell
.venv/Scripts/python.exe -m scripts.prepare_meda
.venv/Scripts/python.exe scripts/validate_research.py
.venv/Scripts/python.exe -m pytest -q
```

Preparation is idempotent: rerunning it checks existing source identities and
retains acquisition timestamps. Rerunning curated scientific preparation
preserves imported MEDA observations. The summary loader reruns table summarization,
so editing a summary and recomputing only its stored hash cannot change displayed evidence.

- [Environmental summary CSV](../data/processed/jezero_meda_sols100_101.csv)
- [Hourly and sensor summaries](../data/processed/planetary_environment.json)
- [Scientific observations and source registry](../data/metadata/science_evidence.json)
- [Research UI regression report](../data/processed/research_validation.json)
- [PDS MEDA interpretation cautions](https://atmos.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/readme.txt)

Automated checks cover publisher checksum corruption, wrong units/sol/row counts,
blank/sentinel missingness, sparse sample coverage, tampered summaries,
temporal contracts and sampling-protocol gates. Real UI checks verify sensor-table
values, the uncertainty warning and clearing the local CSV on target changes.
These are implementation checks, not independent scientific validation or field approval.
