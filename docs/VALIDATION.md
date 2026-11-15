# Validation and limits

The selected submission is v4: v3 frozen climatology + v4 refined RAG gate + pooled empirical intervals. Historical evaluation below is distinct from software checks of this consolidated repository.

| Historical diagnostic | Recorded result | Interpretation |
|---|---|---|
| Climate point model | All six tasks retained climatology | Complex candidates did not pass the promotion gate |
| Rainfall MAE, 2018–2025 | 62.7357 mm/month, 96 months per task | Reused retrospective diagnostic; not an untouched test |
| Rainfall interval coverage | 67.71% for nominal 80% intervals | Empirical range; no coverage guarantee under temporal shift |
| Equal-task MAE ratio versus frozen v2 | Selected ML was 4.85% worse | No ML superiority claim |
| RAG final questions | 16 authored questions: 8 answerable, 8 unanswerable | Small bounded set, not broad user or expert validation |
| Answerable evidence agreement | 8/8 | Correct reference card within this set |
| Correct abstention | 6/8, versus 1/8 for v2 | Two unsupported questions still escaped refusal |

Known RAG failures include rice-futures margin and GMO baby-corn questions. Lexical support and source hashes do not prove semantic entailment. The source can match its hash and still be outdated or unsuitable for a plot.

Development used five historical years; calibration used 2015–2017; the final diagnostic used 2018–2025. Those final labels had already been exposed in project research. Historical data vintages were not independently verified; there is no geographic holdout at a single AOI. The calibration timing, reuse and dependence caveats are retained in the original reports.

For the worked December rainfall example, **33.68 mm** is the climatological point estimate. **0–93.27 mm** is the clipped empirical prediction range produced by the saved residual radius. It is not the minimum/maximum rainfall observed at this farm, a guaranteed 80% interval, or uncertainty in a field rain gauge.

The product does not establish crop suitability, yield/profit improvement, irrigation savings, calibrated probabilities or independent agronomic sign-off. Score/rank/probability remain null and `domain_approved` remains false. Optional bench hardware evidence from prior sessions is historical; a board must be connected and verified again before claiming a current physical demo.

Original evidence: [ML diagnostic](../backend/reports/v3/evidence/final-diagnostic.json), [ML protocol](../backend/reports/v3/VALIDATION.md), [RAG final](../backend/reports/v4/evidence/refined/final.json), [RAG protocol](../backend/reports/v4/VALIDATION.md). Current packaging checks: [SUBMISSION-CHECKS.md](SUBMISSION-CHECKS.md).
