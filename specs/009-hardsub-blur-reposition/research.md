# Research: Làm mờ phụ đề gốc và chèn phụ đề mới đúng vị trí (009)

**Ngày**: 2026-07-30 | **Plan**: [plan.md](./plan.md)

Không có mục NEEDS CLARIFICATION nào trong Technical Context — spec đã qua
`/speckit-clarify` với các quyết định đã chốt (2 câu hỏi: hành vi khi dò sai vị
trí + tiêu chí phân biệt tiêu đề/phụ đề). Phần dưới ghi lại các quyết định kỹ
thuật rút ra từ việc đọc code hiện có và thử nghiệm trực tiếp trên máy, để agent
thực thi không phải suy luận lại.

---

## 1. Vì sao cần đổi từ `.srt` sang `.ass` cho phụ đề mới

**Vấn đề**: `merge/subtitle_burner.py` hiện tại burn phụ đề bằng bộ lọc ffmpeg
`subtitles=...:force_style='Alignment=2,FontSize=16,...'`. `force_style` là
tham số **toàn cục cho cả file** — không có cách nào khiến MỘT SỐ dòng phụ đề
dùng vị trí/cỡ chữ khác trong khi các dòng khác giữ nguyên vị trí mặc định,
trong cùng một lượt gọi `subtitles` filter.

**Decision**: sinh phụ đề mới bằng định dạng **ASS (Advanced SubStation
Alpha)** thay vì SRT khi tính năng 009 bật. Mỗi dòng thoại (Dialogue) trong
`.ass` có thể mang override tag riêng ngay trong nội dung — `{\pos(x,y)\fs<n>}`
— áp dụng CHỈ cho dòng đó. Với các dòng KHÔNG rơi vào vùng đã phát hiện, không
thêm override gì, dòng đó tự nhiên dùng đúng style mặc định (giữ nguyên
`force_style` hiện có, không đổi hành vi cũ — SC-006).

`burn_subtitles()` vẫn dùng đúng bộ lọc `subtitles=...` của ffmpeg (libass đọc
được cả `.srt` lẫn `.ass`), chỉ đổi file đầu vào — không đổi cách gọi ffmpeg ở
tầng ngoài.

**Alternatives considered**:

- *Nhiều lượt gọi `subtitles` filter, mỗi lượt 1 `force_style` riêng, mỗi lượt
  chỉ chứa các dòng cùng vị trí*: không khả thi vì mỗi vùng phát hiện thường có
  toạ độ KHÁC NHAU (mỗi đoạn có phụ đề gốc một vị trí riêng) — số lượt gọi sẽ
  bằng số vùng, và mỗi lượt cần một file phụ đề con chỉ chứa đúng các dòng của
  vùng đó, phức tạp hơn hẳn 1 file `.ass` với override theo dòng.
- *`drawtext` filter thay cho `subtitles`*: `drawtext` không đọc file phụ đề,
  phải tự dựng timeline `enable=between(...)` cho từng dòng — mất hết lợi ích
  của cơ chế `write_srt()`/timeline sẵn có, và không tự xuống dòng được như
  libass.

## 2. Mờ theo vùng: chain `crop → boxblur → overlay`, không phải 1 `boxblur` toàn khung

**Vấn đề**: mỗi đoạn có phụ đề gốc có TOẠ ĐỘ RIÊNG (khác nhau). Một bộ lọc
`boxblur` áp cho toàn khung hình sẽ mờ luôn phần không cần mờ; `boxblur` cũng
không nhận toạ độ vùng — nó mờ toàn bộ frame nó nhận được.

**Decision**: với mỗi vùng đã phát hiện, dựng một chain filter riêng:

```text
[base]split=2[pass][region_in]
[region_in]crop=w:h:x:y,boxblur=<mức mờ>[blurred]
[pass][blurred]overlay=x:y:enable='between(t,start,end)'[base]
```

Lặp lại chain này cho từng vùng (nối tiếp `[base]` qua các vùng), số chain =
số đoạn có phụ đề gốc — đúng tinh thần SC-005 (chi phí tỉ lệ số đoạn). Toàn bộ
dùng filter có sẵn của ffmpeg (`split`, `crop`, `boxblur`, `overlay` — đã xác
nhận có mặt trên bản ffmpeg 8.1.2 cài qua Homebrew, và các bản ffmpeg tiêu
chuẩn khác không cần build đặc biệt như `subtitles`/libass).

Chạy như MỘT PASS ffmpeg RIÊNG (trước burn phụ đề), tương tự cách
`apply_keep_original_ranges()` đã làm cho audio — giữ đúng khuôn mẫu "mỗi bước
xử lý là 1 pass ffmpeg tách biệt, dễ test/debug độc lập" đã dùng xuyên suốt
`merge/ffmpeg_merge.py`.

**Alternatives considered**:

- *1 `boxblur` áp toàn khung hình cả video*: đơn giản nhất nhưng làm mờ nhầm
  toàn bộ phần không có phụ đề gốc — vi phạm SC-002 trực tiếp.
- *Xử lý bằng Pillow/OpenCV thao tác từng frame (thay vì filter ffmpeg)*: chậm
  hơn nhiều (decode/encode lại toàn bộ frame bằng Python), không tận dụng được
  tăng tốc phần cứng của ffmpeg — không cần thiết khi ffmpeg filter làm được.

## 3. Phân biệt "có nền hộp" và "không nền hộp" — độ lệch chuẩn màu pixel

**Vấn đề** (FR-014): OCR chỉ trả về VỊ TRÍ có chữ, không biết dòng chữ đó có
đang nằm trên một nền hộp đặc (kiểu tiêu đề) hay nằm trực tiếp trên khung hình
video (kiểu phụ đề khớp lời nói, chỉ có viền đen quanh chữ).

**Decision**: với mỗi dòng chữ OCR tìm được (bounding box), lấy một **vùng dò
xét mở rộng** quanh bounding box đó (nới thêm ~20% mỗi chiều), rồi tính **độ
lệch chuẩn (standard deviation)** giá trị màu (RGB) của các pixel trong vùng
dò xét đó (không tính riêng vùng chữ, tính cả vùng — nét chữ chiếm tỉ lệ nhỏ
nên không làm sai lệch đáng kể):

- Độ lệch chuẩn **thấp** (màu gần như đồng nhất trên cả vùng chữ nhoè lẫn nền
  xung quanh) → nghi ngờ có **nền hộp đặc** → loại (FR-014).
- Độ lệch chuẩn **cao** (nền là nội dung video thật — quần áo, tuyết, background
  — biến thiên mạnh) → **không có nền hộp** → giữ làm ứng viên.

Ngưỡng cụ thể xác định qua thử nghiệm (task riêng ở tasks.md), không cứng số ở
đây — vì phụ thuộc dải giá trị ảnh JPEG ffmpeg xuất ra.

Dùng `numpy` (đã có sẵn trong `requirements.txt`) để tính, `Pillow` (mới) chỉ
để load file ảnh ffmpeg xuất ra thành mảng pixel.

**Alternatives considered**:

- *Dùng LLM vision phân loại "có nền hay không"*: đã bị loại khi chốt spec —
  chậm, tốn phí, và không cần thiết khi heuristic pixel đơn giản đã đủ tin cậy
  cho hình dạng box chữ nhật rõ ràng.
- *Phân tích màu chữ OCR trả về (nếu API hỗ trợ) thay vì màu nền*: Tesseract cơ
  bản không trả màu chữ đáng tin cậy qua `image_to_data()` — phải tự đọc pixel
  vùng chữ, phức tạp hơn không cần thiết so với đọc màu NỀN (rẻ, đơn giản hơn).

## 4. Gộp nhiều dòng OCR thành một vùng (giữ đúng Assumption "một vùng/đoạn")

**Vấn đề**: một câu phụ đề dài có thể xuống 2 dòng — OCR trả về 2 bounding box
tách biệt (theo dòng), dù về mặt hiển thị đó là MỘT khối phụ đề.

**Decision**: sau khi lọc bỏ các dòng "có nền hộp" (bước 3), **gộp các dòng còn
lại theo cụm không gian**: hai dòng được coi là cùng một khối nếu khoảng cách
theo trục dọc giữa chúng nhỏ hơn ~1 lần chiều cao dòng chữ và có độ chồng lấn
theo trục ngang. Lấy hợp (union) bounding box của cả cụm làm MỘT `Vùng phụ đề
gốc`. Nếu sau khi gộp còn nhiều hơn 1 cụm tách biệt (vd 2 vị trí khác hẳn nhau
trên màn hình) → chọn cụm có độ tin cậy OCR trung bình cao nhất, đúng
Assumption "chỉ có MỘT vùng chữ mỗi đoạn" trong spec.

**Alternatives considered**: coi mỗi dòng OCR là một vùng riêng, không gộp —
bị loại vì phá vỡ trực tiếp Assumption trong spec và sẽ tạo 2 vùng mờ tách rời
cho cùng một khối phụ đề 2 dòng, trông rất lạ mắt.

## 5. Lấy mẫu 1–3 khung hình đại diện, không chỉ 1

**Vấn đề**: US3 (spec) đã chấp nhận trường hợp "không tìm thấy" là hợp lệ và
an toàn, nhưng nếu CHỈ lấy đúng 1 khung hình mốc giữa đoạn, xác suất rơi vào
đúng khoảng KHÔNG có phụ đề hiển thị (giữa 2 câu) là không nhỏ — sẽ khiến quá
nhiều đoạn rơi vào US3 một cách không cần thiết.

**Decision**: lấy tối đa **3 khung hình** trải đều trong đoạn (VD 25%/50%/75%
thời lượng đoạn, giới hạn bởi độ dài đoạn nếu đoạn quá ngắn), thử OCR+lọc lần
lượt, DỪNG ngay khi tìm được 1 vùng hợp lệ. Chỉ khi cả 3 lần đều không tìm được
mới rơi vào US3. Vẫn giữ đúng SC-005 (chi phí tỉ lệ SỐ ĐOẠN — tăng hệ số nhân
cố định ×3, không tỉ lệ độ dài video).

**Alternatives considered**: chỉ 1 khung hình (rẻ nhất nhưng dễ rơi vào US3 quá
thường xuyên với đoạn có khoảng lặng giữa các câu) — bị loại vì giảm giá trị
thực dụng của tính năng quá nhiều so với chi phí thêm không đáng kể (tối đa
gấp 3, vẫn rất rẻ).

## 6. Thời điểm chạy phát hiện trong `run_pipeline()` — SAU transcribe, TRƯỚC chốt 1

**Decision**: bước phát hiện vùng phụ đề gốc chạy **ngay sau `transcribe()`
thành công**, TRƯỚC nhánh `if active_supervised and not is_approved(...)` của
chốt 1 (008) — và chạy **không điều kiện theo `active_supervised`**, chỉ điều
kiện theo `job.get("hardsub_blur_enabled")` và `script_mode` có hiển thị phụ đề
(FR-009). Idempotent: bỏ qua nếu `hardsub_regions.json` đã tồn tại (đúng khuôn
mẫu `generate_script()`/`transcribe()` đang dùng cho resume).

**Rationale**:

- Việc phát hiện chỉ cần `source_video` (đã có ngay sau download) — không phụ
  thuộc kết quả ASR. Đặt SAU transcribe (không phải ngay sau download) chỉ vì
  đây là điểm cần trùng với chốt 1 để job supervised hiển thị được (FR-012),
  và transcribe với detect hardsub có thể xem như 2 việc độc lập chạy tuần tự
  trong cùng nhịp pipeline hiện có, không cần thêm status mới.
- Chạy KHÔNG điều kiện theo `active_supervised` giữ ĐÚNG MỘT code path cho cả
  2 trường hợp (FR-012 và FR-013) — job supervised chỉ khác ở chỗ payload chốt
  1 có thêm field `hardsub_regions`, không phải khác luồng tính toán.
- Idempotent giữ đúng FR-011 (không đổi lại vùng đã dò sau mỗi lần retry) —
  tương tự tinh thần "câu đã duyệt không tính lại" của review/gates.py.

**Alternatives considered**: chạy detect ở bước merging (ngay trước khi cần
dùng) — bị loại vì khi đó KHÔNG còn kịp hiển thị ở chốt 1 (đã qua từ lâu),
không thoả FR-012.

## 7. Đánh dấu "không có phụ đề gốc" tại chốt 1 — ghi vào field khai báo có sẵn

**Decision**: khi người dùng đánh dấu một đoạn dò sai thành "không có phụ đề
gốc" tại chốt 1 (FR-012), hành động này **nối thêm khoảng đó vào
`job["hardsub_no_ranges"]`** (cùng field, cùng cú pháp chuỗi khai báo lúc tạo
job — FR-004) và đánh dấu `excluded: true` cho đúng entry đó trong
`hardsub_regions.json`. KHÔNG chạy lại OCR — vùng đã dò (hoặc không dò được)
vẫn giữ nguyên trong file, chỉ thêm cờ loại trừ.

**Rationale**: tái dùng đúng MỘT khái niệm "khoảng không có phụ đề gốc" đã có ở
FR-004, thay vì tạo thêm một field song song thứ hai — tránh 2 nguồn sự thật
cho cùng một ý nghĩa. Bước merging chỉ cần đọc `excluded` để biết bỏ qua vùng
nào, không cần tính lại complement.

## 8. Ràng buộc từ môi trường: không libass ⟹ không burn được (kế thừa từ 008)

**Không phải vấn đề MỚI của feature này** — đã ghi nhận khi verify feature 008:
ffmpeg cài qua Homebrew trên máy dev hiện tại **không có libass**
(`ffmpeg -filters | grep subtitles` → rỗng). Tính năng 009 phụ thuộc CÙNG bộ
lọc `subtitles` để burn `.ass`, nên **kế thừa nguyên hạn chế này**, không phải
lỗi mới phát sinh. Debian's `apt-get install ffmpeg` (dùng trong Dockerfile)
build kèm libass theo mặc định — môi trường production/Docker không bị ảnh
hưởng. Bước blur (`crop`/`boxblur`/`overlay`) KHÔNG cần libass, verify được đầy
đủ ở local; chỉ bước burn `.ass` cuối cùng cần môi trường có libass.

## 9. Constitution: cần amend TRƯỚC khi implement

`pytesseract` + `tesseract-ocr` (binary) + `Pillow` là 3 dòng công nghệ MỚI, và
Governance của constitution.md nói rõ: *"Thay đổi bất kỳ dòng nào trong bảng
[Technology Stack] MUST đi qua amend constitution (Governance), không được đổi
ngầm trong plan.md của từng feature."* Plan này KHÔNG tự thêm dòng vào bảng đó
— việc amend phải chạy qua `/speckit-constitution` như một bước RIÊNG, đứng
trước `/speckit-implement`. Đây là điểm agent thực thi (`tasks.md`) MUST nhắc
lại như một điều kiện tiên quyết, không phải một task thường.
