# Third-party sources and assets

The MIT license applies to original NeuraX code. It does not relicense external publications, satellite products, dependencies, imagery or trademarks.

| Material | Attribution and terms |
|---|---|
| NASA POWER | NASA POWER Project, https://power.larc.nasa.gov/ . Original dataset metadata and hashes are retained. Values are grid context, not farm observations. |
| NASA SMAP L4 / MODIS | NASA product context; product/source URLs are retained in the frozen corpus and manifest. Different dates, support and processing must be respected. |
| Sentinel-2 context image | Contains modified Copernicus Sentinel data (2025), processed for this research view. Scene, bands, scaling and quality details are in `frontend/public/imagery/context/sentinel-manifest.json`. |
| SoilGrids | ISRIC — World Soil Information; modeled property context. Source references are in the corpus and runtime metadata. |
| Terrain tiles | Mapzen; SRTM, GMTED2010 and 3DEP courtesy USGS; ETOPO1 courtesy NOAA. [Provider attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md). Tile metadata is retained in `frontend/public/terrain/manifest.json`; not every input contributes to every pixel. |
| Online basemap | Esri World Imagery and its listed contributors, credited within the map. External service terms apply. Tiles are requested online, not repackaged as a dataset here. |
| Vietnamese/local references and FAO | Original publishers and authors, exact URLs, locators and source hashes are retained in the corpus/manifests. Raw publications are not distributed in Git; public access alone was not treated as redistribution permission. |
| Space Apps / NASA marks | Used to identify the challenge context. They remain their owners' marks and do not imply endorsement. |
| NeuraX logo | Team identity asset; the transparent-background edit was AI-assisted. |
| Fonts | Be Vietnam Pro via `@fontsource/be-vietnam-pro`; its upstream font license applies. |
| Software packages | React, Vite, FastAPI, NumPy, pandas, scikit-learn, MapLibre and other packages retain their package licenses. Versions are recorded in the dependency manifests. |

The 17 evidence cards are authored bilingual paraphrases with citations. They are not verbatim republications of the source documents, official standards, or expert sign-offs. See [DATA.md](docs/DATA.md) for use and scope.
