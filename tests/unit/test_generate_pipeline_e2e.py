"""
tests/unit/test_generate_pipeline_e2e.py — run_generate_pipeline() end-to-end
(010-topic-video-generation, T031).

⚠️ Constitution §VI: mock TOÀN BỘ 9router/Pexels/TTS-adapter/`npx hyperframes`
subprocess — không test nào gọi dịch vụ ngoài thật.
"""

from __future__ import annotations

import json
import subprocess

import httpx
import pytest

import generate_pipeline
from assets import pexels_client
from merge import hyperframes_renderer as hr
from review import gates
from script_gen import topic_script_generator as tsg
from tts import scene_synthesizer

_VALID_OUTLINE_RAW = json.dumps(
    {
        "outline": {"sections": [{"title": "Mở đầu", "key_points": ["a"]}]},
        "scenes": [
            {"index": 0, "type": "hook", "section_index": None, "narration_text": "Câu 1.", "image_query": "coins"},
            {"index": 1, "type": "outro", "section_index": None, "narration_text": "Câu 2.", "image_query": "banknotes"},
        ],
    }
)


@pytest.fixture(autouse=True)
def mock_everything(monkeypatch):
    # 1) 9router (outline + scenes)
    monkeypatch.setattr(tsg, "_chat_completion", lambda *a, **kw: _VALID_OUTLINE_RAW)

    # 2) Pexels — trả 1 ảnh cho mọi query
    monkeypatch.setattr(pexels_client, "PEXELS_API_KEY", "test-key")

    def pexels_handler(request: httpx.Request) -> httpx.Response:
        if "api.pexels.com/v1/search" in str(request.url):
            return httpx.Response(
                200, json={"photos": [{"src": {"large2x": "https://images.pexels.com/p.jpg"}}]}
            )
        return httpx.Response(200, content=b"fake-jpg-bytes")

    def pexels_client_factory(timeout: float = pexels_client._TIMEOUT):
        return httpx.Client(
            headers={"Authorization": pexels_client.PEXELS_API_KEY},
            transport=httpx.MockTransport(pexels_handler),
            timeout=timeout,
        )

    monkeypatch.setattr(pexels_client, "_client", pexels_client_factory)

    # 3) TTS adapter — ghi file wav giả, không gọi edge-tts thật
    def fake_get_adapter(provider, voice_id):
        def adapter(text, out):
            out.write_bytes(b"fake-wav-bytes")

        return adapter

    monkeypatch.setattr(scene_synthesizer, "_get_adapter", fake_get_adapter)
    monkeypatch.setattr(scene_synthesizer, "get_media_duration", lambda path: 2.5)

    # 4) npx hyperframes render — mock subprocess.run, tự tạo output.mp4 giả
    def fake_subprocess_run(cmd, cwd=None, capture_output=None, text=None, timeout=None, stdin=None):
        from pathlib import Path

        out_idx = cmd.index("--output") + 1
        Path(cmd[out_idx]).write_bytes(b"fake-mp4-bytes")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(hr.subprocess, "run", fake_subprocess_run)


def test_run_generate_pipeline_reaches_done(tmp_jobs_dir):
    job = generate_pipeline.create_generate_job("tổng quan về tiền tệ", job_id="job-gen-e2e")

    generate_pipeline.run_generate_pipeline(job["job_id"])

    from pipeline import read_job

    final = read_job("job-gen-e2e")
    assert final["status"] == "done"
    assert final["error"] is None

    output_path = final["artifacts"]["output_video"]
    assert output_path
    from pathlib import Path

    assert Path(output_path).exists()
    assert Path(output_path).read_bytes() == b"fake-mp4-bytes"


def test_run_generate_pipeline_writes_full_scene_data(tmp_jobs_dir):
    job = generate_pipeline.create_generate_job("chủ đề x", job_id="job-gen-e2e-2")

    generate_pipeline.run_generate_pipeline(job["job_id"])

    from pipeline import read_job

    final = read_job("job-gen-e2e-2")
    with open(final["artifacts"]["scenes"], encoding="utf-8") as f:
        scenes = json.load(f)["scenes"]

    assert len(scenes) == 2
    for scene in scenes:
        assert scene["image_path"] is not None
        assert scene["voice_path"] is not None
        assert scene["duration"] == 2.5


def test_run_generate_pipeline_is_resume_safe_after_failure(tmp_jobs_dir, monkeypatch):
    """Job fail ở bước rendering (subprocess lỗi) → resume chạy lại KHÔNG gọi
    lại 9router/Pexels/TTS lần 2 cho các scene đã xong (chỉ rendering chạy lại)."""
    job = generate_pipeline.create_generate_job("chủ đề y", job_id="job-gen-resume")

    call_count = {"chat": 0}

    def counting_chat(*a, **kw):
        call_count["chat"] += 1
        return _VALID_OUTLINE_RAW

    monkeypatch.setattr(tsg, "_chat_completion", counting_chat)

    # Bước rendering lỗi lần đầu
    def failing_run(cmd, cwd=None, capture_output=None, text=None, timeout=None, stdin=None):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="render lỗi giả lập")

    monkeypatch.setattr(hr.subprocess, "run", failing_run)

    generate_pipeline.run_generate_pipeline(job["job_id"])

    from pipeline import read_job

    failed = read_job("job-gen-resume")
    assert failed["status"] == "failed"
    assert call_count["chat"] == 1  # outline chỉ gọi 1 lần

    # Sửa render thành công rồi resume
    def succeeding_run(cmd, cwd=None, capture_output=None, text=None, timeout=None, stdin=None):
        from pathlib import Path

        out_idx = cmd.index("--output") + 1
        Path(cmd[out_idx]).write_bytes(b"fake-mp4-bytes")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(hr.subprocess, "run", succeeding_run)

    generate_pipeline.run_generate_pipeline(job["job_id"])

    done = read_job("job-gen-resume")
    assert done["status"] == "done"
    # Resume KHÔNG gọi lại outline (đã có outline.json/scenes.json từ trước)
    assert call_count["chat"] == 1


# ─── US4: chốt duyệt outline (T039/T041/T042) ────────────────────────────────


def test_run_generate_pipeline_stops_at_outline_gate_when_supervised(tmp_jobs_dir):
    job = generate_pipeline.create_generate_job(
        "chủ đề có duyệt", job_id="job-gen-supervised", supervised=True
    )

    generate_pipeline.run_generate_pipeline(job["job_id"])

    from pipeline import read_job

    paused = read_job("job-gen-supervised")
    assert paused["status"] == "awaiting_review"
    assert paused["review_gate"] == "outline"
    assert paused["review_gates"]["outline"]["segment_count"] == 2
    # CHƯA chạm tới sourcing_assets/synthesizing/rendering
    with open(paused["artifacts"]["scenes"], encoding="utf-8") as f:
        for scene in json.load(f)["scenes"]:
            assert scene["image_path"] is None
            assert scene["voice_path"] is None


def test_run_generate_pipeline_resumes_with_edited_narration_after_approval(tmp_jobs_dir):
    """T041/T042: sau khi duyệt (mô phỏng đúng việc review_api.py làm — save_
    edits + mark_approved + set status theo NEXT_STATUS_AFTER_GATE), resume
    PHẢI dùng bản narration_text ĐÃ SỬA, không phải bản gốc LLM sinh ra."""
    job = generate_pipeline.create_generate_job(
        "chủ đề có duyệt 2", job_id="job-gen-approve-flow", supervised=True
    )
    generate_pipeline.run_generate_pipeline(job["job_id"])

    from pipeline import _write_job as write_job
    from pipeline import read_job

    paused = read_job("job-gen-approve-flow")
    assert paused["status"] == "awaiting_review"

    # Mô phỏng đúng những gì review_api.py làm khi approve:
    # save_edits() → mark_approved() → set status = NEXT_STATUS_AFTER_GATE
    saved, dropped = gates.save_edits(
        paused, gates.GATE_OUTLINE, [{"index": 0, "text": "Câu đã sửa tay."}]
    )
    assert (saved, dropped) == (2, 0)
    gates.mark_approved(paused, gates.GATE_OUTLINE)
    paused["status"] = gates.NEXT_STATUS_AFTER_GATE[gates.GATE_OUTLINE]
    write_job("job-gen-approve-flow", paused)
    assert paused["status"] == "sourcing_assets"

    # generate_pipeline.py import synthesize_scene bên trong hàm (lazy import)
    # từ module tts.scene_synthesizer — patch TẠI NGUỒN để bắt được lượt gọi
    # thật (mock_everything ở fixture chỉ patch _get_adapter/get_media_duration
    # bên trong scene_synthesizer, không patch chính synthesize_scene).
    narrations_synthesized = []
    orig_synthesize_scene = scene_synthesizer.synthesize_scene

    def spy_synthesize_scene(text, output_path, provider="edge-tts", voice_id=None):
        narrations_synthesized.append(text)
        return orig_synthesize_scene(text, output_path, provider, voice_id)

    scene_synthesizer.synthesize_scene = spy_synthesize_scene
    try:
        generate_pipeline.run_generate_pipeline("job-gen-approve-flow")
    finally:
        scene_synthesizer.synthesize_scene = orig_synthesize_scene

    done = read_job("job-gen-approve-flow")
    assert done["status"] == "done"
    assert "Câu đã sửa tay." in narrations_synthesized
    assert "Câu 1." not in narrations_synthesized  # bản gốc LLM KHÔNG được dùng
