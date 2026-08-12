"""
tests/unit/conftest.py — Fixture dùng chung cho test của 008-supervised-pipeline.

Mọi test MUST chạy trên jobs/ tạm (tmp_path), không được ghi vào jobs/ thật của
người dùng. `pipeline.JOBS_DIR` và `web.backend.jobs_api.JOBS_DIR` là HAI tham
chiếu riêng tới cùng một Path (jobs_api import trực tiếp từ pipeline), nên phải
patch cả hai — patch một chỗ là test đọc/ghi lệch thư mục.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import read_job
from pipeline import _write_job as write_job


@pytest.fixture()
def tmp_jobs_dir(tmp_path, monkeypatch) -> Path:
    """Trỏ JOBS_DIR (pipeline, backend, generate_pipeline — 010) sang
    tmp_path/jobs.

    script_to_video_pipeline.PROJECT_ROOT_DIR bị patch RIÊNG sang
    tmp_path/script-to-video — dự án script-to-video KHÔNG dùng jobs/ nữa
    (tách biệt hoàn toàn khỏi dub/generate) — KHÔNG được để test ghi vào thư
    mục script-to-video/ thật ở repo root (chứa ví dụ viết tay
    film-vs-digital-camera/ của người dùng).
    """
    import generate_pipeline
    import pipeline
    import script_to_video_pipeline
    from web.backend import generate_jobs_api, jobs_api

    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    monkeypatch.setattr(pipeline, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(jobs_api, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(generate_pipeline, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(generate_jobs_api, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(script_to_video_pipeline, "PROJECT_ROOT_DIR", tmp_path / "script-to-video")
    return jobs_dir


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@pytest.fixture()
def make_job(tmp_jobs_dir):
    """
    Tạo jobs/{job_id}/job.json (+ transcript/script tuỳ chọn) rồi trả về job dict.

    Dùng `pipeline.create_job()` để job.json luôn khớp schema thật — test không
    tự dựng dict rời, tránh trôi khỏi hình dạng production.
    """
    import pipeline

    def _make(
        job_id: str = "job-test-001",
        *,
        status: str = "pending",
        script_mode: str = "translate",
        supervised: bool = False,
        review_gate: str | None = None,
        review_gates: dict | None = None,
        transcript_segments: list[dict] | None = None,
        reviewed_segments: list[dict] | None = None,
        script_segments: list[dict] | None = None,
        scene_items: list[dict] | None = None,
        extra: dict | None = None,
    ) -> dict:
        job = pipeline.create_job(
            "https://www.tiktok.com/@u/video/1",
            "tiktok",
            script_mode,
            job_id=job_id,
            supervised=supervised,
        )
        job_dir = tmp_jobs_dir / job_id

        if transcript_segments is not None:
            path = job_dir / "transcript.json"
            _write(path, {"language": "en", "segments": transcript_segments})
            job["artifacts"]["transcript"] = str(path)

        if reviewed_segments is not None:
            path = job_dir / "transcript_reviewed.json"
            _write(
                path,
                {
                    "source": "transcript.json",
                    "resegmented": True,
                    "segments": reviewed_segments,
                },
            )
            job["artifacts"]["transcript_reviewed"] = str(path)

        if script_segments is not None:
            path = job_dir / "script.json"
            _write(
                path,
                {
                    "mode": script_mode,
                    "content": " ".join(
                        s.get("translated_text", "") for s in script_segments
                    ),
                    "target_language": "vi",
                    "segments": script_segments,
                },
            )
            job["artifacts"]["script"] = str(path)

        # 010-topic-video-generation: scenes.json — payload chốt GATE_OUTLINE
        # (data-model.md §3). Không dùng pipeline.create_job() cho job_type=
        # "generate" thật (đó là generate_pipeline.create_generate_job(), test
        # riêng ở test_generate_pipeline.py) — ở đây chỉ cần đủ hình dạng
        # artifacts.scenes để test review/gates.py, gate không quan tâm
        # job_type.
        if scene_items is not None:
            path = job_dir / "scenes.json"
            _write(path, {"source": "outline.json", "scenes": scene_items})
            job["artifacts"]["scenes"] = str(path)

        job["status"] = status
        job["review_gate"] = review_gate
        if review_gates is not None:
            job["review_gates"] = review_gates
        if extra:
            job.update(extra)

        pipeline._write_job(job_id, job)
        return pipeline.read_job(job_id)

    return _make


@pytest.fixture()
def make_generate_job(tmp_jobs_dir):
    """
    Tạo jobs/{job_id}/job.json cho job_type="generate" (010-topic-video-
    generation) qua generate_pipeline.create_generate_job(), rồi cho phép ghi
    đè status/artifacts/scenes để dựng fixture cho từng bước pipeline.
    """
    import generate_pipeline

    def _make(
        job_id: str = "job-gen-test-001",
        *,
        topic: str = "chủ đề thử nghiệm",
        status: str = "pending",
        supervised: bool = False,
        review_gate: str | None = None,
        review_gates: dict | None = None,
        scene_items: list[dict] | None = None,
        extra: dict | None = None,
    ) -> dict:
        job = generate_pipeline.create_generate_job(topic, job_id=job_id, supervised=supervised)
        job_dir = tmp_jobs_dir / job_id

        if scene_items is not None:
            path = job_dir / "scenes.json"
            _write(path, {"source": "outline.json", "scenes": scene_items})
            job["artifacts"]["scenes"] = str(path)
            job["artifacts"]["outline"] = str(job_dir / "outline.json")
            _write(path.parent / "outline.json", {"topic": topic, "search_used": False, "sections": []})

        job["status"] = status
        job["review_gate"] = review_gate
        if review_gates is not None:
            job["review_gates"] = review_gates
        if extra:
            job.update(extra)

        write_job(job_id, job)
        return read_job(job_id)

    return _make


@pytest.fixture()
def make_script_to_video_project(tmp_jobs_dir):
    """
    Tạo script-to-video/{slug}/project.json qua
    script_to_video_pipeline.create_script_to_video_project(), cho phép seed
    sẵn từng phần (part-N/script.json) để dựng fixture cho từng bước pipeline
    mà không cần gọi LLM thật.

    `tmp_jobs_dir` chỉ cần để lấy đúng lượt patch `PROJECT_ROOT_DIR` (fixture
    đó đã patch cả JOBS_DIR lẫn PROJECT_ROOT_DIR) — dự án script-to-video
    KHÔNG nằm trong thư mục jobs/ nó trả về.

    `parts`: dict {part_index: {"screen_items": [...], "status": ...,
    "title": ..., "role": ..., "review_gate": ..., "review_gates": ...,
    "uploaded_video_path": ..., "voice_full_path": ..., "voice_full_duration": ...,
    "continuity_notes": ..., "error": ...}} — phần nào không liệt kê thì
    KHÔNG tạo part-N/script.json (giữ nguyên "chưa sinh kịch bản").
    """
    import script_to_video_pipeline as s2v

    def _make(
        slug: str = "proj-s2v-test-001",
        *,
        premise: str = "chủ đề thử nghiệm",
        num_parts: int = 1,
        target_screens_per_part: int = 3,
        status: str = "pending",
        extra: dict | None = None,
        parts: dict[int, dict] | None = None,
    ) -> dict:
        project = s2v.create_script_to_video_project(
            premise,
            num_parts=num_parts,
            target_screens_per_part=target_screens_per_part,
            slug=slug,
        )
        project["status"] = status
        if extra:
            project.update(extra)
        s2v._write_project(slug, project)

        for part_index, cfg in (parts or {}).items():
            part_dir = s2v.part_dir_for(slug, part_index)
            (part_dir / "video-raw").mkdir(parents=True, exist_ok=True)
            part_data = {
                "part_index": part_index,
                "title": cfg.get("title", f"Phần {part_index + 1}"),
                "role": cfg.get("role", "Hook"),
                "screens": cfg.get("screen_items", []),
                "continuity_notes": cfg.get("continuity_notes", []),
                "uploaded_video_path": cfg.get("uploaded_video_path"),
                "voice_full_path": cfg.get("voice_full_path"),
                "voice_full_duration": cfg.get("voice_full_duration"),
                "status": cfg.get("status", "awaiting_review"),
                "review_gate": cfg.get("review_gate"),
                "review_gates": cfg.get("review_gates", {}),
                "error": cfg.get("error"),
            }
            s2v._write_part(slug, part_index, part_data)

        return s2v.read_project(slug)

    return _make


def _part_screen(
    index: int,
    *,
    duration_seconds: int = 8,
    voice_path: str | None = None,
    voice_duration: float | None = None,
) -> dict:
    """Dựng 1 phần tử `screens[]` mẫu cho test — giữ đủ field bắt buộc của
    part-N/script.json (screen_script_generator.write_part_script())."""
    return {
        "index": index,
        "duration_seconds": duration_seconds,
        "role_label": f"Vai trò screen {index + 1}",
        "ingredients_used": "Nhân vật · Bối cảnh",
        "prompt_detail_md": "## Handoff\n- **START:** ...\n- **END STATE:** ...\n## Nhịp trong clip\n- **0-Ns:** ...",
        "visual_prompt": f"Using the provided images for the character, create a {duration_seconds}-second shot. Dialogue: None.",
        "vi_voiceover_text": f"Lời thoại screen {index + 1}.",
        "voice_path": voice_path,
        "voice_duration": voice_duration,
    }


# ── Dữ liệu mẫu ngắn, dùng lại giữa các test ────────────────────────────────

TRANSCRIPT_SEGMENTS = [
    {
        "start": 0.0,
        "end": 0.62,
        "text": " Hey Mr. Beast,",
        "words": [
            {"word": " Hey", "start": 0.0, "end": 0.3},
            {"word": " Mr.", "start": 0.3, "end": 0.44},
            {"word": " Beast,", "start": 0.52, "end": 0.62},
        ],
    },
    {
        "start": 0.9,
        "end": 1.94,
        "text": " if I give you this camera,",
        "words": [
            {"word": " if", "start": 0.9, "end": 1.0},
            {"word": " I", "start": 1.0, "end": 1.1},
            {"word": " give", "start": 1.1, "end": 1.4},
            {"word": " you", "start": 1.4, "end": 1.6},
            {"word": " this", "start": 1.6, "end": 1.8},
            {"word": " camera,", "start": 1.8, "end": 1.94},
        ],
    },
]

REVIEWED_SEGMENTS = [
    {"start": 0.0, "end": 0.62, "text": "Này Mít Bít,"},
    {"start": 0.9, "end": 1.94, "text": "nếu tôi đưa anh máy ảnh này,"},
]

SCRIPT_SEGMENTS = [
    {
        "start": 0.0,
        "end": 0.62,
        "source_text": "Hey Mr. Beast,",
        "translated_text": "Này MrBeast,",
    },
    {
        "start": 0.9,
        "end": 1.94,
        "source_text": "if I give you this camera,",
        "translated_text": "nếu tôi đưa anh máy ảnh này,",
    },
]

# 010-topic-video-generation: mẫu scenes.json.scenes[] (data-model.md §3) —
# image_path/voice_path/duration còn null vì chưa qua bước sourcing_assets/
# synthesizing khi job đang dừng ở GATE_OUTLINE.
SCENE_ITEMS = [
    {
        "index": 0,
        "narration_text": "Tiền tệ đã tồn tại hàng nghìn năm.",
        "image_query": "ancient coins currency history",
        "image_path": None,
        "voice_path": None,
        "duration": None,
    },
    {
        "index": 1,
        "narration_text": "Ngày nay tiền pháp định thống trị hệ thống tài chính.",
        "image_query": "modern banknotes finance",
        "image_path": None,
        "voice_path": None,
        "duration": None,
    },
]
