# ArgoTwin — English script for all seven slides

Based on the currently visible slides, including the dashboard screenshot on slide 3. Target: 120 seconds speaking after the separate 30-second video. Read only the paragraphs, not the headings or cues. Timing is a rehearsal target; allow for spoken numbers, technical names and speaker handoffs.

| Speaker | Slides | Speaking time |
|---|---|---|
| Ngọc Bích | 1–3 | 0:00–0:35 |
| Việt | 4–5 | 0:35–1:35 |
| Hưng | 6–7 | 1:35–2:00 |

This full-team version shortens Việt’s earlier standalone 75-second script so Hưng has time to cover validation and next steps.

## Slide 1 — Ngọc Bích — 0:00–0:08

We are NeuraX. ArgoTwin addresses Field Shift: using NASA data to support crop-rotation decisions.

## Slide 2 — Ngọc Bích — 0:08–0:20

After rice, what should a farmer grow next? Rainfall matters, but drainage, soil and water conditions also determine which options deserve consideration.

## Slide 3 — Ngọc Bích — 0:20–0:35

ArgoTwin presents three reference rotations: rice only, rice with baby corn, and rice with mungbean. The dashboard brings these options together. Việt will explain the data.

## Slide 4 — Việt — 0:35–1:05

NASA POWER supplies rainfall, temperature and humidity across 514 months. We check daily data, then fit same-month historical averages. The chart shows regional rainfall history. For December, the estimate is 33.68 millimetres, with an empirical uncertainty range of zero to 93.27. Nominal coverage is 80 percent; diagnostic rainfall coverage was 67.7 percent.

## Slide 5 — Việt — 1:05–1:35

The climate block produces estimates and ranges. The evidence block searches seventeen bilingual cards using BM25 and character TF-IDF, then checks support and source hashes. It returns cited content or refuses unsupported questions. Farm constraints feed the decision layer. Here, declared poor drainage conflicts with the mungbean guideline, so mungbean is blocked. Hưng will present validation.

## Slide 6 — Hưng — 1:35–1:51

Our small evaluation declined six of eight unsupported questions. Rainfall MAE was 62.74 millimetres per month on a reused diagnostic. Field benefits remain unmeasured.

## Slide 7 — Hưng — 1:51–2:00

Next, we will complete dashboard integration, validate local inputs and agronomic rules, then run a small usability pilot. Thank you.

## Rehearsal cues

- Video runs before the speaking clock above: 30 seconds video + 120 seconds speech = 2:30 total.
- Slide 4: point to the historical rainfall chart, then the estimate/range. “Coverage” is not “accuracy.”
- Slide 5: point to both branches, then the poor-drainage example. Do not simulate a click; these are static slides.
- Slide 6: “reused diagnostic” matters. Do not call it an independent test or claim measured savings.
- If behind time, omit “The chart shows regional rainfall history” and “Farm constraints feed the decision layer.” Keep the results and their qualifications.
- Slide 7 says integration is a next step even though slide 3 already shows an integrated prototype. “Complete dashboard integration” means completing that work, not claiming there is no integration today. The team should update the roadmap if integration is considered fully finished.
