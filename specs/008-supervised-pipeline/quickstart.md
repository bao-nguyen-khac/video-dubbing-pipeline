# Quickstart & Validation: Chế độ quản lý pipeline (008-supervised-pipeline)

**Ngày**: 2026-07-30 | **Plan**: [plan.md](./plan.md) | **API**: [contracts/api.md](./contracts/api.md)

Hướng dẫn chạy & kiểm chứng tính năng end-to-end. Đây là tài liệu **verify**, không
phải tài liệu implement — chi tiết từng bước code nằm ở `tasks.md`.

---

## Prerequisites

- Python 3.11 trong `venv/` đã cài `requirements.txt`; `ffmpeg` có trong PATH.
- `.env` có `ROUTER_BASE_URL` / `ROUTER_API_KEY` / `ROUTER_MODEL` (cần cho bước
  sinh kịch bản và bước chèn dấu câu ở chốt 1) và `WEB_UI_*` cho đăng nhập.
- Frontend đã build: `cd web/frontend && npm install && npm run build`.
- **TTS**: mọi lượt verify dùng `edge-tts` (Constitution VI). KHÔNG chọn
  LucyAI/Vivibe cho các lượt thử lặp lại.
- **Không cần** `ZERNIO_API_KEY` — feature này không chạm luồng đăng bài.

Khởi động backend từ repo root:

```bash
./venv/bin/uvicorn web.backend.main:app --host 0.0.0.0 --port 8000
```

## Unit test (chạy trước, nhanh, không tốn quota)

```bash
./venv/bin/python -m pytest tests/unit/test_review_gates.py tests/unit/test_review_api.py tests/unit/test_supervised_pipeline.py -v
```

Bộ test này MUST mock mọi lượt gọi LLM (monkeypatch `start_job` hoặc
`script_gen.router_client._chat_completion`) và trỏ `JOBS_DIR` sang `tmp_path` —
không được gọi 9router thật, không được ghi vào `jobs/` thật.

Toàn bộ test hiện có phải vẫn xanh (chứng cứ cho SC-001 ở tầng unit):

```bash
./venv/bin/python -m pytest tests/ -q
```

## Scenario A — Chốt lời thoại: dừng, sửa, phê duyệt (US1, SC-003, SC-007)

Dùng một clip **ngắn** (dưới ~60s) có tên riêng dễ bị nghe sai.

1. Mở web UI, tab tạo job: dán URL, chọn chế độ `Dịch & lồng tiếng`, provider
   `edge-tts`, **bật** checkbox "Quản lý pipeline", submit.
2. **Kỳ vọng**: job chạy qua download + tách lời rồi dừng. Danh sách job hiển thị
   nhãn *chờ duyệt* (khác hẳn nhãn đang xử lý và nhãn lỗi — FR-006), tiến trình
   40%.
3. Mở trang chi tiết job. **Kỳ vọng**: bảng các câu đã tách, mỗi dòng có mốc
   `start–end` **không sửa được** (FR-016) và nội dung chữ **sửa được**; có nút
   *Lưu* và *Phê duyệt*.
4. Sửa một câu bị nghe sai (vd tên riêng), bấm **Lưu**.
   **Kỳ vọng**: thông báo lưu thành công, job vẫn ở trạng thái chờ duyệt.
5. Bấm **Phê duyệt**. **Kỳ vọng**: job chạy tiếp sang bước sinh kịch bản.

**Kiểm chứng bằng file** (bằng chứng cụ thể, Constitution VI):

```bash
python3 -c "import json,sys; d=json.load(open(f'jobs/{sys.argv[1]}/transcript_reviewed.json')); print('words' in d['segments'][0], len(d['segments'])); [print(s['text']) for s in d['segments'][:5]]" <JOB_ID>
```

MUST in ra `False` ở giá trị đầu (không có `words` — điều kiện đúng đắn của
feature, [research.md](./research.md) §3) và thấy câu đã sửa.

Sau khi job xong, câu đã sửa MUST xuất hiện trong `jobs/<JOB_ID>/script.json`
(`source_text` của segment tương ứng) và trong giọng đọc/phụ đề của
`output.mp4` — đây chính là SC-003.

## Scenario B — Chốt kịch bản: đối chiếu, sửa, phê duyệt (US2)

Tiếp ngay Scenario A.

1. **Kỳ vọng**: job dừng lần hai, tiến trình 56%, nhãn chờ duyệt tại *chốt kịch bản*.
2. Trang chi tiết: mỗi dòng hiện **câu gốc** bên cạnh **câu dịch sửa được** (FR-010).
3. Sửa một câu dịch, **Lưu**, rồi **Phê duyệt**.
4. **Kỳ vọng**: job chạy tiếp TTS → merge → `done`; nghe/xem `output.mp4` thấy đúng
   câu đã sửa.
5. `jobs/<JOB_ID>/script_original.json` MUST tồn tại và chứa bản dịch **trước** khi
   sửa tay.

Lặp lại Scenario A+B với `script_mode = "subtitle"` để xác nhận cả 2 chốt vẫn áp
dụng và phụ đề burn ra khớp nội dung đã sửa (US2-4).

## Scenario C — Không chiếm suất & chống duyệt trùng (US3, SC-005, FR-018/FR-019)

1. Để job A dừng ở một chốt (đừng phê duyệt).
2. Submit job B mới. **Kỳ vọng**: nhận `201` và job B bắt đầu chạy (SC-005) — KHÔNG
   phải `409 "Đang có job xử lý"`.
3. Trong lúc job B đang xử lý, bấm **Phê duyệt** job A.
   **Kỳ vọng**: `409` kèm thông báo nói rõ đang có job khác xử lý; job A vẫn ở
   trạng thái chờ duyệt và nội dung đã sửa còn nguyên.
4. Chờ job B xong, bấm phê duyệt lại job A. **Kỳ vọng**: chạy tiếp bình thường.
5. **Duyệt hai lần**: bấm Phê duyệt hai lần liên tiếp thật nhanh (hoặc mở 2 tab).
   **Kỳ vọng**: đúng một lượt chạy tiếp; lượt sau trả `409` vô hại. Kiểm chứng
   bằng log backend — MUST NOT thấy hai lượt bắt đầu cùng một bước cho cùng job.

## Scenario D — Bền vững qua restart (SC-006, FR-007)

1. Để một job ở trạng thái chờ duyệt, đã **Lưu** ít nhất một câu sửa.
2. Dừng backend (Ctrl-C) rồi khởi động lại.
3. **Kỳ vọng**: job vẫn `awaiting_review` tại **đúng chốt cũ**, bảng câu hiện đúng
   nội dung đã lưu, không tự chạy tiếp, không bị đánh dấu lỗi.
4. Không phê duyệt, đợi ≥30 phút. **Kỳ vọng**: vẫn chờ duyệt (SC-002).

> Lưu ý: user này tự deploy/restart hệ thống — không tự chạy `docker compose` ở
> bước này, hãy nhờ người dùng restart.

## Scenario E — Hồi quy: job không bật chế độ quản lý (SC-001, FR-002)

1. Submit job với checkbox "Quản lý pipeline" **TẮT**.
2. **Kỳ vọng**: chạy liền một mạch `pending → downloading → transcribing →
   scripting → synthesizing → merging → done`, **không** một điểm dừng nào, trang
   chi tiết KHÔNG hiện panel review.
3. `jobs/<JOB_ID>/job.json` MUST có `supervised: false`, `review_gate: null`,
   `review_gates: {}`, và **không** có `transcript_reviewed.json`.
4. Mở một job **cũ** (tạo trước feature này) trong danh sách + trang chi tiết:
   MUST hiển thị bình thường, không lỗi vì thiếu field mới.

## Scenario F — Các nhánh biên (Edge Cases trong spec)

| Kiểm tra | Cách chạy | Kỳ vọng |
|---|---|---|
| Chế độ chỉ tải (FR-008) | Submit `script_mode="download"` + bật quản lý | Job kết thúc `done`, KHÔNG bao giờ vào `awaiting_review` |
| Bỏ câu rác (FR-013) | Xoá trắng nội dung 1 câu rồi Lưu | `saved_count` giảm 1, `dropped_count` = 1; câu đó không có trong sản phẩm cuối |
| Rỗng toàn bộ (FR-014) | Xoá trắng MỌI câu rồi Lưu | `400` kèm lý do rõ ràng; file trên đĩa **không đổi** |
| Sửa chưa lưu (FR-015) | Sửa một câu rồi bấm Phê duyệt ngay | Frontend cảnh báo trước, không âm thầm bỏ phần sửa |
| Video không lời | Job supervised với clip không có tiếng nói | Chốt 1 vẫn dừng, hiện rõ "không có câu nào"; nếu phê duyệt → job `failed` với message *"Transcript rỗng — video gốc không có lời thoại..."* ([research.md](./research.md) §10) |
| Xoá job chờ duyệt (FR-022) | `DELETE /api/jobs/{id}` khi đang chờ duyệt | `200 {"ok": true}`, thư mục job bị xoá |
| Retry sau chốt (FR-023) | Làm job lỗi ở bước TTS (vd tắt mạng) rồi bấm Thử lại | Chạy tiếp từ bước lỗi, KHÔNG bắt duyệt lại các chốt đã duyệt; `review_gates.*.approved_at` giữ nguyên |
| Sinh lại kịch bản (US4) | Ở chốt 2 bấm Sinh lại | Hộp xác nhận cảnh báo ghi đè; sau khi xác nhận, `script.json` có nội dung mới, job dừng lại đúng chốt 2, `transcript_reviewed.json` **không đổi** |

## Kiểm tra nhanh bằng curl (không cần UI)

```bash
curl -s -c /tmp/c.txt -X POST localhost:8000/api/login -H 'Content-Type: application/json' -d '{"username":"<USER>","password":"<PASS>"}'
```

```bash
curl -s -b /tmp/c.txt localhost:8000/api/jobs/<JOB_ID>/review | python3 -m json.tool | head -40
```

```bash
curl -s -b /tmp/c.txt -X POST localhost:8000/api/jobs/<JOB_ID>/review/approve -H 'Content-Type: application/json' -d '{"gate":"transcript"}'
```

## Definition of Done cho feature

- [ ] `pytest tests/ -q` xanh toàn bộ (gồm 3 file test mới).
- [ ] Scenario A + B chạy trọn một lượt thật, có `output.mp4` chứa nội dung đã sửa.
- [ ] Scenario C, D, E, F đạt kỳ vọng, có log/output làm bằng chứng.
- [ ] Không thêm dependency nào vào `requirements.txt` / `package.json`.
