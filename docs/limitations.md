# Scientific and implementation limitations

- No real scientific dataset has been processed; all test measurements are synthetic.
- The real Mars/Moon/two-Earth availability checkpoint and >=10-site acceptance
  criteria remain unmet. No scientific ranking is claimed.
- PDS decoding depends on GDAL and an audited interpretation sidecar. Supported
  mechanics have temporary GeoTIFF tests; real PDS product interpretation is pending.
- Source units, vertical datum, masks and coordinate semantics require scientific
  review beyond schema validation. Ingestion does not prove metadata are truthful.
- Water/ground masks must already be present in supplied rasters. No automatic
  water detection, acquisition, mosaicking or arbitrary upload is implemented.
- Source resolution checks are local samples, not a global distortion guarantee.
  Pole/dateline crossings and longitude normalization need dedicated validation.
- Catalog polygons require verified geolocation. Automated equivalence between
  catalog footprints and projected analysis bounds remains incomplete.
- Buffered derivative margins are not implemented; edge samples are consistently
  excluded. Fully valid roughness windows and conservative aggregation may reduce
  coverage near masks.
- The first map uses online basemap tiles. Numerical analysis, tables, methodology
  and CSV remain local; a self-contained offline basemap is a follow-up task.
- Interactive map/table selection synchronization, weight sliders, two-site
  comparison, measured terrain transects and geology tags are not complete.
- Weight/tolerance sensitivity and independent sanity checks require real data.
- Release gates cover automated counts/schema/ranking checks, not source rights,
  novelty, geographic distinctness or independent scientific review.
- Per-file output replacement is atomic; the collection of profile tables and
  report is not a transactional multi-file snapshot. Do not prepare files while
  the app is reading a production bundle.

Terrain similarity does not establish matching geology, chemistry, atmosphere,
gravity, radiation, temperature, resources, accessibility, operational suitability
or safety. It is not a NASA recommendation or endorsement. Known analogs must be
described as baselines; novelty requires a literature review.
