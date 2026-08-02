"""
merge/hyperframes_renderer.py — render_scenes_to_video(scenes, job_dir): sinh
HTML timeline (index.html) từ scene JSON (data-model.md §3) rồi gọi
`npx hyperframes render` qua subprocess để ra output.mp4, cho tính năng
"Tạo video từ chủ đề" (010-topic-video-generation). Cú pháp data-*/tham số
CLI đã xác nhận thật ở research.md §5b (spike T002) — không suy đoán thêm.
"""

from __future__ import annotations

import html
import json
import shutil
import subprocess
from pathlib import Path

# Template project HyperFrames tối thiểu (package.json + hyperframes.json),
# KHÔNG chạy `npx hyperframes init` mỗi job — research.md §5b: init mặc định
# gọi mạng cài "AI skills" vào home dir, side-effect không mong muốn cho môi
# trường server. Template này coi như đã "init" 1 lần, commit sẵn vào repo.
TEMPLATE_DIR = Path(__file__).parent / "hyperframes_template"

# Tỉ lệ dọc 9:16 (spec Assumptions) — đã xác nhận thật ở spike T002.
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920

_HTML_HEAD = """<!doctype html>
<html lang="vi" data-resolution="portrait">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={width}, height={height}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: {width}px; height: {height}px; overflow: hidden; background: #000; }}
      body {{ font-family: "Inter", sans-serif; }}
      .scene-image {{ position: absolute; inset: 0; width: {width}px; height: {height}px; object-fit: cover; }}
      .caption {{
        position: absolute; left: 60px; right: 60px; bottom: 140px;
        color: #fff; font-size: 56px; font-weight: 700; text-align: center;
        text-shadow: 0 2px 10px rgba(0, 0, 0, 0.8);
      }}
      /* Scene "hook" (mở đầu) — câu hỏi/đặt vấn đề phóng to giữa khung, dim
         nền để chữ luôn đọc được bất kể ảnh nền sáng/tối. */
      .dim-overlay {{
        position: absolute; inset: 0;
        background: linear-gradient(180deg, rgba(0,0,0,0.15) 0%, rgba(0,0,0,0.6) 100%);
      }}
      .hook-text {{
        position: absolute; left: 60px; right: 60px; top: 50%; transform: translateY(-50%);
        color: #fff; font-size: 64px; font-weight: 800; text-align: center; line-height: 1.25;
        text-shadow: 0 4px 20px rgba(0, 0, 0, 0.9);
      }}
      /* Scene "concept"/"fact" — nhãn nhỏ góc trên giữ tên section, giúp
         người xem bám cấu trúc khi có nhiều scene ngắn liên tiếp. */
      .section-badge {{
        position: absolute; left: 60px; top: 100px;
        background: rgba(0, 0, 0, 0.55); color: #fff; font-size: 32px; font-weight: 700;
        padding: 14px 28px; border-radius: 999px; letter-spacing: 0.5px;
      }}
      /* Scene "transition" — chuyển hướng nội dung rõ rệt (VD sang khái
         niệm đối lập): thanh tối + tên section mới phóng to giữa khung. */
      .transition-bar {{
        position: absolute; left: 0; right: 0; top: 50%; height: 260px; transform: translateY(-50%);
        background: linear-gradient(90deg, rgba(0,0,0,0.8), rgba(0,0,0,0.4));
      }}
      .transition-label {{
        position: absolute; left: 0; right: 0; top: 50%; transform: translateY(-50%);
        color: #fff; font-size: 72px; font-weight: 800; text-align: center; text-transform: uppercase;
        letter-spacing: 2px; text-shadow: 0 4px 20px rgba(0, 0, 0, 0.9);
      }}
      /* Scene "fact" — tách 1 con số/sự thật đáng nhớ ra khỏi caption
         thường, nhấn bằng vạch màu bên trái thay vì chỉ caption cả câu. */
      .fact-text {{
        position: absolute; left: 80px; right: 80px; top: 50%; transform: translateY(-50%);
        color: #fff; font-size: 54px; font-weight: 800; text-align: left; line-height: 1.3;
        border-left: 8px solid #ffcc00; padding-left: 32px;
        text-shadow: 0 4px 16px rgba(0, 0, 0, 0.9);
      }}
      /* Scene "outro" — card kết luận: gradient tối dần từ dưới lên, chữ to
         giữa khung, thay vì chỉ 1 dòng caption mỏng như thân bài. */
      .outro-card {{
        position: absolute; left: 0; right: 0; bottom: 0; height: 60%;
        background: linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,0.85) 45%, rgba(0,0,0,0.92) 100%);
        display: flex; align-items: flex-end; justify-content: center; padding-bottom: 160px;
      }}
      .outro-text {{
        color: #fff; font-size: 56px; font-weight: 800; text-align: center; padding: 0 70px;
        text-shadow: 0 4px 20px rgba(0, 0, 0, 0.9);
      }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total_duration}" data-width="{width}" data-height="{height}">
"""

# Ảnh CÙNG data-start/data-duration với các lớp chữ/overlay của scene đó (khớp
# giọng đọc), khác data-track-index (không được chồng thời gian trên cùng 1
# track — xác nhận ở spike). Audio track riêng (10) — không cần class="clip"
# (không có phần hiển thị, research.md §5b).
#
# 5 template theo `scene["type"]` (script_gen/topic_script_generator.py
# SCENE_TYPES) — mỗi type build ra 1 markup khác nhau, nhưng LUÔN giữ
# `id="scene-{i}-image"` và `id="scene-{i}-caption"` để _SCRIPT_TEMPLATE
# animate chung 1 vòng lặp cho mọi type. Scene KHÔNG có "type" (job cũ trước
# khi thêm field này) mặc định "concept" — markup giữ NGUYÊN như trước đây.
_IMG_TAG = (
    '<img id="scene-{i}-image" class="clip scene-image" '
    'src="assets/scenes/{i}/image.jpg" data-start="{start}" data-duration="{duration}" '
    'data-track-index="1" />'
)
_AUDIO_TAG = (
    '<audio id="scene-{i}-audio" src="assets/scenes/{i}/voice.wav" '
    'data-start="{start}" data-duration="{duration}" data-track-index="10"></audio>'
)


def _clip(i, tag, cls, start, duration, track, text="", el_id=None):
    el_id = el_id or f"scene-{i}-{tag}"
    return (
        f'<div id="{el_id}" class="clip {cls}" data-start="{start}" '
        f'data-duration="{duration}" data-track-index="{track}">{text}</div>'
    )


def _scene_body(s: dict, i: int, start: float, duration: float) -> str:
    """Markup của 1 scene, chọn theo `s.get("type")` (mặc định "concept")."""
    scene_type = s.get("type") or "concept"
    narration = html.escape(s["narration_text"])
    section_title = s.get("section_title")
    img = _IMG_TAG.format(i=i, start=start, duration=duration)
    audio = _AUDIO_TAG.format(i=i, start=start, duration=duration)

    if scene_type == "hook":
        parts = [
            img,
            _clip(i, "dim", "dim-overlay", start, duration, 2, el_id=f"scene-{i}-badge"),
            _clip(i, "caption", "hook-text", start, duration, 3, text=narration),
            audio,
        ]
    elif scene_type == "transition":
        label = html.escape(section_title) if section_title else narration
        parts = [
            img,
            _clip(i, "bar", "transition-bar", start, duration, 2, el_id=f"scene-{i}-badge"),
            _clip(i, "caption", "transition-label", start, duration, 3, text=label),
            audio,
        ]
    elif scene_type == "fact":
        parts = [img]
        if section_title:
            parts.append(_clip(i, "badge", "section-badge", start, duration, 2, text=html.escape(section_title)))
        parts.append(_clip(i, "caption", "fact-text", start, duration, 4, text=narration))
        parts.append(audio)
    elif scene_type == "outro":
        parts = [
            img,
            f'<div id="scene-{i}-badge" class="clip outro-card" data-start="{start}" '
            f'data-duration="{duration}" data-track-index="2">'
            f'<div id="scene-{i}-caption" class="outro-text">{narration}</div></div>',
            audio,
        ]
    else:  # "concept" (mặc định) — layout gốc, không đổi so với trước
        parts = [img, _clip(i, "caption", "caption", start, duration, 2, text=narration)]
        if section_title:
            parts.append(_clip(i, "badge", "section-badge", start, duration, 3, text=html.escape(section_title)))
        parts.append(audio)

    return "\n      ".join(parts)

# Script cuối: đăng ký timeline + animate từng scene (Ken Burns trên ảnh, rise-
# fade cho caption) — hyperframes-animation skill (adapters/gsap-timeline-and-
# labels.md): position parameter dạng số = thời điểm TUYỆT ĐỐI trên timeline,
# `fromTo()` (không phải `from()`) để đúng trạng thái khi HyperFrames seek lại
# từ đầu. Chỉ tween `scale`/`y`/`opacity` (allowlist của hyperframes-core —
# KHÔNG tween width/height/top/left), không `Math.random()`/`repeat:-1`.
_SCRIPT_TEMPLATE = """
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      const scenes = {scenes_json};

      scenes.forEach((s, idx) => {{
        const img = document.getElementById(`scene-${{s.index}}-image`);
        const caption = document.getElementById(`scene-${{s.index}}-caption`);
        // Lớp phụ tuỳ template (dim-overlay/transition-bar/section-badge/
        // outro-card) — không tồn tại ở scene "concept" thường (null, bỏ qua).
        const badge = document.getElementById(`scene-${{s.index}}-badge`);
        // Ken Burns — luân phiên zoom-in/zoom-out theo chỉ số scene (quyết
        // định trước, KHÔNG random) để các scene liên tiếp không lặp y hệt
        const zoomIn = idx % 2 === 0;
        tl.fromTo(
          img,
          {{ scale: zoomIn ? 1 : 1.08 }},
          {{ scale: zoomIn ? 1.08 : 1, duration: s.duration, ease: "none" }},
          s.start,
        );
        const captionIn = Math.min(0.4, s.duration / 3);
        const captionOut = Math.min(0.3, s.duration / 3);
        tl.fromTo(
          caption,
          {{ y: 24, opacity: 0 }},
          {{ y: 0, opacity: 1, duration: captionIn, ease: "power2.out" }},
          s.start,
        );
        tl.to(
          caption,
          {{ opacity: 0, duration: captionOut, ease: "power1.in" }},
          s.start + s.duration - captionOut,
        );
        if (badge) {{
          tl.fromTo(
            badge,
            {{ opacity: 0 }},
            {{ opacity: 1, duration: captionIn, ease: "power2.out" }},
            s.start,
          );
          tl.to(
            badge,
            {{ opacity: 0, duration: captionOut, ease: "power1.in" }},
            s.start + s.duration - captionOut,
          );
        }}
      }});

      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""


def _build_index_html(scenes: list[dict]) -> str:
    """
    Sinh index.html từ scene JSON đã đủ `image_path`/`voice_path`/`duration`
    — 1 layout cố định (ảnh full-frame Ken Burns + caption rise-fade dưới),
    template string Python thuần (KHÔNG dùng Jinja2 — repo chưa có dependency
    này, research.md §5).
    """
    total_duration = sum(float(s["duration"]) for s in scenes)
    body_parts = []
    timing = []
    t = 0.0
    for s in scenes:
        duration = float(s["duration"])
        start = round(t, 3)
        duration = round(duration, 3)
        body_parts.append("\n      " + _scene_body(s, s["index"], start, duration) + "\n")
        timing.append({"index": s["index"], "start": start, "duration": duration})
        t += duration

    return (
        _HTML_HEAD.format(
            width=CANVAS_WIDTH, height=CANVAS_HEIGHT, total_duration=round(total_duration, 3)
        )
        + "".join(body_parts)
        + _SCRIPT_TEMPLATE.format(scenes_json=json.dumps(timing))
    )


def render_scenes_to_video(scenes: list[dict], job_dir: Path) -> Path:
    """
    Sinh HTML timeline từ scene JSON đã đủ `image_path`/`voice_path`/
    `duration` rồi gọi `npx hyperframes render` → `job_dir/output.mp4`.

    Mỗi lần gọi dựng LẠI `job_dir/hyperframes_project/` từ `TEMPLATE_DIR`, copy
    ảnh/audio từng scene vào TRONG thư mục project (KHÔNG tham chiếu path
    ngoài project — chưa xác nhận HyperFrames serve được asset ngoài thư mục
    project lúc render, nên đi hướng chắc chắn đã test — research.md §5b).

    Raises:
        RuntimeError: `subprocess` gọi `npx hyperframes render` lỗi (exit
            code khác 0), hoặc không tạo được output.mp4 hợp lệ.
    """
    job_dir = Path(job_dir)
    project_dir = job_dir / "hyperframes_project"
    if project_dir.exists():
        shutil.rmtree(project_dir)
    shutil.copytree(TEMPLATE_DIR, project_dir)

    assets_dir = project_dir / "assets" / "scenes"
    for s in scenes:
        scene_assets_dir = assets_dir / str(s["index"])
        scene_assets_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s["image_path"], scene_assets_dir / "image.jpg")
        shutil.copy2(s["voice_path"], scene_assets_dir / "voice.wav")

    (project_dir / "index.html").write_text(_build_index_html(scenes), encoding="utf-8")

    output_path = job_dir / "output.mp4"
    result = subprocess.run(
        [
            "npx", "--yes", "hyperframes@0.7.87", "render",
            "--quality", "standard",
            "--output", str(output_path.resolve()),
            "--strict",  # fail rõ ràng nếu lint có lỗi, thay vì render ra video sai âm thầm
            "--quiet",
        ],
        cwd=project_dir,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,  # chạy nền không có ai gõ phím — chặn triệt để mọi
        # khả năng npx treo chờ xác nhận cài package (từng bị treo đủ 600s vì thiếu
        # --yes/version ghim, lệch với package.json của chính template)
        timeout=600,  # video 1-5 phút (spec Assumptions) — dư cho render standard quality
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"npx hyperframes render thất bại (exit {result.returncode}):\n"
            f"{result.stderr[-1000:] or result.stdout[-1000:]}"
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("npx hyperframes render không tạo được output.mp4 hợp lệ")

    return output_path
