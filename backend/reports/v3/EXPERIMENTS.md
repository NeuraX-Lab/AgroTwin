# Experiments and reproduction

Protocol fixed before fitting: `config/v3-protocol.json`. CPU single thread, no cloud/GPU, paid cost zero. Real doctor output: MX570 A 2 GB VRAM, approximately 15.7 GB RAM; roughly 1.8 GB free at audit. Reuse `.venv-geo-eda` and pinned `requirements-v2.txt` (Python/runtime versions in `evidence/environment.json`). All fits, seeds and runtime counts are in the frozen ledger; deterministic Ridge/climatology do not vary by seed. Frozen HGB uses existing seed 42, without stochastic subsampling; it is a comparator, not a new deep training campaign.

From the lab root, cached original data required:

```powershell
.venv-geo-eda/Scripts/python.exe -X utf8 scripts/research_v3.py freeze
.venv-geo-eda/Scripts/python.exe -X utf8 scripts/research_v3.py develop
.venv-geo-eda/Scripts/python.exe -X utf8 scripts/audit_research.py
.venv-geo-eda/Scripts/python.exe -X utf8 scripts/research_v3.py calibrate
.venv-geo-eda/Scripts/python.exe -X utf8 scripts/research_v3.py verify
.venv-geo-eda/Scripts/python.exe -X utf8 -m pytest tests/test_research_v3.py tests/test_v2.py tests/test_pipeline.py -q
```

Default selection is immutable: repeated develop refuses overwrite. For reruns choose `--out runs/research-v3-replay` on freeze/develop/calibrate/verify; replay reports are written inside the chosen run folder and do not overwrite canonical report snapshots. Nothing downloads data. Raw bytes/learned weights stay outside Git; manifests and aggregate metric evidence are tracked. `audit_research.py` redirects exact v1 execution to `runs/research-v3/audit/v1-exact`, so original v1/v2 runs are preserved. V4/v5 develop also support `--out` for immutable replays.

All 60 method/task results and five yearly folds are in `evidence/*-development.json`; raw per-month prediction CSVs are in `runs/research-v3/<task>/*-dev.csv`. Read `evidence/development-summary.json` for decisions. The largest apparent temperature/RH gains fail the yearly confidence/robustness gate. Recency/anomaly candidates are retained as negative findings.

Operational model files: `runs/research-v3/<target>-h<h>/model.joblib`; held-out diagnostics use separately refitted models, never these full-history operational artifacts. Radius calibration is based on 2015–2017 only, after freezing point selection. Future evaluation appears in the final version report; no final diagnostic is used to produce successors.
