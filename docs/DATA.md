# Data and evidence roles

| Layer | Purpose | Limits |
|---|---|---|
| NASA POWER | Historical monthly rainfall, air temperature and RH for the six climate tasks | Coarse regional grid; not a farm station or a field observation |
| NASA SMAP L4 | Historical regional soil-moisture context | Different spatial/temporal support; not a direct field moisture sensor |
| NASA MODIS / Sentinel-2 | Vegetation/optical and map context | Not a validated crop classifier, yield model or suitability label |
| SoilGrids | Modeled soil context | Depth, quantiles and uncertainty matter; not a soil laboratory result |
| Vietnamese/local agricultural publications | Crop management requirements, scope and rotation evidence | Historical/reference conditions require local checking; not current plot measurements |
| User farm inputs | Drainage, irrigation, crop, dates, salinity and other conditions | Self-reported and unverified; scenarios are labeled accordingly |
| Optional hardware | Timestamped sensor telemetry with provenance | No agronomic calibration or outcome validation implied |

The frozen climate table contains **514 calendar months, January 1984–October 2026**, at latitude **10.479098**, longitude **106.021621**. “Mỹ Thành” is the retained study label; it is not an independently surveyed field boundary. Monthly rainfall is a total; temperature and RH are means. Missing daily observations require explicit coverage checks and must not silently become zeros.

The **17 bilingual cards are analyst-authored evidence summaries**, not 17 separate training datasets, regulatory standards, or expert approvals. NASA provides environmental context; local references describe crop requirements and applicability limits. Combining them does not create field-level agronomic labels.

Inspect the [frozen corpus](../backend/reports/v3/evidence/corpus-frozen.json), [original data manifest](../backend/reports/v3/evidence/data-manifest.json) and [runtime acquisition manifest](../backend/runtime-manifest.json). Each runtime entry preserves its original path, byte count and SHA-256. External publications carry their original source links and are downloaded locally rather than redistributed in Git.

Processed aggregates, compact climate statistics and retrieval metadata are included for reproducibility. Broad exploratory datasets, raw publication caches, private working notes, virtual environments and unrelated experiments are excluded from this submission. NASA POWER information: https://power.larc.nasa.gov/ . Full source URLs and locators are in the corpus and manifests above.
