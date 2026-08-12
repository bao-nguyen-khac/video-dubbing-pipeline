# Phần 1/2: "Đàn Robot Ngoài Kia" (~76s · 10 screen)

> **Format:** 9:16 · Google Flow · Gemini Omni Flash  
> **Ingredients:** [`../character-bible.md`](../character-bible.md) — Erik / Cabin / Cửa sổ+robots / Mining robot  
> **Thời lượng:** chọn đúng 6/8/10s từng file trong UI Flow.  
> **Chuyển cảnh:** mỗi prompt có handoff END→START; xem bảng Continuity bên dưới + mục 5b series rules.

---

## Continuity chain (khớp cắt)

| Từ → Sang | Kiểu nối | Handoff |
|---|---|---|
| S1 → S2 | match face + **cùng chiều L→R** | S1: Erik **right-facing**, cửa sổ **screen-right** → S2 mở cùng chiều, rồi **bước tiếp sang phải** vào cabin (không quay bước trái) |
| S2 → S3 | nối bước cùng chiều L→R | S2 end mid-step **screen-right** → S3 vào từ **screen-left**, đi tiếp sang phải, ngồi console **center-right** |
| S3 → S4 | match tay | S3 đóng tablet cyan sáng, mắt hướng console → S4 mở tay đã ở trên 3 tile |
| S4 → S5 | quay đầu | S4 đóng 3 tile xanh, tay nghỉ → S5 mở từ cùng chỗ, Erik quay nhìn tường feed + dolly |
| S5 → S6 | eyeline cut | S5 đóng đang nhìn feed khoan giữa → S6 = full-frame đúng feed đó (**chỉ khoan**) |
| S6 → S7 | pull back | S6 đóng robot **đang khoan** trong bezel → S7 mở kéo ra OTS tay Erik trên schematic |
| S7 → S8 | pan console | S7 đóng robot chỉnh khớp trên feed phụ → S8 mở đẩy sang ore-flow bên cạnh |
| S8 → S9 | cùng khung | S8 đóng Erik liếc schematic/cửa sổ → S9 mở cùng medium, tile góc nhấp amber |
| S9 → S10 | escalate | S9 đóng Erik vừa bỏ qua tín hiệu → S10 mở cùng góc, tile chuyển đỏ hẳn |
| **P1 S10 → P2 S1** | match tay | P1 đóng tay lơ lửng trên override → P2 mở **cùng tư thế tại console** (không chạy tới từ chỗ khác) |

---

## Bảng phân cảnh

| # | Clip | Vai trò | File |
|---|------|---------|------|
| 1 | **8s** | Hook + HUD — nhìn đàn robot ngoài kính | [`prompt-screen-1.md`](prompt-screen-1.md) |
| 2 | **6s** | Bật earpiece, bước vào cabin | [`prompt-screen-2.md`](prompt-screen-2.md) |
| 3 | **8s** | Ngồi console, đánh thức tablet | [`prompt-screen-3.md`](prompt-screen-3.md) |
| 4 | **6s** | Checklist link/power/swarm-hold → xanh | [`prompt-screen-4.md`](prompt-screen-4.md) |
| 5 | **8s** | Tổng quan swarm — dolly tường feed, khóa eyeline feed giữa | [`prompt-screen-5.md`](prompt-screen-5.md) |
| 6 | **6s** | Cận feed — khoan mạnh (một action) | [`prompt-screen-6.md`](prompt-screen-6.md) |
| 7 | **10s** | Chuỗi lệnh — pull-back feed → node → chỉnh khớp khoan | [`prompt-screen-7.md`](prompt-screen-7.md) |
| 8 | **8s** | Ore-flow — pan từ schematic, 3 dải kim loại về tàu | [`prompt-screen-8.md`](prompt-screen-8.md) |
| 9 | **6s** | Foreshadow — tile amber pulse rõ ×2, Erik phản ứng | [`prompt-screen-9.md`](prompt-screen-9.md) |
| 10 | **10s** | Cliffhanger — jam khoan rõ, khớp giật rồi khóa, hover override | [`prompt-screen-10.md`](prompt-screen-10.md) |

**Tổng:** 76 giây · [`prompt-screen-vi.md`](prompt-screen-vi.md)

---

## Voiceover theo screen

1. *(8s)* *"Năm 2100. Quanh Ryke-114, đàn robot đang đào platinum, nickel và cobalt. Ca trực bắt đầu."*
2. *(6s)* *"Tôi không ra ngoài đá. Việc của tôi nằm trong cabin này."*
3. *(8s)* *"Tôi là Erik — kỹ sư hệ thống. Đàn robot chỉ mạnh khi còn nghe lệnh."*
4. *(6s)* *"Link. Điện. Swarm-hold. Tất cả phải xanh."*
5. *(8s)* *"Mười đơn vị bám đá cùng lúc — khoan, gàu, kéo. Một cơ thể ngoài kia."*
6. *(6s)* *"Nhìn gần: khớp ổn, mũi khoan ăn đúng mạch kim loại."*
7. *(10s)* *"Mỗi lệnh từ tay tôi xuống anten, xuống khớp. Sai một nhịp — cả đường quặng lệch."*
8. *(8s)* *"Nickel, cobalt, platinum chỉ về tàu khi đàn còn đồng bộ."*
9. *(6s)* *"Một tín hiệu lệch… rất nhỏ. Dễ bỏ qua."*
10. *(10s)* *"Unit 7 lệch đường khoan và mất khớp. Vega gọi tôi. Robot lỗi — việc của kỹ sư."*

---

## Hậu kỳ nối hình (nhanh)
- 1 bed ambient liên tục cả 76s.
- Cắt thẳng nếu handoff khớp; lệch nhẹ → crossfade 4–8 frame.
- Nếu Flow hỗ trợ: frame cuối S(n) → điều kiện mở S(n+1).
