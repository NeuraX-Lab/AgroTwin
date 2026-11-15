# Free public deployment with Vercel CLI

The public demo combines the production frontend and the **same selected v4 Python engine** in one Vercel Hobby project. The build restores the frozen runtime and verifies source hashes; it does not fit or promote a model.

**Live dashboard:** https://agrotwin-six.vercel.app/w/my-thanh/farmer

**Health:** https://agrotwin-six.vercel.app/api/health

```powershell
npx vercel@65.16.0 login
npx vercel@65.16.0 deploy --prod --yes --project agrotwin --create-if-missing --scope YOUR_HOBBY_SCOPE
```

Choose a workspace whose billing plan is **Hobby**. The deployment uses no paid database, AI gateway, GPU or persistent disk. Vercel's [Hobby plan](https://vercel.com/docs/plans/hobby) is free within its usage limits; exceeding a limit can pause service. This is a research/demo deployment, not an availability guarantee.

## Build and routing

`pyproject.toml` declares the Python 3.12 runtime dependencies and `main:app` entrypoint. Vercel prioritizes that dependency manifest for this deployment. `scripts/build_host.py` runs the source-verifying bootstrap and the frontend production build. The original `requirements.txt` remains the fuller local development/test environment.

FastAPI promotes `frontend/dist` to CDN assets with navigation fallback to `index.html`. `/api/v4/*` executes the existing selected model/RAG endpoints. `/api/v1/analysis` and `/api/v1/h1/ingest` use the original A1/H1 implementation with a temporary directory scoped to each request. The adapter checks request origin and size and marks API results `no-store`.

The public adapter does not expose shared server run history. Save/reopen remains browser storage. H1 aggregation on the public demo covers the submitted batch only; history and duplicate detection across different requests are not retained. Use the local launcher for a persistent local bench session.

External publications are downloaded from their publishers during build into private function resources and checked against the frozen manifest. They are never mounted as static files or served as PDF downloads. The frontend build is the only directory promoted to the CDN.

## Check a deployment

Request `/api/health`: it should identify v4, 6 models, and 17/17 verified evidence cards after a full build. Open `/w/my-thanh/farmer`, submit a comparison and inspect a fresh run ID, six forecasts, uncertainty and a NASA citation. Test an unsupported field question and confirm refusal.

Production checks can reuse the browser tests:

```powershell
cd frontend
$env:AGROTWIN_BASE_URL='https://YOUR-PRODUCTION-ALIAS.vercel.app'
npx playwright test tests/e2e/live-v4.spec.ts --reporter=list
```

Use the production alias for a public submission. Vercel may require login on the deployment-specific inspection/preview URLs. See [FastAPI deployment documentation](https://vercel.com/docs/frameworks/backend/fastapi) for current platform behavior.
