"""
tests/unit/test_hyperframes_renderer.py — render_scenes_to_video() (010-topic-
video-generation, T028).

⚠️ Constitution §VI: mock `subprocess.run` — không test nào gọi `npx
hyperframes` thật (chạy thật là quickstart.md, bước riêng ngoài unit test).
"""

from __future__ import annotations

import subprocess

import pytest

from merge import hyperframes_renderer as hr


def _make_scene(tmp_path, index, narration_text, duration, type=None, section_title=None):
    scene_dir = tmp_path / "scenes" / str(index)
    scene_dir.mkdir(parents=True)
    image_path = scene_dir / "image.jpg"
    image_path.write_bytes(b"fake-jpg")
    voice_path = scene_dir / "voice.wav"
    voice_path.write_bytes(b"fake-wav")
    scene = {
        "index": index,
        "narration_text": narration_text,
        "image_query": "q",
        "image_path": str(image_path),
        "voice_path": str(voice_path),
        "duration": duration,
    }
    if type is not None:
        scene["type"] = type
    if section_title is not None:
        scene["section_title"] = section_title
    return scene


@pytest.fixture()
def fake_subprocess_run(monkeypatch):
    """Mock subprocess.run — mặc định giả lập render THÀNH CÔNG (tạo output.mp4)."""
    calls: list[dict] = []

    def _install(returncode: int = 0, create_output: bool = True):
        def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None, stdin=None):
            calls.append({"cmd": cmd, "cwd": cwd, "timeout": timeout})
            if create_output and returncode == 0:
                # --output là đối số ngay sau "--output" trong cmd
                out_idx = cmd.index("--output") + 1
                from pathlib import Path

                Path(cmd[out_idx]).write_bytes(b"fake-mp4-bytes")
            return subprocess.CompletedProcess(
                cmd, returncode, stdout="", stderr="" if returncode == 0 else "lỗi giả lập"
            )

        monkeypatch.setattr(hr.subprocess, "run", fake_run)
        return calls

    return _install


def test_render_scenes_to_video_success(tmp_path, fake_subprocess_run):
    calls = fake_subprocess_run()
    scenes = [
        _make_scene(tmp_path, 0, "Câu chuyện bắt đầu.", 3.2),
        _make_scene(tmp_path, 1, "Và kết thúc ở đây.", 2.6),
    ]

    output_path = hr.render_scenes_to_video(scenes, tmp_path)

    assert output_path == tmp_path / "output.mp4"
    assert output_path.exists()
    assert len(calls) == 1
    cmd = calls[0]["cmd"]
    assert cmd[0] == "npx"
    assert cmd[3] == "render"
    assert "--strict" in cmd
    assert str(calls[0]["cwd"]).endswith("hyperframes_project")


def test_render_scenes_to_video_writes_index_html_with_correct_timing(tmp_path, fake_subprocess_run):
    fake_subprocess_run()
    scenes = [
        _make_scene(tmp_path, 0, "Cảnh một có dấu <script>.", 3.2),
        _make_scene(tmp_path, 1, "Cảnh hai.", 2.6),
    ]

    hr.render_scenes_to_video(scenes, tmp_path)

    index_html = (tmp_path / "hyperframes_project" / "index.html").read_text(encoding="utf-8")

    # Root duration = tổng thời lượng scene
    assert 'data-duration="5.8"' in index_html
    # Scene 0 bắt đầu ở t=0, scene 1 bắt đầu ở t=3.2 (nối tiếp, không chồng lấn)
    assert 'id="scene-0-image"' in index_html
    assert 'data-start="0"' in index_html or 'data-start="0.0"' in index_html
    assert 'id="scene-1-image"' in index_html
    assert 'data-start="3.2"' in index_html
    # Text nguy hiểm phải được escape, không lọt nguyên văn vào caption
    assert "Cảnh một có dấu <script>." not in index_html
    assert "&lt;script&gt;" in index_html
    # Ảnh/audio đã được copy vào TRONG thư mục project (research.md §5b)
    assert (tmp_path / "hyperframes_project" / "assets" / "scenes" / "0" / "image.jpg").exists()
    assert (tmp_path / "hyperframes_project" / "assets" / "scenes" / "1" / "voice.wav").exists()


def test_render_scenes_to_video_animates_scenes_ken_burns_and_caption(tmp_path, fake_subprocess_run):
    """Video không còn là slideshow tĩnh — mỗi scene có Ken Burns (scale) trên
    ảnh và rise-fade (y/opacity) trên caption, đăng ký trên timeline GSAP đúng
    theo thời điểm tuyệt đối của scene đó (đã verify render THẬT, không chỉ
    test này, xem ghi chú trong PR/commit)."""
    fake_subprocess_run()
    scenes = [
        _make_scene(tmp_path, 0, "Cảnh một.", 3.2),
        _make_scene(tmp_path, 1, "Cảnh hai.", 2.6),
    ]

    hr.render_scenes_to_video(scenes, tmp_path)

    index_html = (tmp_path / "hyperframes_project" / "index.html").read_text(encoding="utf-8")

    assert "gsap.timeline({ paused: true })" in index_html
    assert "tl.fromTo(" in index_html
    assert "scale: zoomIn ? 1 : 1.08" in index_html  # Ken Burns
    assert "y: 24, opacity: 0" in index_html  # caption entrance
    # Không dùng nguồn ngẫu nhiên/không xác định (determinism, hyperframes-core)
    assert "Math.random" not in index_html
    assert "repeat: -1" not in index_html


def test_render_scenes_to_video_raises_on_nonzero_exit(tmp_path, fake_subprocess_run):
    fake_subprocess_run(returncode=1, create_output=False)
    scenes = [_make_scene(tmp_path, 0, "x", 1.0)]

    with pytest.raises(RuntimeError, match="thất bại"):
        hr.render_scenes_to_video(scenes, tmp_path)


def test_render_scenes_to_video_raises_when_output_missing(tmp_path, fake_subprocess_run):
    """returncode=0 nhưng vì lý do gì đó không tạo ra output.mp4 — vẫn phải raise."""
    fake_subprocess_run(returncode=0, create_output=False)
    scenes = [_make_scene(tmp_path, 0, "x", 1.0)]

    with pytest.raises(RuntimeError, match="không tạo được"):
        hr.render_scenes_to_video(scenes, tmp_path)


def test_render_scenes_to_video_rebuilds_project_dir_each_call(tmp_path, fake_subprocess_run):
    """Gọi 2 lần liên tiếp không bị lỗi 'thư mục đã tồn tại' (dựng lại sạch mỗi lần)."""
    fake_subprocess_run()
    scenes = [_make_scene(tmp_path, 0, "x", 1.0)]

    hr.render_scenes_to_video(scenes, tmp_path)
    hr.render_scenes_to_video(scenes, tmp_path)  # không raise

    assert (tmp_path / "hyperframes_project" / "index.html").exists()


# ─── 5 template theo scene["type"] (script_gen SCENE_TYPES) ─────────────────


def _render_html(tmp_path, fake_subprocess_run, scenes):
    fake_subprocess_run()
    hr.render_scenes_to_video(scenes, tmp_path)
    return (tmp_path / "hyperframes_project" / "index.html").read_text(encoding="utf-8")


def test_scene_without_type_renders_original_concept_layout(tmp_path, fake_subprocess_run):
    """Job cũ (trước khi thêm field 'type') vẫn render y hệt như trước — mặc
    định 'concept', không có badge/overlay mới nào."""
    scenes = [_make_scene(tmp_path, 0, "Câu chuyện.", 3.0)]
    html_out = _render_html(tmp_path, fake_subprocess_run, scenes)

    assert 'class="clip caption"' in html_out
    assert 'class="clip hook-text"' not in html_out
    assert 'class="clip transition-label"' not in html_out
    assert 'class="clip outro-card"' not in html_out
    assert 'class="clip section-badge"' not in html_out


def test_hook_scene_renders_centered_text_and_dim_overlay(tmp_path, fake_subprocess_run):
    scenes = [
        _make_scene(tmp_path, 0, "Bạn có bao giờ thắc mắc?", 4.0, type="hook"),
        _make_scene(tmp_path, 1, "Kết luận.", 2.0, type="outro"),
    ]
    html_out = _render_html(tmp_path, fake_subprocess_run, scenes)

    assert 'class="clip hook-text"' in html_out
    assert 'id="scene-0-caption"' in html_out
    assert "Bạn có bao giờ thắc mắc?" in html_out
    assert 'class="clip dim-overlay"' in html_out
    assert 'id="scene-0-badge"' in html_out  # dim-overlay dùng chung id "badge" để JS animate


def test_concept_scene_shows_section_badge_when_section_title_present(tmp_path, fake_subprocess_run):
    scenes = [
        _make_scene(tmp_path, 0, "x", 3.0, type="hook"),
        _make_scene(tmp_path, 1, "Nội dung khái niệm.", 4.0, type="concept", section_title="Máy ảnh Digital"),
        _make_scene(tmp_path, 2, "y", 2.0, type="outro"),
    ]
    html_out = _render_html(tmp_path, fake_subprocess_run, scenes)

    assert 'class="clip section-badge"' in html_out
    assert "Máy ảnh Digital" in html_out
    assert 'class="clip caption"' in html_out  # concept vẫn giữ caption dưới như cũ


def test_transition_scene_renders_section_title_big_and_bar(tmp_path, fake_subprocess_run):
    scenes = [
        _make_scene(tmp_path, 0, "x", 3.0, type="hook"),
        _make_scene(tmp_path, 1, "Chuyển sang phần mới.", 4.0, type="transition", section_title="Máy ảnh Film"),
        _make_scene(tmp_path, 2, "y", 2.0, type="outro"),
    ]
    html_out = _render_html(tmp_path, fake_subprocess_run, scenes)

    assert 'class="clip transition-bar"' in html_out
    assert 'class="clip transition-label"' in html_out
    assert "Máy ảnh Film" in html_out


def test_fact_scene_renders_pull_quote_style_with_badge(tmp_path, fake_subprocess_run):
    scenes = [
        _make_scene(tmp_path, 0, "x", 3.0, type="hook"),
        _make_scene(tmp_path, 1, "Chỉ 36 kiểu ảnh trong 1 cuộn film.", 4.0, type="fact", section_title="Máy ảnh Film"),
        _make_scene(tmp_path, 2, "y", 2.0, type="outro"),
    ]
    html_out = _render_html(tmp_path, fake_subprocess_run, scenes)

    assert 'class="clip fact-text"' in html_out
    assert "Chỉ 36 kiểu ảnh trong 1 cuộn film." in html_out
    assert 'class="clip section-badge"' in html_out
    assert "Máy ảnh Film" in html_out


def test_outro_scene_renders_conclusion_card(tmp_path, fake_subprocess_run):
    scenes = [
        _make_scene(tmp_path, 0, "x", 3.0, type="hook"),
        _make_scene(tmp_path, 1, "Chọn Digital nếu bạn cần sự nhanh chóng.", 4.0, type="outro"),
    ]
    html_out = _render_html(tmp_path, fake_subprocess_run, scenes)

    assert 'class="clip outro-card"' in html_out
    assert 'class="outro-text"' in html_out
    assert "Chọn Digital nếu bạn cần sự nhanh chóng." in html_out


def test_all_scene_types_escape_narration_text(tmp_path, fake_subprocess_run):
    scenes = [
        _make_scene(tmp_path, 0, "Nguy hiểm <script>.", 3.0, type="hook"),
        _make_scene(tmp_path, 1, "Nguy hiểm <script>.", 3.0, type="fact"),
        _make_scene(tmp_path, 2, "Nguy hiểm <script>.", 2.0, type="outro"),
    ]
    html_out = _render_html(tmp_path, fake_subprocess_run, scenes)

    assert "Nguy hiểm <script>." not in html_out
    assert html_out.count("&lt;script&gt;") == 3


def test_badge_element_gets_fade_in_out_tween_in_script(tmp_path, fake_subprocess_run):
    """Lớp phụ (badge/dim/bar/card) phải được animate opacity giống caption —
    không đứng im/nhấp nháy đột ngột khi scene bắt đầu/kết thúc."""
    scenes = [
        _make_scene(tmp_path, 0, "x", 3.0, type="hook"),
        _make_scene(tmp_path, 1, "y", 2.0, type="outro"),
    ]
    html_out = _render_html(tmp_path, fake_subprocess_run, scenes)

    assert "const badge = document.getElementById" in html_out
    assert "if (badge) {" in html_out
