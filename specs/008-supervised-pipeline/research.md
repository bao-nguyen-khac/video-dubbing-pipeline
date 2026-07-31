# Research: Chế độ quản lý pipeline (008-supervised-pipeline)

**Ngày**: 2026-07-30 | **Plan**: [plan.md](./plan.md)

Không có mục NEEDS CLARIFICATION nào trong Technical Context — spec đã qua
`/speckit-clarify` với 4 câu hỏi chốt và toàn bộ công nghệ đều đã nằm trong
Constitution → Technology Stack. Phần dưới ghi lại các quyết định kỹ thuật rút
ra từ việc đọc code hiện có, để agent thực thi không phải suy luận lại.

---

## 1. Cách "dừng chờ duyệt" — tái dùng dispatch-theo-status

**Decision**: Thêm một status mới `awaiting_review` vào state machine của
`pipeline.py`. Khi job supervised hoàn thành một bước có chốt, `run_pipeline()`
ghi `status="awaiting_review"` + `review_gate="transcript"|"script"` rồi `return`
sớm. "Phê duyệt" = ghi status về bước kế tiếp (`scripting` / `synthesizing`) rồi
gọi lại `web.backend.job_runner.start_job()` với cùng `job_id`.

**Rationale**: `run_pipeline()` (pipeline.py:409–633) đã là một chuỗi
`if job["status"] == "<bước>"` đọc lại `job.json` giữa mỗi bước, và
`retry_job()` (jobs_api.py:265) đã chứng minh cơ chế "ghi status rồi gọi lại
start_job() cùng job_id" hoạt động. Vì vậy:

- FR-005 (không tự chạy tiếp) đúng "miễn phí": `return` sớm, không có timer, không
  có tiến trình nền nào biết tới job đó nữa.
- FR-007 (bền vững qua restart) đúng "miễn phí": status nằm trong `job.json` trên
  đĩa, không có state in-memory.
- Assumption "chờ duyệt là vô hạn" đúng "miễn phí": không có gì hết hạn được.

**Alternatives considered**:

- *Thread chờ trên `threading.Event`*: giữ job trong RAM → mất trắng khi restart
  (vi phạm FR-007), và vẫn chiếm thread (đi ngược FR-021).
- *Hàng đợi/scheduler ngoài (Celery, APScheduler)*: thêm dependency + tiến trình
  nền cho một tính năng vốn chỉ cần một field trong JSON — vi phạm Principle V và
  đi ngược Assumption "tái dùng cơ chế sẵn có" trong spec.

## 2. MỘT status + field gate, không phải hai status

**Decision**: `status="awaiting_review"`, kèm `review_gate ∈ {"transcript",
"script", null}`.

**Rationale**: mã hiện tại phân loại status ở 5 chỗ (`VALID_TRANSITIONS`,
`_STATUS_PROGRESS_MAP`, `find_running_job_id()`, `delete_job()` blocklist,
`StatusBadge`/`JobProgress`). Một status mới = 5 chỗ sửa; hai status mới = nhân
đôi mọi danh sách đó cho cùng một lượng thông tin.

**Alternatives considered**: hai status riêng biệt — loại vì lý do trên; giữ
status cũ (`transcribing`) + thêm cờ `paused` — loại vì
`find_running_job_id()`/`delete_job()` phân loại theo status, cờ phụ sẽ khiến job
chờ duyệt vẫn bị coi là đang xử lý ở mọi chỗ chưa được sửa (bug ngầm).

## 3. ⚠ Bẫy chính: `resegment_by_sentences()` sẽ ghi đè phần sửa ở chốt 1

**Vấn đề**: bước scripting gọi `generate_script()` → `resegment_by_sentences(
transcript_data["segments"], ...)` (router_client.py:349–351). Hàm này
(`sentence_segmenter.py:113`) **dựng lại segment từ mảng `words`**:
`_build_segments()` tạo `text` bằng `"".join(w["word"] for w in chunk)`. Nghĩa là
nếu người dùng chỉ sửa trường `text` của segment mà `words` giữ nguyên, phần sửa
bị **xoá sạch** ở bước scripting — FR-012 sai âm thầm, đúng loại lỗi khó phát
hiện nhất.

**Decision**: với job supervised, chạy resegment **ngay trước khi vào chốt 1**
(cuối bước transcribing) và ghi kết quả ra `jobs/{job_id}/transcript_reviewed.json`
với mảng `words` **đã bị loại bỏ**. File này chính là payload chốt 1 (người dùng
sửa trực tiếp lên nó). Bước scripting sau đó đọc
`artifacts["transcript_reviewed"]` nếu có, thay cho `artifacts["transcript"]`.

Vì `_flatten_words()` trả `None` khi bất kỳ segment nào thiếu `words`
(sentence_segmenter.py:45–57), `resegment_by_sentences()` sẽ **tự trả segments
nguyên trạng** — không cần thêm cờ, không cần sửa `sentence_segmenter.py`, và
phần sửa tay được giữ nguyên byte-for-byte.

**Lợi ích kèm theo**: người dùng review đúng các câu đã cắt theo ranh giới câu
(thứ mà các bước sau thực sự dùng), không phải các mảnh ASR cắt giữa câu. Số lượt
gọi LLM **không tăng** — chỉ dịch chuyển lượt gọi chèn dấu câu từ bước scripting
sang cuối bước transcribing.

**Alternatives considered**:

- *Sửa `text` rồi cũng sửa/xoá `words` từng segment tương ứng*: phải map lại từ →
  mốc thời gian sau khi người dùng đổi chữ, việc bất khả thi trong trường hợp
  tổng quát.
- *Thêm tham số `skip_resegment=True` vào `generate_script()`*: cũng chạy được,
  nhưng khi đó chốt 1 hiển thị mảnh ASR cắt giữa câu (UX tệ hơn) và ta mất luôn
  lợi ích "review đúng thứ sẽ dùng". Loại.
- *Đặt biến môi trường `DISABLE_SENTENCE_RESEGMENT`*: là công tắc toàn cục cho cả
  process, không thể bật riêng cho một job. Loại.

## 4. Payload chốt 2 ghi thẳng vào `script.json`

**Decision**: phần sửa ở chốt 2 được ghi trực tiếp vào
`jobs/{job_id}/script.json` (trường `translated_text` của từng segment), và lần
sửa đầu tiên tạo bản lưu `script_original.json` để còn đối chiếu/audit.

**Rationale**: `script.json` là đầu vào của **cả ba** nhánh hạ nguồn —
`synthesize_segments()` (TTS), `write_srt()`/`burn_subtitles()` (phụ đề mode
`subtitle`), và phụ đề động. Ghi thẳng vào đó là cách duy nhất đảm bảo FR-012
cho mọi nhánh mà không phải sửa từng nhánh. Thêm nữa, `generate_script()` và
`generate_subtitle_script()` đều **return sớm nếu `script.json` đã có `segments`**
(router_client.py:329–334, 398–404) → phần sửa không bị sinh lại đè lên khi
resume. Bản lưu `script_original.json` giữ đúng tinh thần Principle VI (audit lại
được quyết định của bước trước).

**Alternatives considered**: file `script_reviewed.json` riêng — loại vì phải sửa
cả 3 nhánh hạ nguồn để ưu tiên file mới, nhiều chỗ sót hơn.

## 5. Job chờ duyệt không chiếm suất (FR-021)

**Decision**: sửa `find_running_job_id()` (jobs_api.py:65) từ
`status not in ("done", "failed")` thành
`status not in ("done", "failed", "awaiting_review")`.

`delete_job()` (jobs_api.py:333) đã dùng **allowlist ngược** — chỉ chặn khi status
thuộc `("downloading","transcribing","scripting","synthesizing","merging")` —
nên `awaiting_review` **xoá được sẵn**, FR-022 không cần sửa gì. Task tương ứng
chỉ cần một test khẳng định hành vi này, không cần đổi code.

## 6. Chống duyệt hai lần và tranh chấp suất (FR-018, FR-019)

**Decision**: endpoint approve làm theo thứ tự: (1) đọc `job.json`; (2) 409 nếu
`status != "awaiting_review"` — đây chính là cái chặn cú click thứ hai, vì lượt
đầu đã đổi status; (3) 409 nếu `review_gate` trong body không khớp field trong
job (chống tab cũ duyệt sai chốt); (4) 409 nếu `find_running_job_id()` khác
`None`; (5) ghi status bước kế tiếp; (6) `start_job()`. Toàn bộ bước 1–5 chạy
trong một `threading.Lock` cấp module.

**Rationale**: chính status trong `job.json` là cái khoá idempotency — không cần
token/nonce riêng. Cần `Lock` vì `start_job()` chạy pipeline trong thread nền
(job_runner.py:26), nên hai request gần nhau thực sự có thể xen giữa
`read_job()` và `_write_job()`. FR-018 được thoả tự nhiên: bước 5 chưa chạy nên
job vẫn nguyên trạng `awaiting_review` cùng toàn bộ nội dung đã lưu.

## 7. Ràng buộc nội dung khi lưu (FR-013, FR-014)

**Decision**: lúc `PUT` bản sửa, câu có nội dung rỗng/chỉ khoảng trắng bị **loại
khỏi file đã lưu** (không lưu câu rỗng rồi lọc ở bước sau). Nếu sau khi loại mà
không còn câu nào → trả 400 kèm lý do, **không ghi file**.

**Rationale**: loại ngay lúc lưu khiến "nội dung đã lưu" đúng nghĩa là "nội dung
các bước sau dùng" (FR-012) — không có nhánh lọc thứ hai nào để quên. Trả 400
trước khi ghi giữ đúng FR-018-style: job không bị hỏng vì một lượt lưu sai.

## 8. Sinh lại kịch bản ở chốt 2 (FR-020)

**Decision**: endpoint regenerate: xoá `jobs/{job_id}/script.json`, ghi
`status="scripting"`, `review_gate=null`, rồi `start_job()`. Bước scripting chạy
lại từ `transcript_reviewed.json` (lời thoại **đã duyệt**), sinh `script.json`
mới, rồi lại dừng ở chốt 2. Cảnh báo "phần sửa tay sẽ bị ghi đè" là hộp xác nhận
ở frontend trước khi gọi API (FR-020, US4-2). `script_original.json` bị xoá kèm
để lượt sửa tay tiếp theo tạo bản lưu mới đúng với `script.json` mới.

**Rationale**: `generate_script()` return sớm khi `script.json` tồn tại, nên xoá
file là cách duy nhất buộc nó sinh lại — và cũng là cách rẻ nhất, không cần thêm
tham số `force`.

**Ràng buộc test (Constitution VI)**: test cho endpoint này MUST monkeypatch
`script_gen.router_client` (hoặc `start_job`) — không được để test gọi thật
9router.

## 9. Chế độ `download` bỏ qua toàn bộ cơ chế chốt (FR-008)

**Decision**: không cần code mới. Nhánh `script_mode == "download"` trong
`run_pipeline()` (pipeline.py:473–483) chuyển thẳng `downloading → done` và
`sys.exit(0)` trước khi tới bất kỳ chốt nào. Task tương ứng chỉ là một test
khẳng định `supervised=True` + `script_mode="download"` vẫn kết thúc `done`.

## 10. Transcript rỗng ở chốt 1 — quyết định có ý thức

**Decision**: chốt 1 **vẫn dừng** và hiển thị rõ "không có câu nào" (spec, Edge
Cases). Người dùng có 2 lựa chọn: xoá job, hoặc bấm phê duyệt. Nếu bấm phê duyệt,
bước scripting sẽ dừng job ở `failed` với message đã có sẵn và đọc được:
*"Transcript rỗng — video gốc không có lời thoại để lồng tiếng."*
(router_client.py:356–359).

**Rationale**: v1 **không** làm nhánh "sản phẩm không lời" (chạy tiếp bỏ qua TTS
và xuất video im lặng). Nhánh đó là một chế độ xử lý mới, không phải một phần của
cơ chế chốt, và người dùng đã có `script_mode="download"` để lấy video gốc.
Đây là chỗ duy nhất trong feature mà hành vi kết thúc là `failed` chứ không phải
`done` — được ghi lại tường minh ở đây thay vì để agent thực thi tự đoán.

**Alternatives considered**: chặn không cho phê duyệt khi 0 câu — loại vì spec nói
rõ người dùng được quyền chọn; thêm nhánh xuất video không lời — loại vì mở rộng
phạm vi (Principle V).

## 11. Job cũ và job không supervised (FR-002, SC-001)

**Decision**: mọi field mới đọc bằng `job.get("supervised", False)` /
`job.get("review_gate")`. Không viết migration, không sửa `job.json` cũ.

**Rationale**: đúng khuôn mẫu đã dùng cho `dynamic_captions`, `tts_provider`,
`pinned`, `keep_original_ranges` (jobs_api.py:146–153) — job cũ thiếu field mặc
định về `False`/`None`, tức chạy liền mạch như trước. Điểm dừng chỉ được đánh giá
bên trong `if supervised:`, nên đường đi của job không supervised **không thêm một
nhánh nào** ở runtime.

**Ràng buộc bổ sung**: `run_pipeline()` MUST lấy `supervised` từ `job.json`
(không chỉ từ tham số hàm) — cùng lỗi đã sửa cho `dynamic_captions` ở T035 của
feature 005 (pipeline.py:577): resume/retry không truyền lại cờ sẽ âm thầm mất
chế độ quản lý và job chạy vọt qua chốt.
