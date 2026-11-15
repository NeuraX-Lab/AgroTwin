# V4 experiments

Development comprises the original six v2 development questions plus thirteen authored cases (11 answerable, 8 unanswerable total). Original v2 final 24 is explicitly an exposed regression guard, not a fresh test. Threshold search: .4/.55/.7, fixed original retriever/corpus. Promote only with no regression on the exposed answerable/abstention checks. Refined .4 selected; no final-label tuning.

Results: v2 baseline correct abstention 0/8, positive evidence agreement 11/11; refined gate 8/8 and 11/11. Original exposed regression remains 16/16 positive evidence and 8/8 abstentions. No-sufficiency ablation returns to 0/8; no-integrity ablation has no effect on ordinary clean cases but fails the simulated source-integrity check. Byte hashes authenticate provenance; literal rendering is supported by the analyst card. Neither proves full semantic faithfulness to the original PDF or field suitability.

Failed first pass remains in `evidence/development-*.json`, `evidence/exposed-regression-*.json` and the first selection ledger: .4 had 15/16 positives on exposed regression. It was not deployed. Refined results/ledger use `runs/research-v4-refined/` and `evidence/refined/` so no failed experiment is erased.

```powershell
# Requires v3 frozen artifacts. Refuses overwriting an existing refined ledger.
.venv-geo-eda/Scripts/python.exe -X utf8 scripts/research_v4.py develop
.venv-geo-eda/Scripts/python.exe -X utf8 -m pytest tests/test_research_v4.py -q
.venv-geo-eda/Scripts/python.exe -m uvicorn scripts.research_runtime:app --host 127.0.0.1 --port 8183
```

Eight v4 tests pass: source substitution/change-after-first-answer, unit/region/date/NaN/bounds validation, extreme/missing forecast invariance, incompatible dates, existing alias/API validation, and changed ML-input checksum rejection. Same Starlette/httpx deprecation warning as v2; no test failure.

Final paraphrases were evaluated after the version chain freeze `9214d35`: 8/8 positive evidence agreement and retrieval recall, correct abstention 6/8 versus v2 1/8. Two negative questions are falsely supported (rice futures margin, baby-corn genetic modification safety); no policy patch was made from these outcomes. `evidence/refined/final.json` retains all responses. Complete replay reproduced the chosen threshold and development decisions. Runtime/memory/latency measurements are in `../research-final/evidence/verification.json`.
