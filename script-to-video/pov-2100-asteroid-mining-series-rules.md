# Series Bible: POV Khai Thác Tiểu Hành Tinh (2100)

> Chốt ngày 2026-08-11. Series **độc lập** với POV 2126 — không dùng chung world rules/solarpunk. File này là nguồn quy tắc chuẩn cho mọi arc trong dòng 2100 asteroid mining. Cập nhật file này nếu quy tắc đổi.

## 1. Khái niệm
- Mỗi tập là góc nhìn thứ nhất (POV) của **một người làm việc trong ngành khai thác tiểu hành tinh** năm **2100** (kỹ sư, phi công drone, nhà địa chất quỹ đạo, thợ bảo trì, điều phối viên quỹ đạo...).
- Nội dung phải **thực tế/hợp lý** — ngoại suy từ xu hướng thật: asteroid mining, ISRU, robotics, AI vận hành, propulsion, radiation shielding. KHÔNG fantasy, KHÔNG “chiến tranh sao”, KHÔNG sinh vật ngoài hành tinh.
- Hướng hình ảnh: **hard sci-fi công nghiệp quỹ đạo** — kim loại bẩn, đèn làm việc ấm/lạnh lẫn, bụi khoáng, kính chống bức xạ, máy móc nặng. Tránh neon cyberpunk và tránh “tàu trắng bóng như quảng cáo”.

## 2. Nguyên tắc sản xuất (Google Flow / Gemini Omni Flash)
- Công cụ: **Google Flow**, model **Gemini Omni Flash**. KHÔNG nhúng `--ar 9:16` hay tham số Midjourney vào prompt.
- Format: dọc 9:16 — chọn trong UI Google Flow.

### Khung prompt chuẩn Omni Flash (5 yếu tố)
1. **Goal** — loại video / vị trí screen trong chuỗi.
2. **Input Role** — gọi tên ảnh Ingredients rõ ràng (`Using the provided images for...`).
3. **Scene** — ~20 từ trọng tâm, không giải thích vật lý dài.
4. **Motion** — camera + hành động vừa đúng ~10s.
5. **Constraints** — giữ trang phục, HUD, đặc điểm nhận diện xuyên suốt.
- Audio gắn thẳng trong Visual Prompt: `Dialogue: ...`, `SFX: ...`, `Ambient noise: ...`.
- `Dialogue: None` khi không có ai nói trên hình — lời tiếng Việt lồng tiếng hậu kỳ (TTS).

### Ingredients
- Tạo ảnh tham chiếu bằng **Gemini 2.5 Flash Image** trước khi generate video.
- Ảnh nhân vật: nền trơn, ánh sáng nhất quán trong 1 arc.
- Prompt video luôn gọi đúng tên ảnh đã upload.

## 3. World Rules — giữ xuyên suốt mọi arc
- **Card mở đầu HUD** góc màn hình: `[Tàu / Địa điểm quỹ đạo] — Năm 2100 — [Vai trò]`. Cùng style mọi tập.
- **Mood/palette:** công nghiệp quỹ đạo — xám kim loại, amber cảnh báo, xanh cyan của panel hệ thống, ánh nắng khắc nghiệt ngoài kính quan sát.
- **Sợi dây liên kết vũ trụ:** AI vận hành đội tàu tên **Vega** — chỉ giọng nói + 1 chấm sáng nhỏ trên console, xuất hiện thoáng qua mọi arc.
- **Tài nguyên khai thác chuẩn thế giới:** Platinum, Nickel, Cobalt, và các vật liệu hiếm khác — nhắc đúng, không bịa kim loại “fantasy”.

## 4. Cấu trúc Arc — mặc định **2 phần dài** (không tách 4 phần ngắn)
> Tách 4 phần × ~40s dễ thành teaser rỗng. Ưu tiên **2 video/arc**, mỗi video đủ nghĩa.

1. **Phần 1 — Hook + Đào sâu** — nhân vật là ai, công nghệ/quy trình đặc trưng chạy ra sao, kết bằng tình huống dở dang cần kỹ sư vào cuộc.
2. **Phần 2 — Twist + Kết/CTA** — sự cố leo thang, nhân vật xử lý, câu đọng + bắc cầu arc sau.
- Đăng cách ngày 1 phần để giữ cliffhanger giữa 2 tập.
- Chỉ tách thêm phần khi nội dung thực sự vượt quá ~60–70s; tránh chia nhỏ chỉ để “đủ số tập”.

## 5. Thời lượng & độ dài phần
- Mỗi phần khoảng **10 screen** (mục tiêu ~70–90s tổng), đủ nghĩa — không cắt thành teaser mỏng.
- Mỗi screen chọn **4 / 6 / 8 / 10 giây** trong UI Google Flow (không cố định 10s). Ghi rõ thời lượng chọn ở đầu mỗi `prompt-screen-*.md`.
- Trong Visual Prompt phải có **timeline nhịp** (vd: `From 0-4 seconds: ... From 4-8 seconds: ...`) khớp đúng số giây đã chọn.
- Mỗi phần phải có ≥1 chi tiết công nghệ/cốt truyện đáng nhớ — không chỉ hook rỗng.

## 5b. Chuyển cảnh mượt giữa các screen (bắt buộc)
Flow/Veo generate **từng clip rời** — nếu screen sau mở cảnh mới hoàn toàn sẽ bị “cứng”. Áp dụng chuỗi handoff:

1. **Match end → start:** mỗi `prompt-screen-N` ghi `END STATE` và screen N+1 mở bằng đúng trạng thái đó (góc máy / tư thế / ánh sáng / prop trên tay).
2. **Nối hành động, đừng reset:** ưu tiên tiếp nối (tay đang với → nhấn; đang nhìn feed → zoom vào feed), tránh mỗi clip mở bằng establishing shot mới.
3. **Một trục không gian mỗi cụm:** cụm cửa sổ (S1–S2), cụm console (S3–S5, S7–S10), cụm feed robot (S6) — chỉ “nhảy” khi có lý do (vd: vào feed full-frame).
4. **Câu nối trong prompt:** đoạn đầu Visual Prompt luôn có `Continuing from the previous shot, ...` + mô tả trạng thái kế thừa; đoạn cuối có `End frozen on ...` để khóa khung chốt.
5. **Hậu kỳ (nên làm):**
   - 1 lớp ambient liên tục cả phần (hull hum / fans) — cắt hình nhưng không cắt giường âm.
   - Match-cut cứng nếu handoff đã khớp; nếu lệch nhẹ dùng crossfade **4–8 frame** (~0.15–0.3s), không dissolve dài.
   - Cách mạnh nhất nếu Flow cho phép: lấy **frame cuối** clip N làm image/frame điều kiện cho clip N+1.
6. **Khóa trục trái/phải (screen direction):** trong cùng 1 cụm không gian, ghi rõ cửa sổ / console / hướng mặt nằm **screen-left hay screen-right**. Screen sau phải giữ cùng trục — cấm để model tự lật gương (người đi trái→phải ở clip 1 rồi phải→trái ở clip 2).


## 6. Cấu trúc thư mục
```
script-to-video/2100-pov-<ten-nhan-vat>/
  character-bible.md
  part-1/  script.md, prompt-screen-*.md, video-raw/
  part-2/  ...
```

## 7. Pool nhân vật (brainstorm)
1. Kỹ sư hệ thống trong cabin quản lý đàn robot khai thác ← **arc đầu (Erik)**
2. Phi công EVA / thợ sửa robot ngoài bề mặt tiểu hành tinh
3. Nhà địa chất quỹ đạo đọc phổ khoáng từ xa
4. Điều phối viên quỹ đạo tránh va chạm mảnh vụn khai thác
5. Kỹ thuật viên khoang nghiền–tách Platinum / Nickel / Cobalt trên tàu mẹ
