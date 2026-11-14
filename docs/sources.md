# Source inventory and third-party credits

The development guide supplied by the project owner defines the MVP requirements.
The registry [sources.csv](../data/metadata/sources.csv) now identifies MOLA's
MEGT44N000HB image and NASADEM n36w117 HGT/SWB/NUM members. Small measured profiles
and derived analysis grids are included; original large rasters remain excluded.
Cached original PDS4/CMR metadata, the NASADEM guide, verification hashes and a
clearly identified structured Gazetteer transcription are under `data/metadata/evidence/`.
Original user download dates are unknown and not invented.

PDS's [FAQ](https://pds-geosciences.wustl.edu/faq.html) states archived PDS data are
public domain. NASADEM credit follows the [USGS data citation policy](https://www.usgs.gov/centers/eros/data-citation).
Credit the MOLA and NASADEM science teams, NASA PDS Geosciences, NASA JPL and LP DAAC.
Use of these data implies no agency endorsement. Earth ZIP publisher checksum
verification remains incomplete; the registry explicitly preserves that limitation.

- [PDS MOLA MEGDR](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html)
- [PDS LOLA](https://pds-geosciences.wustl.edu/missions/lro/lola.htm)
- [NASADEM_HGT.001](https://doi.org/10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001)

Runtime libraries include NumPy, Pandas, SciPy, Pydantic, PyYAML, Rasterio/GDAL,
PyProj/PROJ, GeoPandas, Shapely, PyArrow, Streamlit and PyDeck. Test/development
tools are pytest and Ruff. Their original licenses remain in the installed package
distributions; the project's Apache-2.0 license does not relicense dependencies or
data. Version pins are in [the tested constraints](../constraints-py311-windows.txt).

The Apache-2.0 license text was obtained from the installed Requests distribution's
unmodified standard license text, after direct retrieval from apache.org failed.
No NASA insignia, stock planetary imagery or fabricated scientific citations have
been added. Review dataset rights and retain required credits before release.
