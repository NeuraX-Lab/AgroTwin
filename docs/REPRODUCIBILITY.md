# Reproducing the selected demo

1. Install the pinned Python and frontend dependencies from the README.
2. Run `python scripts/bootstrap.py --offline` from the repository root. This restores included resources to ignored runtime paths under `backend/` and checks their exact bytes. Six saved 1.4 KB climatology artifacts are included as a bounded reproducibility exception; no unrelated model weights are distributed. Only load the trusted artifacts that match the checked manifest.
3. For full evidence availability, run `python scripts/bootstrap.py`. It downloads nine external publications/pages, approximately 77 MB total, from their original publishers. Original rights apply. A network failure or changed source is reported; it is never accepted under a new hash automatically.
4. If you already have an authorized exact local research checkout, use `python scripts/bootstrap.py --cache /path/to/neurax-fieldshift-lab`. This reads matching paths, checks their hashes and leaves that checkout unchanged.
5. Run `python scripts/verify.py`, then `python scripts/dev.py`. The launcher uses the current Python executable and only the source in this repository. It binds all services to `127.0.0.1` and refuses occupied ports.

## Missing or changed sources

Offline mode deliberately leaves external publications unavailable. The model estimates, NASA context, dashboard and three reference rotations can still be inspected. Questions requiring a missing publication must abstain. `verify.py` reports how many of the 17 source cards are verified. A missing publication is not a reason to bypass the integrity gate.

For a changed publisher page, obtain the exact original version through an authorized archive, put it at the path listed in `backend/runtime-manifest.json`, and rerun bootstrap. The script refuses to overwrite an existing file with different bytes. Remove or rename your own incorrect local copy manually before retrying. Do not edit the manifest just to make a failed check pass.

## A short demo

Open `/w/my-thanh/farmer`. Show the three reference rotations and the source/uncertainty context. Open farm conditions, choose a planting window from December 2026 to February 2027 and set drainage to poor. Run the comparison: the constraint gate should block the dryland alternatives instead of inventing a best crop. Ask “T2M là gì?” to inspect a NASA-backed citation, then ask “What is field EC at this plot?” to show refusal for an unmeasured field value. Save and reopen the run to inspect its original identity and provenance.

Map tiles are an online enhancement. Saved NASA context and frozen inference remain separate from a live map request. A hardware demonstration additionally needs a compatible board, a Chromium browser and a user-initiated Web Serial permission grant. Firmware and a physical board are not prerequisites for the software demo.

## Tests

The default CI restores included resources offline, checks source/hash boundaries, runs selected API integration tests and A1 tests, then runs frontend tests, lint and build. The full `backend/tests/test_research_v4.py` suite exercises publication tampering and needs the original downloaded source bytes. No API request or bootstrap command trains a model; some research tests fit tiny temporary models to verify temporal-causality invariants.
