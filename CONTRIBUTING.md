# Contributing

Create a short task branch, keep the selected system pinned to v4, and open a pull request for review. Preserve missing/unknown values, source hashes, uncertainty labels and the distinction between regional data and field observations. Do not add real credentials, raw publication caches, generated runs, environments or unrelated weights to Git.

Use the README verification commands for source changes. Frontend changes should pass tests, lint and production build. Runtime changes should retain the artifact and contract checks and be tested through the real API. Update documentation when behavior or reproducibility changes.

Slide ownership is listed in `presentation/README.md`. Edit only your slide sections when possible; rebuild the portable HTML with `python presentation/build.py` and export/check the seven-page PDF after visual edits.
