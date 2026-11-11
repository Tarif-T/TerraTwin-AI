# Source inventory and third-party credits

The development guide supplied by the project owner defines the MVP requirements.
No source raster or prepared scientific table is redistributed at this stage.
The authoritative product-level registry is [sources.csv](../data/metadata/sources.csv),
currently header-only. Archive links below are acquisition entry points, not
evidence that a particular raster has been processed or its rights verified.

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
