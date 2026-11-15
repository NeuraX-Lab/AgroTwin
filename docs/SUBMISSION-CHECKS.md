# Submission packaging checks · 2026-11-15

These checks ran against this consolidated checkout, independently of the earlier research reports.

| Check | Actual result |
|---|---|
| Fresh Python environment | Python 3.11; `pip install -r requirements.txt` completed |
| Fresh frontend installation | `npm ci` completed; Node 24.13.0 emitted an engine warning for jsdom's newer supported Node range; README and CI use the supported range |
| Frozen runtime | 6 artifacts, 514 monthly records, 17 cards; all 17 card sources verified using the exact local research cache; no training during bootstrap/inference |
| Backend tests | **38 passed** in the fresh environment, including API, temporal invariants, source tampering, A1 and H1 contracts |
| Frontend unit tests | **51 passed** in 11 files |
| Frontend lint / production build | Both passed |
| Real browser selected-v4 flow | **5 passed** using the new checkout and alternate local ports 18000 / 18184 / 15174 |
| Presentation | 7 HTML slide sections, all referenced assets present, 7 PDF pages; portable HTML rebuilt from the editable source |
| Publication scan | Distributable files checked for credential patterns, oversized files and generated/raw runtime paths; see `scripts/verify.py` |
| Physical hardware | **NOT_TESTED in this packaging run**; no current physical-board success claim |

A separate clean Git clone restored the included resources with Git line-ending conversion disabled, verifying that the frozen bytes survive cross-platform checkout. Offline mode verified 5/17 source cards and correctly retained all six models. The offline API/A1 subset passed **24 tests**. Full publisher acquisition was also tested independently: all **9 external source files** downloaded from their publishers and matched the frozen sizes/hashes, after using the recorded official MDPI CDN URL for its article.

The five browser checks cover real frozen inference and a fresh run identity; uncertainty and a NASA citation; save/reopen; API outage and mismatched echoed input; unsupported-question refusal; delayed response rejection after input edits; mobile/English UI and serious/critical accessibility checks. They ran in Chromium/Edge through the actual proxy/API path, not a static screenshot alone.

Full source-byte checks used the authorized local source cache. Publisher availability is a separate concern; offline bootstrap intentionally keeps unsupported publication answers unavailable. Research MAE/coverage and the small RAG question-set metrics are historical diagnostics, not new measurements established by these software tests.

Deprecation warnings from matplotlib/pyparsing and FastAPI's legacy httpx test client remain. They did not fail the checks. No claim is made that every legacy E2E test file, every browser, or an internet outage has been retested in this packaging run.

## Public deployment checks · 2026-11-15

Deployed through **Vercel CLI 65.16.0** to the **Hobby** workspace `2uoc-vi3ts-projects`. Production: https://agrotwin-six.vercel.app/w/my-thanh/farmer .

- The public adapter and existing backend tests passed **42 tests** locally.
- All **5 selected-v4 browser tests passed against the live production alias**, including actual six-model inference, citations/refusal, save/reopen, error handling and mobile/English accessibility.
- Anonymous HTTPS requests returned JSON health with `selected_system=v4`, `models=6`, `evidence_verified=17`, `evidence_total=17`; the dashboard navigation returned HTML successfully.
- The cloud build restored and hash-verified every frozen resource and all external source files, then built the production frontend. Python runtime dependencies are explicit in `pyproject.toml`; offline plotting imports are deferred until training is explicitly invoked.
- Public A1/H1 storage is temporary per request. There is no shared server run history; saved browser runs remain local to the browser. No physical board was tested during this deploy.

The first deployment exposed a missing Python dependency declaration and failed invocation; the corrected production build was verified through the real API and browser before publishing its link. Deployment-specific URLs can require Vercel authentication; the production alias above was checked without authentication.
