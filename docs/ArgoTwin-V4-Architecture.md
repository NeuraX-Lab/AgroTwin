# ArgoTwin v4 — sơ đồ kiến trúc

Bản kiến trúc phục vụ trình bày và demo, đối chiếu ngày 15/11/2026. **Selected v4 = ML v3 seasonal climatology + RAG v4 refined evidence gate + pooled empirical intervals.** Dashboard v4 đã có bản tích hợp local; các ghi chú cũ “chưa nhận UI” không còn mô tả bản đang chạy.

Mở file bằng trình xem Markdown hỗ trợ **Mermaid** như GitHub hoặc Markdown Preview có Mermaid. Các sơ đồ là cấu trúc logic, không ngụ ý hệ thống đã được kiểm chứng canh tác tại ruộng.

## 1. Tổng thể DATA → AI → UI

```mermaid
flowchart LR
    NASA["NASA POWER<br/>Mưa, nhiệt độ, độ ẩm"] --> QA["Kiểm dữ liệu<br/>Đơn vị, lịch, ngày thiếu"]
    QA --> MONTH["Dữ liệu tháng"]
    MONTH --> CLIMATE["Khối khí hậu<br/>Seasonal mean climatology"]
    CAL["Sai số calibration<br/>2015–2017"] --> BAND["Khoảng bất định thực nghiệm"]
    CLIMATE --> FORECAST["6 kết quả<br/>3 biến × horizon 1/3 tháng"]
    BAND --> FORECAST

    LOCAL["Tài liệu nông học có nguồn"] --> CARDS["17 thẻ bằng chứng<br/>Anh / Việt"]
    CARDS --> RAG["Khối bằng chứng<br/>Hybrid retrieval + evidence gates"]
    QUESTION["Câu hỏi người dùng"] --> RAG

    FARM["Điều kiện ruộng khai báo"] --> RULES["Kiểm ràng buộc"]
    FORECAST --> RULES
    RULES --> API["Selected v4 API"]
    RAG --> API
    API --> UI["Dashboard<br/>Kết quả, điều kiện thiếu, citation"]
```

**Câu giải thích:** Dữ liệu NASA cung cấp bối cảnh khí hậu; tài liệu địa phương cung cấp bằng chứng; điều kiện ruộng giúp kiểm xung đột trước khi hiển thị kết quả.

## 2. DATA và phương pháp khí hậu

```mermaid
flowchart TD
    RAW["POWER daily<br/>1984-01 đến 2026-10"] --> CHECK["Kiểm đơn vị, giá trị thiếu,<br/>duplicate và lịch ngày"]
    CHECK --> COMPLETE{"Tháng đủ dữ liệu?"}
    COMPLETE -->|"Không"| MISSING["Giữ trạng thái thiếu<br/>Không đổi missing thành 0"]
    COMPLETE -->|"Có"| AGG["Mưa: tổng tháng<br/>Nhiệt / RH: trung bình tháng"]
    AGG --> FIT["Fit mean climatology<br/>Trung bình các tháng cùng mùa trong train"]
    FIT --> POINT["Ước tính trung tâm"]
    RES["Residuals calibration 2015–2017"] --> RADIUS["Pooled empirical radius"]
    POINT --> INTERVAL["Ước tính ± radius<br/>Mưa có cận dưới tối thiểu 0"]
    RADIUS --> INTERVAL
    INTERVAL --> OUT["Target, unit, origin, horizon,<br/>data cutoff, lower, upper"]
```

- Đây là baseline thống kê đã fit, không phải neural network.
- Ba target: mưa tháng, nhiệt độ trung bình, độ ẩm không khí trung bình; mỗi target có horizon 1 và 3 tháng.
- Snapshot đến 10/2026: origin 11/2026, tháng đích 12/2026 và 02/2027 do availability buffer. Đây không phải dự báo từng ngày.
- Ví dụ mưa tháng 12/2026: **33,68 mm**, khoảng thực nghiệm **0–93,27 mm**. Radius khoảng 59,59 mm; cận âm được chặn ở 0.
- Nominal coverage 80% là mục tiêu; coverage mưa trên diagnostic lịch sử đạt khoảng 67,7%. Diagnostic đã được dùng trước đó, không phải blind test độc lập; không có bảo đảm coverage cho từng dự báo.

## 3. RAG — từ câu hỏi tới câu trả lời có nguồn

```mermaid
flowchart TD
    Q["Câu hỏi Anh / Việt"] --> SEARCH["Hybrid retrieval<br/>BM25 + character TF-IDF"]
    C["17 bilingual evidence cards<br/>Source ID, URL, locator, SHA256"] --> SEARCH
    SEARCH --> TOP["Lấy top 3<br/>Card top 1 đi qua gate"]
    TOP --> SUPPORT{"Đủ hỗ trợ câu hỏi?<br/>Không đòi số đo chưa có?"}
    SUPPORT -->|"Không"| REFUSE["insufficient_evidence<br/>Không tạo câu trả lời khẳng định"]
    SUPPORT -->|"Có"| HASH{"Source bytes có sẵn<br/>và đúng SHA256?"}
    HASH -->|"Không"| REFUSE
    HASH -->|"Có"| EXTRACT["Constrained extractive answer<br/>Trả nội dung card đã biên soạn"]
    EXTRACT --> CITED["Câu trả lời + citation<br/>Source ID, URL, locator, hash"]
```

**Hybrid search chỉ là bước truy xuất**, chưa phải toàn bộ RAG. Sau đó còn kiểm mức hỗ trợ, kiểm nguồn và ghép câu trả lời có trích dẫn hoặc từ chối. Bản này không fine-tune LLM và không dùng LLM tự tạo số liệu nông học. Hash xác nhận file đúng bản đã pin, không tự chứng minh diễn giải nông học đúng.

## 4. Quyết định luân canh và ví dụ demo

```mermaid
flowchart LR
    INPUT["Input khai báo<br/>Thoát nước kém"] --> CONFLICT["Kiểm ràng buộc cây cạn"]
    GUIDE["Quy trình đậu xanh<br/>Tránh nơi bị úng"] --> CONFLICT
    CONFLICT --> BLOCK["R2: đậu xanh bị chặn"]
    BLOCK --> WHY["Hiện lý do,<br/>bằng chứng và thông tin còn thiếu"]
```

```mermaid
flowchart TD
    FARM["Cây hiện tại, nguồn tưới, drainage,<br/>lịch vụ, đất và nước"] --> CHECK["Kiểm theo reference và ràng buộc"]
    CHECK --> BAD{"Có xung đột đã khai báo?"}
    BAD -->|"Có"| BLOCKED["blocked"]
    BAD -->|"Không"| ENOUGH{"Đủ thông tin để xét điều kiện?"}
    ENOUGH -->|"Chưa"| NEED["needs_information"]
    ENOUGH -->|"Đủ trong phạm vi reference"| REF["conditional_reference"]
    BLOCKED --> DISPLAY["Hiển thị phương án và giải thích"]
    NEED --> DISPLAY
    REF --> DISPLAY
```

R0/R1/R2 lần lượt là lúa–lúa–lúa, lúa–bắp non–lúa, lúa–đậu xanh–lúa. Các trạng thái trên là output prototype; rank, score và success probability vẫn null, domain approval chưa có. Không suy ra cây tốt nhất hoặc mức tăng năng suất.

## 5. Dashboard, hai dịch vụ backend và ESP32

```mermaid
flowchart LR
    USER["Người trình diễn / người dùng"] --> BROWSER["Dashboard trong browser<br/>127.0.0.1:5174"]
    BROWSER -->|"/api/v4/*"| V4["Selected AI v4<br/>127.0.0.1:8184"]
    V4 --> MODEL["6 model artifacts<br/>v3 climatology"]
    V4 --> EVIDENCE["RAG v4<br/>Cards và source cache"]
    BROWSER -->|"/api/* qua proxy"| A1["A1/H1 service<br/>127.0.0.1:8000"]
    A1 --> CONTEXT["Geometry, NASA history,<br/>catalog và telemetry contracts"]
    BOARD["ESP32-S3<br/>USB serial"] -->|"User chọn cổng, baud 115200"| SERIAL["Web Serial + parser<br/>trong browser"]
    SERIAL --> BROWSER
    BROWSER --> DRAFT["localStorage<br/>Input, run, output, citations"]
```

Hai backend có vai trò khác nhau: A1/H1 giữ context và hợp đồng telemetry; selected v4 xử lý inference và evidence. Luồng demo v4 không cần dịch vụ v2. Các cổng đều bind local.

Số đo ESP32 được hiển thị riêng: nhiệt độ, %RH, raw soil ADC và thời điểm nhận. Raw ADC không tự thành phần trăm ẩm đất đã hiệu chuẩn; dữ liệu bench/thiếu device time không được mặc định đủ điều kiện đưa vào AI. Không có đường nối trực tiếp từ sensor sang crop score trong sơ đồ này.

## 6. Một lần bấm phân tích v4

```mermaid
sequenceDiagram
    actor U as Người dùng
    participant UI as Dashboard
    participant API as API v4
    participant ML as Climate models
    participant RAG as Retrieval và gates
    U->>UI: Nhập điều kiện và câu hỏi
    UI->>API: POST /api/v4/analyze
    API->>ML: Chạy 6 predictions từ artifact đã fit
    ML-->>API: Forecasts, bounds, metadata
    API->>RAG: Truy xuất và kiểm bằng chứng
    RAG-->>API: Cited answer hoặc abstention
    Note over API: Kiểm constraints và output contract
    API-->>UI: Run ID v4-*, forecasts, options, citations, warnings
    UI-->>U: Hiển thị kết quả và thông tin thiếu
    opt Người dùng lưu bản nháp
        UI->>UI: Ghi và đọc lại localStorage
    end
```

Mỗi request phân tích chạy inference từ model hiện có, **không train lại model**. Mở bản nháp đã lưu không tự gọi phân tích mới. Run ID của request khác selection ID `research-*` của bộ artifact.

## Nguồn đối chiếu

- `neurax-docs/nasa-space-apps-2026/selected-system-v4/01-AI-ARCHITECTURE.md`: ML, RAG, constraints và uncertainty; ghi chú UI pending trong tài liệu cũ đã được thay bằng trạng thái tích hợp local ở sơ đồ trên.
- `neurax-fieldshift-lab/integration/README-v4.md`: cập nhật dashboard integration, fresh inference, service identity và contract.
- `work/agrotwin-v4-integration/docs/integration/V4_ESP32_INTEGRATION_REPORT.md`: A1/H1, backend v4, persistence và hardware gates.
- `work/agrotwin-v4-integration/frontend/vite.config.ts`: proxy thực tế giữa 5174, 8184 và 8000.
- `neurax-fieldshift-lab/reports/v3/evidence/bands-frozen.json` và API forecast đã lưu: radius, calibration và ví dụ khoảng mưa.

Giới hạn còn lại: một AOI chưa survey độc lập, coarse climate grid, historical diagnostic đã lộ, uncertainty chưa được bảo đảm, chưa có agronomic sign-off hoặc farmer trial trong bằng chứng dùng ở đây.
