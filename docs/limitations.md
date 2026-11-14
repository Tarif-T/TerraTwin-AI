# Scientific and implementation limitations

- A real Mars/one-Earth slice is numerically verified. Scientific suitability and
  useful rankings across distinct candidates have not been established.
- The real Mars/Moon/two-Earth availability checkpoint and >=10-site acceptance
  criteria remain unmet. Rank 1 among one candidate establishes no superiority.
- PDS decoding depends on GDAL and an audited interpretation sidecar. Supported
  mechanics have temporary GeoTIFF tests and a real MOLA comparison; LOLA is blocked.
- Source units, vertical datum, masks and coordinate semantics require scientific
  review beyond schema validation. Ingestion does not prove metadata are truthful.
- The external NASADEM SWB mask is checksummed and applied during preprocessing.
  No automatic water detection, mosaicking or arbitrary upload is implemented.
- Source resolution checks are local samples, not a global distortion guarantee.
  Pole/dateline crossings and longitude normalization need dedicated validation.
- Catalog polygons require verified geolocation. Earth polygon/analysis bounds
  equivalence is now checked automatically in the local metric projection.
- Buffered derivative margins are not implemented; edge samples are consistently
  excluded. Fully valid roughness windows and conservative aggregation may reduce
  coverage near masks.
- The first map uses online basemap tiles. Numerical analysis, tables, methodology
  and CSV remain local; a self-contained offline basemap is a follow-up task.
- Interactive map/table selection synchronization, weight sliders, two-site
  comparison, measured terrain transects and geology tags are not complete.
- Limited weight sensitivity and independent arithmetic checks were run on the
  real slice. Broader calibration and held-out expert assessment remain pending.
- Four aggregate features do not compare crater shape or spatial arrangement.
  A high index can occur for visually different landforms under broad tolerances.
- The Earth original ZIP checksum has not been independently verified against the
  provider. Source members are locally hashed and tied to original CMR metadata.
- Release gates cover automated counts/schema/ranking checks, not source rights,
  novelty, geographic distinctness or independent scientific review.
- Per-file output replacement is atomic; the collection of profile tables and
  report is not a transactional multi-file snapshot. Do not prepare files while
  the app is reading a production bundle.

Terrain similarity does not establish matching geology, chemistry, atmosphere,
gravity, radiation, temperature, resources, accessibility, operational suitability
or safety. It is not a NASA recommendation or endorsement. Known analogs must be
described as baselines; novelty requires a literature review.
