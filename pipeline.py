"""
pipeline.py — Orchestrator CLI entrypoint cho Video Repurpose Pipeline.

State machine:
  pending → downloading → transcribing → scripting → synthesizing → merging → done
                                                                           ↘ failed
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Load .env ở repo root sớm nhất có thể — trước khi script_gen/env_check đọc
# ROUTER_BASE_URL/ROUTER_API_KEY/ROUTER_MODEL qua os.environ (lazy import bên dưới)
load_dotenv()

# ─── Constants ───────────────────────────────────────────────────────────────

JOBS_DIR = Path(__file__).parent / "jobs"

StatusLiteral = Literal[
    "pending",
    "downloading",
    "transcribing",
    "scripting",
    "synthesizing",
    "merging",
    "done",
    "failed",
]

VALID_TRANSITIONS: dict[str, list[str]] = {
    "pending": ["downloading"],
    "downloading": ["transcribing", "failed"],
    "transcribing": ["scripting", "failed"],
    "scripting": ["synthesizing", "failed"],
    "synthesizing": ["merging", "failed"],
    "merging": ["done", "failed"],
    "done": [],
    "failed": [],
}


# ─── Job State Management (T004) ─────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(
    url: str,
    platform: str,
    script_mode: str,
    job_id: str | None = None,
    dynamic_captions: bool = False,
    tts_provider: str = "edge-tts",
    voice_id: str | None = None,
) -> dict:
    """Tạo job mới và ghi job.json vào jobs/{job_id}/.

    dynamic_captions (003-dubbing-fixes-subtitles, US4): chỉ có ý nghĩa khi
    script_mode là 'translate'/'rewrite'; không áp dụng với 'subtitle' (phụ
    đề đã luôn bật ở mode đó, xem data-model.md).

    tts_provider/voice_id (004-voice-selection-preview): chỉ có ý nghĩa khi
    script_mode là 'translate'/'rewrite'. voice_id=None → bước synthesizing
    tự resolve về giọng mặc định của provider tương ứng.
    """
    jid = job_id or str(uuid.uuid4())
    job_dir = JOBS_DIR / jid
    job_dir.mkdir(parents=True, exist_ok=True)

    job = {
        "job_id": jid,
        "source_url": url,
        "platform": platform,
        "script_mode": script_mode,
        "dynamic_captions": dynamic_captions,
        "tts_provider": tts_provider,
        "voice_id": voice_id,
        "status": "pending",
        "error": None,
        "artifacts": {
            "source_video": None,
            "transcript": None,
            "script": None,
            "voice_track": None,
            # 005-natural-pause-dubbing: mốc thời gian thực tế từng nhịp trong
            # voice.wav — nguồn của captions.json và của kiểm tra SC-001/SC-002
            "voice_timeline": None,
            "background_audio": None,
            "output_video": None,
        },
        "warnings": {
            "watermark": False,
            "duration_mismatch": False,
            "background_music_lost": False,
            # 005: có ≥1 nhịp bị thay bằng khoảng lặng do lỗi TTS cục bộ (FR-007)
            "tts_segments_failed": False,
        },
        # 005: số nhịp lỗi — để UI nói rõ "N câu" thay vì chỉ "có câu lỗi"
        "tts_failed_segments": 0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }

    _write_job(jid, job)
    return job


def read_job(job_id: str) -> dict:
    """Đọc job.json từ đĩa."""
    job_path = JOBS_DIR / job_id / "job.json"
    if not job_path.exists():
        raise FileNotFoundError(f"Job không tồn tại: {job_id}")
    with open(job_path, encoding="utf-8") as f:
        return json.load(f)


def _write_job(job_id: str, job: dict) -> None:
    """Ghi job.json ra đĩa (đọc → sửa → ghi)."""
    job_path = JOBS_DIR / job_id / "job.json"
    job["updated_at"] = _now_iso()
    with open(job_path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)


def update_job_status(
    job_id: str,
    new_status: StatusLiteral,
    error: str | None = None,
    artifacts_update: dict | None = None,
    warnings_update: dict | None = None,
    extra_update: dict | None = None,
) -> dict:
    """
    Cập nhật trạng thái job với validation state transition.
    Raises ValueError nếu transition không hợp lệ.

    extra_update (003-dubbing-fixes-subtitles): merge trực tiếp vào top-level
    job dict — dùng cho field không thuộc artifacts/warnings, VD
    `subtitles_burned` (US3/US4).
    """
    job = read_job(job_id)
    current = job["status"]

    allowed = VALID_TRANSITIONS.get(current, [])
    if new_status != current and new_status not in allowed:
        raise ValueError(
            f"Transition không hợp lệ: {current} → {new_status}. "
            f"Cho phép: {allowed}"
        )

    job["status"] = new_status
    if error is not None:
        job["error"] = error
    if artifacts_update:
        job["artifacts"].update(artifacts_update)
    if warnings_update:
        job["warnings"].update(warnings_update)
    if extra_update:
        job.update(extra_update)

    _write_job(job_id, job)
    return job


def fail_job(job_id: str, step: str, exc: Exception) -> None:
    """Đánh dấu job failed với message lỗi rõ ràng (FR-008)."""
    try:
        job = read_job(job_id)
        current = job["status"]
        allowed = VALID_TRANSITIONS.get(current, [])
        if "failed" in allowed:
            update_job_status(
                job_id,
                "failed",
                error=f"[{step}] {type(exc).__name__}: {exc}",
            )
        # Nếu đã failed/done → không ghi đè
    except Exception:
        pass  # Không để lỗi lan rộng khi handling error


def status_from_artifacts(job: dict) -> StatusLiteral:
    """
    Suy ra trạng thái cần resume tới dựa trên artifact đã có trong job.json.
    Dùng khi resume một job đã "failed" (trạng thái cuối, không tự biết bước dở dang).
    """
    artifacts = job["artifacts"]
    if not artifacts.get("source_video"):
        return "pending"
    if not artifacts.get("transcript"):
        return "transcribing"
    if not artifacts.get("script"):
        return "scripting"
    if not artifacts.get("voice_track"):
        return "synthesizing"
    if not artifacts.get("output_video"):
        return "merging"
    return "done"


# ─── Platform Detection (T005) ───────────────────────────────────────────────


def detect_platform(url: str) -> str:
    """
    Phát hiện nền tảng từ URL.
    Returns: 'tiktok' | 'douyin' | 'youtube'
    Raises: ValueError nếu không nhận dạng được.
    """
    url_lower = url.lower()
    if "tiktok.com" in url_lower or "vm.tiktok.com" in url_lower:
        return "tiktok"
    if "douyin.com" in url_lower or "iesdouyin.com" in url_lower:
        return "douyin"
    if (
        "youtube.com" in url_lower
        or "youtu.be" in url_lower
        or "youtube-nocookie.com" in url_lower
    ):
        return "youtube"
    raise ValueError(
        f"URL không thuộc 3 nền tảng hỗ trợ (tiktok/douyin/youtube): {url}"
    )


# ─── CLI Skeleton (T005) ─────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Video Repurpose Pipeline: download → transcribe → script → TTS → merge",
    )
    parser.add_argument(
        "--url",
        required=True,
        help="URL công khai từ TikTok, Douyin, hoặc YouTube",
    )
    parser.add_argument(
        "--script-mode",
        dest="script_mode",
        required=True,
        choices=["translate", "rewrite", "subtitle"],
        help=(
            "Chế độ xử lý: 'translate' (dịch lồng tiếng), 'rewrite' (tự soạn "
            "lồng tiếng), hoặc 'subtitle' (giữ nguyên âm thanh gốc, chỉ thêm "
            "phụ đề — 003-dubbing-fixes-subtitles)"
        ),
    )
    parser.add_argument(
        "--dynamic-captions",
        dest="dynamic_captions",
        action="store_true",
        help=(
            "Thêm phụ đề động khớp nhịp giọng đọc (chỉ có tác dụng với "
            "--script-mode translate/rewrite; bị bỏ qua với subtitle) — "
            "003-dubbing-fixes-subtitles"
        ),
    )
    parser.add_argument(
        "--tts-provider",
        dest="tts_provider",
        default="edge-tts",
        choices=["edge-tts", "lucyai", "router-tts"],
        help=(
            "Provider TTS: 'edge-tts' (mặc định, free), 'lucyai' (Vivibe, cần "
            "VIVIBE_API_KEY trong .env), hoặc 'router-tts' (giọng Gemini qua "
            "9router, tái dùng ROUTER_API_KEY có sẵn) — chỉ áp dụng với "
            "--script-mode translate/rewrite — 004-voice-selection-preview"
        ),
    )
    parser.add_argument(
        "--voice-id",
        dest="voice_id",
        default=None,
        help=(
            "Giọng đọc cụ thể (VD 'vi-VN-HoaiMyNeural' cho edge-tts, id giọng "
            "trong tài khoản Vivibe cho lucyai, hoặc tên giọng Gemini VD "
            "'Puck' cho router-tts); để trống → dùng giọng mặc định hiện có "
            "— 004-voice-selection-preview"
        ),
    )
    parser.add_argument(
        "--job-id",
        dest="job_id",
        default=None,
        help="UUID của job đã tồn tại để resume; để trống → tạo job mới",
    )
    return parser.parse_args(argv)


# ─── Pipeline Orchestrator (T013 — nối luồng sau khi các module sẵn sàng) ──


def run_pipeline(
    url: str,
    script_mode: str,
    job_id: str | None = None,
    dynamic_captions: bool = False,
    tts_provider: str = "edge-tts",
    voice_id: str | None = None,
) -> None:
    """
    Điều phối pipeline end-to-end.
    Import các module chỉ khi cần để tránh crash khi chưa install dependency.

    dynamic_captions (003-dubbing-fixes-subtitles, US4): chỉ áp dụng khi
    script_mode là 'translate'/'rewrite', bị bỏ qua với 'subtitle'.

    tts_provider/voice_id (004-voice-selection-preview): chỉ áp dụng khi
    script_mode là 'translate'/'rewrite'.
    """
    # Lazy imports — tránh ImportError crash khi chạy --help
    from asr.transcriber import transcribe
    from clean_video.detector import detect_watermark
    from downloader.f2_client import download_video
    from env_check import run_checks
    from media_utils import get_media_duration
    from merge.ffmpeg_merge import merge_audio
    from merge.subtitle_burner import burn_subtitles, write_srt
    from merge.vocal_separator import extract_background_music
    from script_gen.router_client import generate_script, generate_subtitle_script
    from tts.edge_tts_client import DEFAULT_VOICE
    from tts.segment_synthesizer import synthesize_segments

    # 0. Kiểm tra môi trường (T006, FR-008) — fail sớm, rõ ràng nếu thiếu ffmpeg/9router
    if not run_checks():
        print("[ERROR] Môi trường chưa sẵn sàng, xem chi tiết ở trên.", file=sys.stderr)
        sys.exit(1)

    # 1. Detect platform từ URL
    try:
        platform = detect_platform(url)
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Khởi tạo / resume job
    if job_id:
        try:
            job = read_job(job_id)
            print(f"[pipeline] Resume job {job_id} (status={job['status']})")
            # Nếu job chưa bắt đầu download và user truyền URL/platform khác lúc
            # tạo job, đồng bộ lại job.json để tránh lưu source_url/platform cũ
            if job["status"] == "pending" and (
                job["source_url"] != url or job["platform"] != platform
            ):
                job["source_url"] = url
                job["platform"] = platform
                _write_job(job_id, job)
        except FileNotFoundError:
            print(f"[ERROR] Job không tồn tại: {job_id}", file=sys.stderr)
            sys.exit(1)
    else:
        job = create_job(
            url,
            platform,
            script_mode,
            dynamic_captions=dynamic_captions,
            tts_provider=tts_provider,
            voice_id=voice_id,
        )
        job_id = job["job_id"]
        print(f"[pipeline] Tạo job mới {job_id}")

    jid = job["job_id"]
    job_dir = JOBS_DIR / jid

    # Resume sau lỗi: "failed" là trạng thái cuối, không nằm trong luồng dispatch
    # bên dưới — suy ra lại bước cần chạy tiếp dựa trên artifact đã có (đây là một
    # reset chỉnh trực tiếp, không phải transition thường qua update_job_status)
    if job["status"] == "failed":
        resumed_status = status_from_artifacts(job)
        print(f"[pipeline][{jid}] Resume sau lỗi, tiếp tục từ trạng thái: {resumed_status}")
        job["status"] = resumed_status
        job["error"] = None
        _write_job(jid, job)
        job = read_job(jid)

    # ── Bước 1: Download ────────────────────────────────────────────────────
    if job["status"] in ("pending", "downloading"):
        print(f"[pipeline][{jid}] Bắt đầu downloading...")
        try:
            update_job_status(jid, "downloading")
            # Chọn client phù hợp theo platform
            if platform in ("tiktok", "douyin"):
                source_path = download_video(url, job_dir, platform)
            else:
                from downloader.ytdlp_client import download_video_ytdlp
                source_path = download_video_ytdlp(url, job_dir)

            update_job_status(
                jid,
                "transcribing",
                artifacts_update={"source_video": str(source_path)},
            )
            print(f"[pipeline][{jid}] Download xong: {source_path}")
        except Exception as e:
            fail_job(jid, "downloading", e)
            print(f"[ERROR][{jid}] Download thất bại: {e}", file=sys.stderr)
            sys.exit(2)

    # Re-read job để lấy trạng thái mới nhất (resume support)
    job = read_job(jid)

    # ── Bước 2: Detect watermark (clean_video) ──────────────────────────────
    if job["status"] == "transcribing":
        source_path = job["artifacts"]["source_video"]
        try:
            has_wm = detect_watermark(source_path)
            if has_wm:
                print(f"[pipeline][{jid}] ⚠ Cảnh báo: phát hiện watermark/hardsub còn sót")
                update_job_status(jid, "transcribing", warnings_update={"watermark": True})
        except Exception:
            pass  # detector không block pipeline (chỉ warning)

    # ── Bước 3: Transcribe ──────────────────────────────────────────────────
    job = read_job(jid)
    if job["status"] == "transcribing":
        print(f"[pipeline][{jid}] Bắt đầu transcribing...")
        try:
            transcript_path = transcribe(job["artifacts"]["source_video"], job_dir)
            update_job_status(
                jid,
                "scripting",
                artifacts_update={"transcript": str(transcript_path)},
            )
            print(f"[pipeline][{jid}] Transcribe xong: {transcript_path}")
        except Exception as e:
            fail_job(jid, "transcribing", e)
            print(f"[ERROR][{jid}] Transcribe thất bại: {e}", file=sys.stderr)
            sys.exit(2)

    # ── Bước 4: Script Generation ────────────────────────────────────────────
    job = read_job(jid)
    if job["status"] == "scripting":
        print(f"[pipeline][{jid}] Bắt đầu scripting (mode={script_mode})...")
        try:
            if script_mode == "subtitle":
                # US3: dịch theo segment (giữ mốc thời gian ASR gốc) thay vì
                # dịch nguyên khối — không cần source_duration (không TTS)
                script_path = generate_subtitle_script(
                    job["artifacts"]["transcript"], job_dir
                )
            else:
                # 005: ngân sách ký tự nay tính theo TỪNG nhịp từ mốc ASR bên
                # trong generate_script() — không cần source_duration nữa
                script_path = generate_script(
                    job["artifacts"]["transcript"],
                    job_dir,
                    mode=script_mode,
                )
            update_job_status(
                jid,
                "synthesizing",
                artifacts_update={"script": str(script_path)},
            )
            print(f"[pipeline][{jid}] Script xong: {script_path}")
        except Exception as e:
            fail_job(jid, "scripting", e)
            print(f"[ERROR][{jid}] Script generation thất bại: {e}", file=sys.stderr)
            sys.exit(2)

    # ── Bước 5: TTS Synthesize ───────────────────────────────────────────────
    job = read_job(jid)
    if job["status"] == "synthesizing":
        if script_mode == "subtitle":
            # US3: giữ nguyên âm thanh gốc — không TTS, không tách nhạc nền,
            # artifacts.voice_track giữ None có chủ đích (data-model.md)
            print(f"[pipeline][{jid}] Bỏ qua TTS (chế độ Phụ đề tự động)")
            update_job_status(jid, "merging")
        else:
            active_provider = job.get("tts_provider", "edge-tts")
            # Chỉ edge-tts có giọng mặc định sẵn (2 giọng cố định); lucyai/
            # router-tts bắt buộc người dùng chọn giọng cụ thể (không có
            # "giọng mặc định" hợp lý cho tài khoản/catalog riêng của họ)
            active_voice_id = job.get("voice_id") or (
                DEFAULT_VOICE if active_provider == "edge-tts" else None
            )
            print(f"[pipeline][{jid}] Bắt đầu synthesizing (provider={active_provider}, voice={active_voice_id})...")
            try:
                source_duration = get_media_duration(job["artifacts"]["source_video"])

                # Job tạo trước feature 005 resume thẳng vào bước này có
                # script.json không chia nhịp — sinh lại thay vì fail
                # (research.md §7; generate_script() tự nhận ra file cũ)
                with open(job["artifacts"]["script"], encoding="utf-8") as f:
                    has_segments = bool(json.load(f).get("segments"))
                if not has_segments:
                    print(f"[pipeline][{jid}] script.json cũ chưa chia nhịp, sinh lại kịch bản...")
                    generate_script(
                        job["artifacts"]["transcript"], job_dir, mode=script_mode
                    )

                # 005: tổng hợp theo từng nhịp + ghép timeline có khoảng lặng
                # thật, dùng chung 1 cơ chế cho cả 3 provider (FR-001..FR-005)
                voice_path, duration, timeline = synthesize_segments(
                    job["artifacts"]["script"],
                    job_dir,
                    provider=active_provider,
                    voice_id=active_voice_id,
                    dynamic_captions=dynamic_captions,
                )

                failed_count = timeline.get("failed_count", 0)
                total_count = len(timeline.get("segments", []))

                update_job_status(
                    jid,
                    "merging",
                    artifacts_update={
                        "voice_track": str(voice_path),
                        "voice_timeline": str(job_dir / "voice_timeline.json"),
                    },
                    warnings_update={"tts_segments_failed": failed_count > 0},
                    extra_update={"tts_failed_segments": failed_count},
                )
                print(
                    f"[pipeline][{jid}] TTS xong: {voice_path} ({duration:.1f}s, "
                    f"video gốc {source_duration:.1f}s, {failed_count}/{total_count} nhịp lỗi)"
                )
                if failed_count:
                    # FR-006: lỗi cục bộ KHÔNG fail job — chỉ cảnh báo rõ ràng
                    print(
                        f"[pipeline][{jid}] ⚠ Cảnh báo: {failed_count} nhịp bị lỗi "
                        "tổng hợp giọng đọc, đã thay bằng khoảng lặng"
                    )
            except Exception as e:
                fail_job(jid, "synthesizing", e)
                print(f"[ERROR][{jid}] TTS thất bại: {e}", file=sys.stderr)
                sys.exit(2)

    # ── Bước 6: Merge (kèm tách/giữ nhạc nền trước khi ghép, FR-009) ─────────
    job = read_job(jid)
    if job["status"] == "merging":
        print(f"[pipeline][{jid}] Bắt đầu merging (ffmpeg)...")
        try:
            if script_mode == "subtitle":
                # US3: burn phụ đề trực tiếp lên source.mp4, audio giữ nguyên
                # 100% — lỗi burn KHÔNG có fallback, để lan lên fail_job()
                # (FR-003: đây là toàn bộ giá trị của mode này, khác US4)
                output_path = job_dir / "output.mp4"
                if not (output_path.exists() and output_path.stat().st_size > 0):
                    with open(job["artifacts"]["script"], encoding="utf-8") as f:
                        script_data = json.load(f)
                    cues = [
                        {"start": c["start"], "end": c["end"], "text": c["translated_text"]}
                        for c in script_data.get("segments", [])
                    ]
                    srt_path = write_srt(cues, job_dir / "subtitles.srt")
                    output_path = burn_subtitles(
                        job["artifacts"]["source_video"], srt_path, output_path
                    )
                update_job_status(
                    jid,
                    "done",
                    artifacts_update={"output_video": str(output_path)},
                    extra_update={"subtitles_burned": True},
                )
                print(f"[pipeline][{jid}] Merge xong (burn phụ đề): {output_path}")
            else:
                background_path = extract_background_music(job["artifacts"]["source_video"], job_dir)
                if background_path is None:
                    print(f"[pipeline][{jid}] ⚠ Không tách được nhạc nền, audio gốc sẽ bị mute hoàn toàn")

                output_path, duration_mismatch, background_kept = merge_audio(
                    job["artifacts"]["source_video"],
                    job["artifacts"]["voice_track"],
                    job_dir,
                    background_audio_path=background_path,
                )
                subtitles_burned = False
                if dynamic_captions:
                    # US4: burn phụ đề động LÊN TRÊN kết quả đã ghép; lỗi ở
                    # đây CHỈ cảnh báo, KHÔNG fail job (nội dung lồng tiếng
                    # vẫn có giá trị dù thiếu caption, khác US3)
                    captions_path = job_dir / "captions.json"
                    if captions_path.exists():
                        try:
                            with open(captions_path, encoding="utf-8") as f:
                                cues = json.load(f)
                            srt_path = write_srt(cues, job_dir / "subtitles.srt")
                            captioned_path = job_dir / "output_captioned.mp4.tmp"
                            burn_subtitles(output_path, srt_path, captioned_path)
                            captioned_path.replace(output_path)
                            subtitles_burned = True
                        except Exception as e:
                            print(f"[pipeline][{jid}] ⚠ Burn phụ đề động thất bại, giữ output không caption: {e}")
                    else:
                        print(f"[pipeline][{jid}] ⚠ Không tìm thấy captions.json, bỏ qua phụ đề động")

                update_job_status(
                    jid,
                    "done",
                    artifacts_update={
                        "output_video": str(output_path),
                        "background_audio": str(background_path) if background_path else None,
                    },
                    warnings_update={
                        "duration_mismatch": duration_mismatch,
                        "background_music_lost": not background_kept,
                    },
                    extra_update={"subtitles_burned": subtitles_burned},
                )
                if duration_mismatch:
                    print(f"[pipeline][{jid}] ⚠ Cảnh báo: lệch thời lượng audio/video")
                print(f"[pipeline][{jid}] Merge xong: {output_path} (nhạc nền: {'giữ' if background_kept else 'mất'})")
        except Exception as e:
            fail_job(jid, "merging", e)
            print(f"[ERROR][{jid}] Merge thất bại: {e}", file=sys.stderr)
            sys.exit(2)

    # ── Hoàn tất ─────────────────────────────────────────────────────────────
    job = read_job(jid)
    if job["status"] == "done":
        output = job["artifacts"]["output_video"]
        print(f"\n✅ Hoàn tất! Output: {Path(output).resolve()}")
        sys.exit(0)
    elif job["status"] == "failed":
        print(f"\n❌ Job {jid} đã failed: {job['error']}", file=sys.stderr)
        sys.exit(2)
    else:
        print(f"[pipeline][{jid}] Đã resume, trạng thái hiện tại: {job['status']}")


# ─── Entrypoint ──────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()
    run_pipeline(
        url=args.url,
        script_mode=args.script_mode,
        job_id=args.job_id,
        dynamic_captions=args.dynamic_captions,
        tts_provider=args.tts_provider,
        voice_id=args.voice_id,
    )


if __name__ == "__main__":
    main()
