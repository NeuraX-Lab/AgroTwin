# NeuraX ArgoTwin — Q&A chuyên sâu Anh–Việt

Trả lời câu đầu trong khoảng 10–20 giây; chỉ mở phần giải thích khi giám khảo hỏi tiếp. Bản này dựa trên selected v4, không dùng kết quả v5/v6 để đổi tên hoặc tô đẹp v4. English là câu có thể nói trực tiếp; tiếng Việt giải thích và bổ sung chi tiết kỹ thuật.

## Project và khác biệt

### 1. What exactly does ArgoTwin do?

**EN:** ArgoTwin combines NASA climate context with cited local agricultural references so farmers can explore crop rotations, understand conditions, and see what information is still missing.

**VI:** Hỗ trợ khám phá phương án và điều kiện áp dụng. Ba reference là lúa–lúa–lúa, lúa–bắp non–lúa, lúa–đậu xanh–lúa. Chưa có rank, score, xác suất thành công hay crop winner. Runtime trả `conditional_reference`, `needs_information` hoặc `blocked`, tùy input. Bằng chứng: `integration/v4-overview.example.json`, demo captures.

### 2. Who is the first user?

**EN:** Our initial use case is a rice farmer or agricultural adviser considering a rotation change in a retained Mekong Delta study area. We have not yet validated the workflow with farmers.

**VI:** AOI được gắn nhãn Mỹ Thành/Đồng Tháp theo thông tin team, mã MT-BLOCK-01. Tọa độ giữ lại là 10.479098°N, 106.021621°E; chưa survey hay geocode độc lập. Chưa tuyên bố đã có khách hàng hoặc nghiên cứu nhu cầu người dùng.

### 3. Why is NASA data essential rather than decorative?

**EN:** NASA POWER supplies the historical climate series used to estimate monthly rainfall, temperature and humidity. Those estimates appear in the decision context alongside their uncertainty and limitations.

**VI:** Truy được đường đi POWER daily → kiểm calendar/unit/missing → monthly → climatology/bands → `decision.climate_context`. Bỏ NASA data sẽ mất climate series và các ước tính đó; tài liệu nông học vẫn có thể đọc nhưng không còn cùng bối cảnh khí hậu. Không nói mọi quyết định block là do NASA: trường hợp poor drainage do input ruộng và rule có nguồn.

### 4. What is different from WaterWise or 2Plant?

**EN:** Our focus is conditional rotation exploration with Vietnamese and English evidence, explicit missing field inputs, and refusal when support is insufficient. WaterWise and 2Plant address related irrigation or planting decisions.

**VI:** WaterWise đạt Best Use of Data 2024; 2Plant đạt Galactic Impact 2024. Khác biệt nêu ở đây là phạm vi prototype, không chứng minh NeuraX chính xác hơn hoặc là đội đầu tiên có feature này. Không so trực tiếp metric trên dataset khác nhau. Nguồn và artifact đã xem ở file nghiên cứu.

### 5. Is this a digital twin?

**EN:** The current prototype is a decision-support research system. It does not maintain a calibrated, continuously updated field simulation, so we avoid claiming a validated digital twin.

**VI:** AgroTwin là concept lịch sử. Bản pitch dùng ArgoTwin để tránh gợi khả năng mô phỏng vật lý/can thiệp/yield chưa có. Chưa có đồng hóa cảm biến liên tục cho một ruộng đã hiệu chuẩn.

## NASA DATA và fusion

### 6. Which NASA dataset is actually used in the selected model?

**EN:** NASA POWER daily meteorological data: corrected precipitation, two-metre air temperature, and relative humidity. The retained monthly series runs from January 1984 through October 2026.

**VI:** API metadata ghi v2.10.3. PRECTOTCORR mm/day cộng thành mm/month; T2M °C và RH2M % lấy trung bình tháng. 514 tháng. Tmin/Tmax có trong data context nhưng không biến thành target mới. SMAP/MODIS/Sentinel/SoilGrids từng được audit không đồng nghĩa đều là feature của selected ML.

### 7. Is POWER a satellite image of an individual field?

**EN:** No. POWER meteorology includes MERRA-2 reanalysis on a coarse grid. It provides regional estimates, not a direct measurement of one field’s soil or water conditions.

**VI:** NASA mô tả MERRA-2 trên lưới 0.5° × 0.625°, giá trị đại diện trung bình ô lưới. Xem [NASA POWER methodology](https://power.larc.nasa.gov/docs/methodology/data/sources_meteorology/). Không gọi đây là độ phân giải ruộng, ảnh thời gian thực hoặc trạm mưa tại ruộng. Sản phẩm/biến khác có resolution khác; không áp một số cho toàn bộ nguồn NASA.

### 8. Why not use every satellite listed in the challenge?

**EN:** A source must have a clear role, usable coverage and defensible preprocessing. We selected a climate backbone we could audit, rather than treating every available dataset as a required model input.

**VI:** Một nguồn được đề gợi ý không trở thành bắt buộc. MODIS/SMAP có thể bổ sung context, nhưng độ sâu, scale và thời gian phải rõ. Không join thêm chỉ để tăng số logo dataset. Muốn thêm nguồn phải đánh giá incremental value và leakage.

### 9. How do you prevent missing rain from becoming zero rain?

**EN:** We preserve zero as a valid measurement, convert documented fill values to missing, and require complete calendar coverage before publishing a monthly rainfall total.

**VI:** Kiểm số ngày theo tháng/năm nhuận, duplicate key, thiếu ngày và đơn vị. Tháng thiếu không được cộng ra “tổng đầy đủ”; không âm thầm nội suy target. Dữ liệu gốc giữ nguyên để đối soát. Mốc ngày daily UTC khác ngày địa phương phải giữ metadata.

### 10. How was preprocessing verified?

**EN:** Monthly values were independently recomputed from the retained raw NASA data and matched within floating-point precision. That checks the transformation, not field accuracy.

**VI:** Sai khác lớn nhất được ghi: mưa 5.68×10⁻¹⁴ mm, nhiệt 3.55×10⁻¹⁵ °C, RH 1.42×10⁻¹⁴ điểm %. Manifest v3 có 380 file. “Independent recomputation” là cách tính lại, không phải đã có chữ ký Q1 của Quang Luật. Nguồn: docs `04-DATA-VALIDATION.md`, Lab `reports/v3/evidence/data-manifest.json`.

### 11. How do you combine NASA and local data?

**EN:** We combine them at the decision layer while preserving their scales and provenance. Regional climate estimates provide context; local references define conditions and questions to check at the field.

**VI:** Không ép nghiên cứu Cai Lậy, SoilGrids hoặc trạm tham chiếu thành nhãn đo của MT-BLOCK-01. Join time series theo grain vùng × tháng; card nông học giữ source/scope riêng. Rule cần điều kiện ruộng; unknown vẫn unknown.

### 12. Are the farmer inputs real observations?

**EN:** The demo inputs are declared scenarios. We label them separately from observed source data and from model estimates.

**VI:** Demo `drainage=poor` là input giả định để minh họa cơ chế. Không có người nông dân cụ thể đã xác nhận điều đó. Mục tiêu FARM mô phỏng không đi vào feature khí tượng hay tạo nhãn suitability.

## Model, thời gian và uncertainty

### 13. What model is selected, and why call this AI?

**EN:** The selected climate component is fitted mean seasonal climatology. The system also uses hybrid evidence retrieval and explicit decision constraints. We describe those components directly instead of implying a neural model.

**VI:** Selected system v4 = ML v3 frozen climatology + RAG v4 refined gate + pooled residual intervals. Có statistical fitting, không có neural training trong bản chọn; không fine-tune LLM. “AI” không phải lý do để che baseline.

### 14. Why did you keep a simple baseline?

**EN:** More complex candidates did not pass all our development gates for consistent improvement. Keeping the baseline makes that result transparent and preserves a reproducible comparison.

**VI:** 60 tổ hợp method/task; gồm climatology cửa sổ gần, Ridge seasonal anomaly và reference. Gate gồm giảm MAE ≥3%, thắng ≥3/5 năm, không mùa nào kém >10%, lower bound paired year-block CI95 >0. Không tune thêm sau khi nhìn diagnostic. Các gate chưa được coi là bảo đảm thống kê với mẫu nhỏ.

### 15. What are the targets and horizons?

**EN:** Monthly rainfall, mean air temperature and relative humidity, each at one- and three-month horizons. They support seasonal context, not tomorrow’s weather or daily irrigation scheduling.

**VI:** Sáu task = 3 target × 2 horizon. Buffer availability thêm một tháng: target t, origin t−h, dữ liệu quan trắc tối đa t−h−1. Snapshot through 2026-10, origin 2026-11, target h1 2026-12 và h3 2027-02. Không đổi nhãn thành “next day”.

### 16. How do you avoid future leakage?

**EN:** We use chronological rolling origins, fit transformations inside each training window, and separate calibration from development. Historical data-vintage availability remains a limitation.

**VI:** Refit theo quý, train mở rộng; feature cập nhật tháng, test mutation tương lai không được làm đổi feature/prediction ở origin cũ. Development dùng 2004/2006/2008/2010/2011; calibration 2015–2017. Chưa chứng minh từng vintage thực sự có sẵn ở mọi origin lịch sử. Có caveat availability của cuối calibration 2017 với origin đầu 2018; không giấu điều này bằng buffer trong feature.

### 17. Was the final evaluation an untouched test?

**EN:** No. The 2018–2025 diagnostic had been exposed earlier in the project. We report it as a reused historical diagnostic, not an independent blind test.

**VI:** 96 tháng/task. Mở sau khi chốt cấu hình v3–v5 không làm nhãn đã lộ thành mới. Cần holdout tương lai thật hoặc cohort mới và protocol khóa trước để xác nhận mạnh hơn.

### 18. What are the actual climate errors?

**EN:** On that reused diagnostic, rainfall MAE was about 62.74 millimetres per month, temperature 0.54 degrees Celsius, and humidity 3.63 percentage points. Those are errors against POWER values, not farm measurements.

| Task | V4 MAE | Frozen v2 MAE cùng protocol | V4 interval coverage |
|---|---:|---:|---:|
| Rain h1, mm/month | 62.7357 | 66.2414 | 67.71% |
| Rain h3, mm/month | 62.7357 | 62.1183 | 67.71% |
| Temperature h1, °C | 0.5373 | 0.5435 | 85.42% |
| Temperature h3, °C | 0.5373 | 0.5376 | 85.42% |
| RH h1, percentage points | 3.6331 | 2.9983 | 82.29% |
| RH h3, percentage points | 3.6331 | 3.2034 | 82.29% |

**VI:** Mưa MAE mùa ướt khoảng 90.706 mm, mùa khô 23.578 mm ở h1; bias toàn kỳ khoảng −49.640 mm. Không báo một “accuracy %” chung cho ba đơn vị khác nhau. Source: `reports/v3/evidence/final-diagnostic.json`, `bands-frozen.json`.

### 19. Did v4 outperform v2 overall?

**EN:** Not on the aggregate climate comparison. The equal-weight MAE ratio was about 1.0485, or 4.85% worse than frozen v2 on that diagnostic. The selected system also contains the improved evidence gate.

**VI:** Tỷ số MAE theo task rồi lấy trung bình, không cộng trực tiếp mm với °C. Không dùng việc RAG tốt hơn để nói forecast tốt hơn. Người dùng chọn cấu hình v4 cho demo; v5/v6 mới hơn không tự động thay lựa chọn.

### 20. Does an 80% interval mean 80% accuracy?

**EN:** No. Eighty percent is the nominal interval target. Rainfall coverage was about 67.7% on the diagnostic, so the current bands under-cover rainfall and are not guaranteed.

**VI:** Pooled empirical bands lấy residual calibration 2015–2017 (36 tháng). Assumption stationarity/exchangeability chưa được bảo đảm. `coverage_guaranteed=false`. Không gọi lower–upper là cận chắc chắn hoặc confidence của crop recommendation. Mưa lower bị chặn tại 0 không làm coverage tự đúng.

### 21. Why can h1 and h3 have the same error?

**EN:** A frozen seasonal climatology can return the same estimate for the same target calendar month at different lead times. It does not gain new predictive features merely because the horizon changes.

**VI:** Cùng target season và fitted statistics có thể cho output giống nhau. H1/h3 vẫn giữ separate metadata, origin và availability checks; identical metrics không tự là bug, cũng không là skill đa horizon mạnh.

### 22. What would demonstrate operational forecast skill?

**EN:** A pre-registered prospective evaluation using data available at each forecast date, comparisons with operational baselines, and local observations suited to the decision.

**VI:** Khóa model và metric trước; lưu vintage, issue time, origin, target; ghi forecast trước khi actual đến; đánh giá mùa ướt/khô và extreme. Có gauge địa phương để kiểm transfer từ POWER grid. Không đặt target accuracy/yield đẹp khi chưa có data.

## RAG và kiểm nguồn

### 23. What does your RAG actually generate?

**EN:** It retrieves analyst-written bilingual evidence cards and returns their constrained text with citations. It does not ask an LLM to invent new agronomic advice.

**VI:** 17 cards, BM25 + character TF-IDF, top3; top1 qua gate. Card là paraphrase có nguồn, không phải trích nguyên văn PDF. Không embedding transformer, không LLM fine-tune. Cách gọi đầy đủ là retrieval plus constrained extractive answer assembly.

### 24. Why use BM25 and character TF-IDF?

**EN:** They provide a lightweight, inspectable baseline for English and Vietnamese wording variation. The corpus is small enough that we can audit the retrieved evidence directly.

**VI:** Character n-gram hỗ trợ khác dấu/cách viết. Không khẳng định hiểu semantic hoàn chỉnh. Muốn thay embedding cần frozen benchmark song ngữ, negative/hard-negative, cost/latency và citation checks tương đương.

### 25. What does the evidence gate check?

**EN:** It checks whether the selected card supports enough informative query terms, blocks unsupported current measurements, and verifies the referenced source file against its pinned hash.

**VI:** Refined threshold 0.4 chốt từ development/exposed regression. Lexical heuristic không phải natural-language entailment; có thể bị lừa bởi keyword overlap. Integrity SHA256 kiểm file bytes đúng version; không xác minh tác giả đúng hay lập luận đúng.

### 26. Which local references are actually used?

**EN:** They include a Mekong rice water-management handbook, a mungbean technical protocol, a crop guide for baby corn, and published rotation studies. Each card retains a locator and its geographic scope.

**VI:** Ví dụ `rice-awd-2024` dùng sổ tay MARD 2024, PDF35/printed27 section4. `mungbean-water` dùng protocol IAS ĐBSCL, PDF3 section4.1. `rotation-historic` CTU597, Table4/PDF6. CTU605 cung cấp bối cảnh vật lý đất. Các nghiên cứu lịch sử/địa bàn khác không chứng minh hiệu quả tại ruộng demo. URL/hash đầy đủ trong `reports/v3/evidence/corpus-frozen.json` và assets demo.

### 27. What was the RAG evaluation result?

**EN:** In a sixteen-question analyst-authored final set, the system retained the expected evidence for all eight supported questions and declined six of eight unsupported questions. Two unsupported cases still slipped through.

**VI:** Recall@3 = 100% trên positive 8 câu; correct abstention 75% trên negative 8 câu, v2 chỉ 1/8. Development 19 câu gồm 11 positive/8 negative; không trộn vào final. Hai failure cuối: futures/margin gạo và an toàn GMO bắp non. Sample nhỏ, chưa expert gold hoặc farmer evaluation. Không quảng cáo “100% grounded” từ citation đúng bytes.

### 28. Can the system cite a correct source but answer the wrong question?

**EN:** Yes. Correct source identity does not prove that the source answers the question. That distinction explains the remaining failures and motivates stronger support checks.

**VI:** Chính xác là lý do không lấy literal support/verified citation 100% làm correctness 100%. Cần expert labeling, hard negatives, contradiction/scope evaluation và refusal policy tốt hơn. Hiện không che error bằng đổi dataset hoặc loại câu khó.

### 29. What if a source file is missing or changed?

**EN:** The answer must decline if its required source bytes cannot be verified. The system exposes partial readiness rather than silently substituting a different file.

**VI:** `/status` báo verified_cards/total_cards. Trước capture hôm nay là 17/17. Missing/sai hash phải abstain cho evidence đó; thiếu model/data registry có thể 503. Hash không thay thế kiểm license khi chia sẻ PDF gốc.

## Decision và demo

### 30. Why does poor drainage block mungbean?

**EN:** The retained mungbean protocol advises avoiding waterlogged sites. When the user declares poor drainage, the prototype flags that conflict and blocks that reference option pending local review.

**VI:** Đây là cách triển khai rule từ evidence, chưa domain-approved hard agronomic threshold. Input poor là scenario, không phải đo. API capture cũng block bắp non; nói về đậu xanh để demo gọn. Rice vẫn needs_information, không được suy “lúa chắc chắn tốt”.

### 31. What happens when all field inputs are unknown?

**EN:** The system presents references and missing information, while leaving ranks, scores and success probabilities empty. Unknown conditions do not become an approval.

**VI:** Cần cây/vụ trước, lịch trồng/thu cuối, nguồn tưới, drainage, pH có method/depth/date, salinity/acid-sulfate khi liên quan. Không tự sinh các chỉ số này từ ảnh quang học hoặc lượng mưa tháng.

### 32. Is the HTML demo a live dashboard?

**EN:** The deck is static. Slide five shows a worked example from a real saved v4 API response; slide three reserves space for the latest dashboard screenshot. No model request or interface interaction runs inside the slides.

**VI:** API đã được gọi thật ngày 15/11, run `research-c94396cf86be`. Deck hiện chỉ hiển thị worked example tĩnh về poor drainage; output gốc giữ ở JSON để truy bằng chứng. UI mới của Hưng chưa fetch hoặc tích hợp; phần screenshot trên slide 3 ghi rõ placeholder.

### 33. What if the internet or backend fails on stage?

**EN:** The deck and recorded API examples run locally. We can still show the source locator, the decision state and the missing inputs without a network connection.

**VI:** Toàn bộ JS/CSS/logo/data cần cho deck nằm cùng folder; không CDN. Source text là card có citation, mở PDF URL cần mạng. Không biến replay thành live bằng bỏ nhãn. Browser Print xuất 7 trang khi cần, nhưng bản nộp phải kiểm format platform hiện hành.

### 34. Is hardware required or already validated?

**EN:** Hardware is an optional integration path. This pitch does not claim a calibrated live sensor or use a sensor demonstration as validation of satellite data.

**VI:** An sở hữu embedded; Quang Luật hỗ trợ QA. Point sensor khác grid vùng. Nếu team gắn hardware thực thì phải ghi timestamp, unit, calibration, live/replay, disconnect state và phạm vi đo. Chưa có các log đó trong bằng chứng dùng cho bộ pitch này.

## Impact, triển khai và câu hỏi khó

### 35. How much water or money will farmers save?

**EN:** We have not measured water savings, yield or profit. Our immediate objective is to improve the evidence available for a rotation discussion and make missing checks visible.

**VI:** Mục tiêu pilot đề xuất: người dùng tìm được điều kiện và nguồn đúng, hiểu warning, nhận ra missing input, thời gian hoàn thành task và tỷ lệ chọn phương án có conflict. Đo lợi ích ruộng phải có thiết kế can thiệp/đối chứng thích hợp và thời gian theo vụ; không lấy bài nghiên cứu khác làm kết quả team.

### 36. What are the most serious current limitations?

**EN:** Coarse climate data for one retained area, a small evidence corpus, reused historical diagnostics, imperfect refusal, and no independent agronomic sign-off or farmer trial.

**VI:** Mưa bias/coverage còn yếu, vintage chưa verified, timing caveat calibration, soil/drainage thực unknown. Tên nguồn có thật không giúp vượt các giới hạn này. Đây là lý do dùng conditional reference và giữ người nông dân/chuyên gia trong vòng quyết định.

### 37. What is the next experiment?

**EN:** First verify local field conditions and obtain agronomic review. Then lock a prospective evaluation and test whether farmers can understand and use the workflow correctly.

**VI:** Bích review domain/K1; Quang Luật kiểm metric/Q1 độc lập; kiểm tọa độ, drainage, EC/pH theo protocol; freeze model/bands và thu actual mới. Hưng/Hiếu ghép UI mới sau khi source được cập nhật. Mỗi bước có owner, acceptance và fallback; không hứa thời hạn hay farmer access chưa xác nhận.

### 38. How would you scale beyond this region?

**EN:** Each region needs its own data-quality checks, applicable crop evidence, language review and evaluation. A global data API does not establish local agronomic validity.

**VI:** Multi-AOI geographic holdout; evidence scope và soil/water checks; human review. Không copy thresholds ĐBSCL cho vùng khác. Kiểm uncertainty theo climate regime và coverage/cost trước deploy.

### 39. What is deployed, and is it secure for public use?

**EN:** We have a local FastAPI research service with versioned responses and explicit error states. Public deployment would require additional authentication, transport security and operational review.

**VI:** `127.0.0.1:8184`; không public bind. API schema `fieldshift-dashboard-1`; reject unknown fields, sai unit/region/date 422; missing artifacts503; forbidden origin403; oversized body413. Adapter TS có sẵn nhưng UI mới chưa build/browser-test. 82 tests là receipt lịch sử, không tuyên bố đã chạy lại toàn bộ suite ở lượt làm pitch.

### 40. Did you build everything during the hackathon, and did you use AI tools?

**EN:** We will disclose reused components, source timestamps and AI assistance accurately. Preparing a pitch does not change when the underlying code or data work was done.

**VI:** Không nói “mọi thứ build trong 48h” nếu git history không chứng minh. Repo ghi cảnh báo organizer về pre-event implementation. Không sửa timestamp/history để đủ điều kiện. Bộ pitch/script/HTML được Codex hỗ trợ tổng hợp, dịch và thiết kế; team cần kiểm rồi ghi disclosure theo form. License bản gốc và quyền truy cập link phải được kiểm riêng trước submission; không tự public repo nghiên cứu.

## Tra cứu bằng chứng khi bị hỏi sâu

| Chủ đề | File nguồn ở Lab `03ca31a` |
|---|---|
| Cấu hình chọn | `config/selected-system.json` |
| Data freeze, lineage | `reports/v3/evidence/data-manifest.json` |
| So model, holdout | `reports/v3/evidence/selection-frozen.json`, `final-diagnostic.json` |
| Calibration/bands | `reports/v3/evidence/bands-frozen.json` |
| Card, locator, hash | `reports/v3/evidence/corpus-frozen.json` |
| RAG failures | `reports/v4/evidence/refined/final.json` |
| API contract, prior validation | `integration/openapi-v4.json`, `v4-http-validation.json` |
| Runtime output mới capture | `slides/assets/demo-unknown.json`, `demo-blocked.json`, `demo-abstain.json`, `runtime-status.json` trong gói pitch |

Docs diễn giải ở `neurax-docs/nasa-space-apps-2026/selected-system-v4/`, commit `64bcff9`. Xem file `03-CLAIMS-SOURCES-AND-RESEARCH.md` để truy link handbook, đối thủ, phạm vi đã xem và điều còn thiếu.
