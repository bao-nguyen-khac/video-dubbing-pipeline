"""
generate_pipeline.py — Orchestrator RIÊNG cho job_type="generate" (tính năng
"Tạo video từ chủ đề", 010-topic-video-generation). KHÔNG đụng vào
`run_pipeline()` của pipeline.py (luồng dub) — state machine/artifact hoàn
toàn khác nhau (data-model.md §5, plan.md § Summary), chỉ dùng chung field
`job_type` trong cùng jobs/{job_id}/job.json để phân biệt 2 loại job.

State machine:
  pending → outlining → scripting → [awaiting_review nếu supervised, chốt "outline"]
          → sourcing_assets → synthesizing → rendering → done
                                                         ↘ failed
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from pipeline import JOBS_DIR, _generate_job_id, read_job
from pipeline import _write_job as write_job
from review import gates

# Load .env sớm nhất có thể — trước khi script_gen/topic_script_generator đọc
# ROUTER_BASE_URL/ROUTER_API_KEY/ROUTER_AGENT_MODEL qua os.environ
load_dotenv()

# ─── Constants ───────────────────────────────────────────────────────────────

GenerateStatusLiteral = Literal[
    "pending",
    "outlining",
    "scripting",
    "awaiting_review",
    "sourcing_assets",
    "synthesizing",
    "rendering",
    "done",
    "failed",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Job State Management (T009) ─────────────────────────────────────────────


def create_generate_job(
    topic: str,
    job_id: str | None = None,
    supervised: bool = False,
    tts_provider: str = "edge-tts",
    voice_id: str | None = None,
) -> dict:
    """Tạo job "generate" mới và ghi jobs/{job_id}/job.json (data-model.md §1).

    `tts_provider`/`voice_id` được chọn ở cấp job (áp dụng chung cho mọi
    scene) — khác với ghi chú cũ, giờ đã có UI chọn giọng ở GenerateVideoPage
    thay vì luôn mặc định `edge-tts`.

    Raises:
        ValueError: `topic.strip()` rỗng.
    """
    if not topic.strip():
        raise ValueError("Chủ đề không được để trống")

    jid = job_id or _generate_job_id()
    job_dir = JOBS_DIR / jid
    job_dir.mkdir(parents=True, exist_ok=True)

    job = {
        "job_id": jid,
        "job_type": "generate",
        "topic": topic,
        "supervised": supervised,
        "tts_provider": tts_provider,
        "voice_id": voice_id,
        "status": "pending",
        # Chốt đang chờ duyệt: "outline" | None (tái dùng review/gates.py)
        "review_gate": None,
        "review_gates": {},
        "artifacts": {
            "outline": None,
            "scenes": None,
            "output_video": None,
        },
        "error": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }

    write_job(jid, job)
    return job


def generate_status_from_artifacts(job: dict) -> GenerateStatusLiteral:
    """
    Suy ra trạng thái cần resume tới dựa trên artifact đã có trong job.json,
    dùng khi resume job "generate" đã "failed" (data-model.md §5). KHÔNG dùng
    chung với `pipeline.status_from_artifacts()` — thứ tự artifact hoàn toàn
    khác (không có download/ASR, `scenes.json` được CẬP NHẬT DẦN qua 2 bước
    sourcing_assets/synthesizing thay vì chỉ xuất hiện 1 lần).
    """
    artifacts = job.get("artifacts", {})

    if not artifacts.get("outline"):
        return "outlining"
    if not artifacts.get("scenes"):
        return "scripting"

    with open(artifacts["scenes"], encoding="utf-8") as f:
        scenes = json.load(f).get("scenes", [])

    if not all(s.get("image_path") for s in scenes):
        return "sourcing_assets"
    if not all(s.get("voice_path") and s.get("duration") is not None for s in scenes):
        return "synthesizing"
    if not artifacts.get("output_video"):
        return "rendering"
    return "done"


def _fail_generate_job(job_id: str, step: str, exc: Exception) -> None:
    """Đánh dấu job "generate" failed với message lỗi rõ ràng (theo mẫu
    `pipeline.fail_job()`)."""
    try:
        job = read_job(job_id)
        job["status"] = "failed"
        job["error"] = f"[{step}] {type(exc).__name__}: {exc}"
        write_job(job_id, job)
    except Exception:
        pass  # Không để lỗi lan rộng khi handling error


def _read_scenes(scenes_path: str | Path) -> dict:
    with open(scenes_path, encoding="utf-8") as f:
        return json.load(f)


def _write_scenes(scenes_path: str | Path, data: dict) -> None:
    with open(scenes_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── Chạy lại từ một bước trước đó (song song 010-rerun-from-step của luồng
# dub, nhưng state machine khác nên KHÔNG dùng chung pipeline.rerun_from_step)
# ────────────────────────────────────────────────────────────────────────────

# "outlining" không đứng riêng — code run_generate_pipeline() luôn xử lý
# outlining+scripting cùng 1 khối (1 lượt gọi LLM sinh cả outline lẫn scenes),
# nên "chạy lại từ đầu kịch bản" luôn có nghĩa là chạy lại cả 2.
GENERATE_RERUN_STEPS: list[str] = ["scripting", "sourcing_assets", "synthesizing", "rendering"]


def rerun_generate_from_step(job_id: str, target_step: str) -> dict:
    """
    Đặt job "generate" quay lại một bước TRƯỚC ĐÓ để chạy lại — xoá sạch
    artifact của bước đó và mọi bước sau, rồi đặt status = target_step. Chỗ
    gọi (API) tự lo `start_generate_job()` sau khi hàm này trả về.

    Đây là hành động PHÁ HUỶ (xoá kịch bản/ảnh/giọng/video đã có của các bước
    sau) — chỗ gọi PHẢI xác nhận với người dùng trước.

    Raises:
        ValueError: `target_step` không phải một bước hợp lệ (`GENERATE_RERUN_STEPS`).
    """
    if target_step not in GENERATE_RERUN_STEPS:
        raise ValueError(
            f"Bước không hợp lệ: {target_step}. Chỉ chạy lại được từ: {GENERATE_RERUN_STEPS}"
        )

    job = read_job(job_id)
    job_dir = JOBS_DIR / job_id
    scenes_path = job["artifacts"].get("scenes")

    # output_video luôn bị xoá trừ khi chạy lại đúng từ rendering (nó tự ghi
    # đè), vì mọi bước TRƯỚC rendering đều làm scenes.json đổi nội dung.
    (job_dir / "output.mp4").unlink(missing_ok=True)
    job["artifacts"]["output_video"] = None

    if target_step == "scripting":
        job["artifacts"]["outline"] = None
        job["artifacts"]["scenes"] = None
        job.get("review_gates", {}).pop("outline", None)
        job["review_gate"] = None
        (job_dir / "outline.json").unlink(missing_ok=True)
        (job_dir / "scenes.json").unlink(missing_ok=True)
        scenes_dir = job_dir / "scenes"
        if scenes_dir.exists():
            shutil.rmtree(scenes_dir)
    elif target_step in ("sourcing_assets", "synthesizing"):
        scenes_data = _read_scenes(scenes_path)
        for scene in scenes_data["scenes"]:
            scene_dir = job_dir / "scenes" / str(scene["index"])
            if target_step == "sourcing_assets":
                scene["image_path"] = None
                for f in scene_dir.glob("image.*"):
                    f.unlink()
            else:  # synthesizing — sourcing_assets giữ nguyên, chỉ xoá giọng
                scene["voice_path"] = None
                scene["duration"] = None
                (scene_dir / "voice.wav").unlink(missing_ok=True)
        _write_scenes(scenes_path, scenes_data)
    # "rendering": không cần xoá gì thêm — render_scenes_to_video() tự dựng
    # lại hyperframes_project/ từ đầu mỗi lần gọi (shutil.rmtree + copytree).

    job["error"] = None
    job["status"] = target_step
    write_job(job_id, job)
    return job


# ─── Pipeline Orchestrator (T029) ─────────────────────────────────────────────


def run_generate_pipeline(job_id: str) -> None:
    """
    Điều phối generate pipeline end-to-end: outlining+scripting (1 lượt LLM) →
    sourcing_assets (Pexels mỗi scene) → synthesizing (TTS mỗi scene) →
    rendering (HyperFrames) → done/failed. Resume-safe: kiểm tra artifact đã
    có (từng scene trong `scenes.json`) thì bỏ qua, theo mẫu
    `merge_audio()`/`apply_anti_detect()` của `pipeline.py`.

    ⚠️ Chốt duyệt outline (`GATE_OUTLINE`, US4) CHƯA được nối ở đây — xem T039
    (Phase 6). Hàm này hiện LUÔN chạy thẳng, bỏ qua `job["supervised"]`.
    """
    job = read_job(job_id)
    jid = job["job_id"]
    job_dir = JOBS_DIR / jid
    topic = job["topic"]

    # Resume sau lỗi: "failed" là trạng thái cuối, không tự biết bước dở dang
    if job["status"] == "failed":
        resumed_status = generate_status_from_artifacts(job)
        print(f"[generate_pipeline][{jid}] Resume sau lỗi, tiếp tục từ: {resumed_status}")
        job["status"] = resumed_status
        job["error"] = None
        write_job(jid, job)
        job = read_job(jid)

    # ── Bước 1: outlining + scripting (1 lượt gọi LLM, ghi 2 file) ──────────
    if job["status"] in ("pending", "outlining", "scripting"):
        print(f"[generate_pipeline][{jid}] Bắt đầu outlining (topic={topic!r})...")
        try:
            job["status"] = "outlining"
            write_job(jid, job)

            from script_gen.topic_script_generator import write_outline_and_scenes_to_disk

            outline_path, scenes_path = write_outline_and_scenes_to_disk(topic, job_dir)

            job = read_job(jid)
            job["artifacts"]["outline"] = str(outline_path)
            job["artifacts"]["scenes"] = str(scenes_path)
            write_job(jid, job)
            print(f"[generate_pipeline][{jid}] Outline + scenes xong: {scenes_path}")

            # ── Chốt outline (US4/T039, FR-012) ─────────────────────────────
            # `is_approved` chặn dừng lại lần hai sau retry — cùng mẫu
            # `pipeline.run_pipeline()` dùng cho GATE_TRANSCRIPT/GATE_SCRIPT.
            if job.get("supervised") and not gates.is_approved(job, gates.GATE_OUTLINE):
                scene_count = len(_read_scenes(scenes_path)["scenes"])
                job = read_job(jid)
                gates.mark_reached(job, gates.GATE_OUTLINE, scene_count)
                job["status"] = "awaiting_review"
                write_job(jid, job)
                print(
                    f"[generate_pipeline][{jid}] ⏸ Dừng chờ duyệt tại chốt outline "
                    f"({scene_count} scene)."
                )
                return

            job = read_job(jid)
            job["status"] = "sourcing_assets"
            write_job(jid, job)
        except Exception as e:
            _fail_generate_job(jid, "outlining", e)
            print(f"[ERROR][{jid}] Outlining thất bại: {e}")
            return

    # ── Bước 2: sourcing_assets (Pexels mỗi scene) ──────────────────────────
    job = read_job(jid)
    if job["status"] == "sourcing_assets":
        print(f"[generate_pipeline][{jid}] Bắt đầu sourcing_assets...")
        try:
            from assets.pexels_client import search_image

            scenes_path = job["artifacts"]["scenes"]
            scenes_data = _read_scenes(scenes_path)
            for scene in scenes_data["scenes"]:
                if scene.get("image_path"):
                    continue  # resume: scene này đã có ảnh
                scene_dir = job_dir / "scenes" / str(scene["index"])
                image_path = search_image(scene["image_query"], scene_dir)
                scene["image_path"] = str(image_path) if image_path else None
                _write_scenes(scenes_path, scenes_data)

            job = read_job(jid)
            job["status"] = "synthesizing"
            write_job(jid, job)
            print(f"[generate_pipeline][{jid}] sourcing_assets xong ({len(scenes_data['scenes'])} scene)")
        except Exception as e:
            _fail_generate_job(jid, "sourcing_assets", e)
            print(f"[ERROR][{jid}] sourcing_assets thất bại: {e}")
            return

    # ── Bước 3: synthesizing (TTS mỗi scene, đo duration thật) ──────────────
    job = read_job(jid)
    if job["status"] == "synthesizing":
        print(f"[generate_pipeline][{jid}] Bắt đầu synthesizing...")
        try:
            from tts.scene_synthesizer import synthesize_scene

            tts_provider = job.get("tts_provider", "edge-tts")
            voice_id = job.get("voice_id")
            scenes_path = job["artifacts"]["scenes"]
            scenes_data = _read_scenes(scenes_path)
            for scene in scenes_data["scenes"]:
                if scene.get("voice_path") and scene.get("duration") is not None:
                    continue  # resume: scene này đã tổng hợp giọng rồi
                voice_path = job_dir / "scenes" / str(scene["index"]) / "voice.wav"
                duration = synthesize_scene(scene["narration_text"], voice_path, tts_provider, voice_id)
                scene["voice_path"] = str(voice_path)
                scene["duration"] = duration
                _write_scenes(scenes_path, scenes_data)

            job = read_job(jid)
            job["status"] = "rendering"
            write_job(jid, job)
            print(f"[generate_pipeline][{jid}] synthesizing xong")
        except Exception as e:
            _fail_generate_job(jid, "synthesizing", e)
            print(f"[ERROR][{jid}] synthesizing thất bại: {e}")
            return

    # ── Bước 4: rendering (HyperFrames) ─────────────────────────────────────
    job = read_job(jid)
    if job["status"] == "rendering":
        print(f"[generate_pipeline][{jid}] Bắt đầu rendering...")
        try:
            from merge.hyperframes_renderer import render_scenes_to_video

            scenes_data = _read_scenes(job["artifacts"]["scenes"])
            output_path = render_scenes_to_video(scenes_data["scenes"], job_dir)

            job = read_job(jid)
            job["artifacts"]["output_video"] = str(output_path)
            job["status"] = "done"
            write_job(jid, job)
            print(f"[generate_pipeline][{jid}] Hoàn tất: {output_path}")
        except Exception as e:
            _fail_generate_job(jid, "rendering", e)
            print(f"[ERROR][{jid}] rendering thất bại: {e}")
            return
