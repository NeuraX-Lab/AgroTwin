# Corpus and interface data

Manifest: `../v3/evidence/data-manifest.json`; corpus: `../v3/evidence/corpus-frozen.json`. Exact 17-card identity is checked at construction. Cards remain analyst paraphrases, not verbatim source quotes. Source hashes authenticate cached bytes, not the correctness of every paraphrase/locator. Independent citation-page and agronomic interpretation review is still absent.

Query tokenization removes stop words, preserves Vietnamese accent normalization inherited from v2, and uses a few corpus-derived aliases (e.g. crop coefficient -> Kc, reference evapotranspiration -> ET0). The first attempt falsely abstained from the exposed FAO-formula regression due to terminology. Those negative results remain in `evidence/`. The refined tokenizer and results are in `evidence/refined/`; refinement used development and previously exposed regression only. New final questions remained unused.

No source file is modified during fault injection. Tests redirect a copied source registry entry to a temporary corrupted file; byte verification is repeated per answer so a later replacement is detected. Weather is still NASA regional estimates; LOCAL is contextual evidence, not new training labels. Farm information remains unverified self-report.
