"""
pipeline.py — Orchestrator CLI entrypoint cho Video Repurpose Pipeline.

State machine:
  pending → downloading → transcribing → scripting → synthesizing → merging → done
                                                                           ↘ failed
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from review import gates

# Load .env ở repo root sớm nhất có thể — trước khi script_gen/env_check đọc
# ROUTER_BASE_URL/ROUTER_API_KEY/ROUTER_MODEL qua os.environ (lazy import bên dưới)
load_dotenv()

# ─── Constants ───────────────────────────────────────────────────────────────

JOBS_DIR = Path(__file__).parent / "jobs"

StatusLiteral = Literal[
    "pending",
    "downloading",
    "transcribing",
    # 008-supervised-pipeline: job bật chế độ quản lý đã xong một bước có chốt và
    # đang chờ người dùng phê duyệt. KHÔNG phải đang xử lý, KHÔNG phải lỗi —
    # `review_gate` cho biết đang chờ ở chốt nào.
    "awaiting_review",
    "scripting",
    "synthesizing",
    "merging",
    "done",
    "failed",
]

VALID_TRANSITIONS: dict[str, list[str]] = {
    "pending": ["downloading"],
    # "done" trực tiếp: script_mode="download" chỉ tải rồi dừng, bỏ mọi bước sau
    "downloading": ["transcribing", "done", "failed"],
    "transcribing": ["scripting", "awaiting_review", "failed"],
    "scripting": ["synthesizing", "awaiting_review", "failed"],
    # "scripting" phục vụ 2 đường: duyệt chốt lời thoại, và sinh lại kịch bản ở
    # chốt kịch bản (FR-020). Đường nào hợp lệ do review_api quyết định theo
    # review_gate, không phải bảng này.
    "awaiting_review": ["scripting", "synthesizing", "failed"],
    "synthesizing": ["merging", "failed"],
    "merging": ["done", "failed"],
    "done": [],
    "failed": [],
}


# ─── Job State Management (T004) ─────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_job_id() -> str:
    """
    Sinh job_id mặc định dạng `job-YY-MM-DD-HH-mm-sss` (giờ local máy chạy,
    `sss` = milisecond) để người dùng phân biệt job theo thời điểm tạo thay
    vì UUID ngẫu nhiên không đọc được. Dùng chung cho cả CLI (`pipeline.py`)
    và web UI (`jobs_api.py` không tự sinh job_id riêng, luôn để
    `create_job()` sinh mặc định).
    """
    now = datetime.now()
    return f"job-{now.strftime('%y-%m-%d-%H-%M')}-{now.microsecond // 1000:03d}"


def create_job(
    url: str,
    platform: str,
    script_mode: str,
    job_id: str | None = None,
    dynamic_captions: bool = False,
    tts_provider: str = "edge-tts",
    voice_id: str | None = None,
    keep_original_ranges: str | None = None,
    supervised: bool = False,
    hardsub_blur_enabled: bool = False,
    hardsub_no_ranges: str | None = None,
) -> dict:
    """Tạo job mới và ghi job.json vào jobs/{job_id}/.

    dynamic_captions (003-dubbing-fixes-subtitles, US4): chỉ có ý nghĩa khi
    script_mode là 'translate'/'rewrite'; không áp dụng với 'subtitle' (phụ
    đề đã luôn bật ở mode đó, xem data-model.md).

    tts_provider/voice_id (004-voice-selection-preview): chỉ có ý nghĩa khi
    script_mode là 'translate'/'rewrite'. voice_id=None → bước synthesizing
    tự resolve về giọng mặc định của provider tương ứng.

    supervised (008-supervised-pipeline): bật chế độ quản lý pipeline — dừng chờ
    phê duyệt sau bước tách lời và sau bước sinh kịch bản. Đặt MỘT LẦN lúc tạo
    job và không đổi trong suốt đời job (FR-003).

    hardsub_blur_enabled/hardsub_no_ranges (009-hardsub-blur-reposition): bật
    làm mờ phụ đề gốc + chèn phụ đề mới đúng vị trí. `hardsub_no_ranges` là
    field ĐỘC LẬP với `keep_original_ranges` dù cùng cú pháp chuỗi khoảng —
    KHÔNG dùng chung giá trị (FR-004). Vùng cần mờ do người dùng tự khoanh tại
    chốt kiểm duyệt (không còn OCR tự động — xem hardsub/detector.py), nên bắt
    buộc `supervised=True` khi bật tính năng này.

    Raises:
        ValueError: `hardsub_blur_enabled=True` mà `supervised=False` — không
            có chốt nào để người dùng khoanh vùng thủ công.
    """
    if hardsub_blur_enabled and not supervised:
        raise ValueError(
            "Làm mờ phụ đề gốc yêu cầu bật Quản lý pipeline (cần chốt lời "
            "thoại để khoanh vùng thủ công)"
        )

    jid = job_id or _generate_job_id()
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
        # Khoảng thời gian giữ nguyên audio gốc (nhạc/tiếng hát), không lồng
        # tiếng đè — vd "0:15-0:30, 1:05-end". None/"" = lồng tiếng toàn bộ.
        "keep_original_ranges": keep_original_ranges,
        # 008-supervised-pipeline: chế độ quản lý pipeline (mặc định TẮT — FR-002)
        "supervised": supervised,
        # Chốt đang chờ duyệt: "transcript" | "script" | None. Chỉ khác None khi
        # status == "awaiting_review" (bất biến, xem data-model.md §2).
        "review_gate": None,
        # Lịch sử từng chốt: {"transcript": {reached_at, approved_at, ...}, ...}
        "review_gates": {},
        # 009-hardsub-blur-reposition: làm mờ phụ đề gốc (mặc định TẮT — FR-002)
        "hardsub_blur_enabled": hardsub_blur_enabled,
        # Khoảng KHÔNG có phụ đề gốc — field riêng, KHÔNG dùng chung giá trị với
        # keep_original_ranges dù cùng cú pháp chuỗi (FR-004)
        "hardsub_no_ranges": hardsub_no_ranges,
        "status": "pending",
        "error": None,
        "artifacts": {
            "source_video": None,
            "transcript": None,
            # 008: transcript đã qua review ở chốt lời thoại (KHÔNG có 'words' —
            # xem review/gates.py). Chỉ job supervised có file này.
            "transcript_reviewed": None,
            "script": None,
            "voice_track": None,
            # 005-natural-pause-dubbing: mốc thời gian thực tế từng nhịp trong
            # voice.wav — nguồn của captions.json và của kiểm tra SC-001/SC-002
            "voice_timeline": None,
            "background_audio": None,
            "output_video": None,
            # 009: khung hình đại diện để người dùng khoanh vùng phụ đề gốc,
            # và hardsub_regions.json dựng từ vùng đã khoanh — cả hai chỉ khác
            # None khi hardsub_blur_enabled=true (data-model.md §1)
            "hardsub_frame": None,
            "hardsub_regions": None,
        },
        "warnings": {
            "watermark": False,
            "duration_mismatch": False,
            "background_music_lost": False,
            # 005: có ≥1 nhịp bị thay bằng khoảng lặng do lỗi TTS cục bộ (FR-007)
            "tts_segments_failed": False,
        },
        # 009: kích thước khung hình đại diện + vùng người dùng đã khoanh (toạ
        # độ theo đúng độ phân giải khung hình đó)
        "hardsub_frame_size": None,
        "hardsub_box": None,
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


# ─── Chạy lại từ một bước trước đó (010-rerun-from-step) ────────────────────

# Thứ tự các bước xử lý CHÍNH — không gồm "pending"/"awaiting_review"/"done"/
# "failed" vì đó là trạng thái biên, không phải bước có thể "chạy lại từ đây".
RERUN_STEPS: list[StatusLiteral] = [
    "downloading",
    "transcribing",
    "scripting",
    "synthesizing",
    "merging",
]

# Artifact (job["artifacts"][key]) cần xoá khi chạy lại TỪ đúng bước này —
# bước sau tự động bị xoá theo vì rerun_from_step() lặp qua mọi bước từ target
# trở đi trong RERUN_STEPS.
_RERUN_ARTIFACT_KEYS: dict[str, list[str]] = {
    "downloading": ["source_video"],
    # 009: hardsub_frame/hardsub_regions là artifact phụ của bước transcribing
    # (trích khung hình ngay sau transcribe() — xem run_pipeline())
    "transcribing": ["transcript", "transcript_reviewed", "hardsub_frame", "hardsub_regions"],
    "scripting": ["script"],
    "synthesizing": ["voice_track", "voice_timeline"],
    "merging": ["output_video", "background_audio"],
}

# job["warnings"][key] cần đặt lại False — cảnh báo cũ không còn đúng sau khi
# bước sinh ra nó chạy lại.
_RERUN_WARNING_KEYS: dict[str, list[str]] = {
    "downloading": [],
    "transcribing": ["watermark"],
    "scripting": [],
    "synthesizing": ["tts_segments_failed"],
    "merging": ["duration_mismatch", "background_music_lost"],
}

# Field top-level khác (không thuộc artifacts/warnings) cần đặt lại giá trị mặc định.
_RERUN_EXTRA_KEYS: dict[str, dict] = {
    # 009: vùng đã khoanh (nếu có) và kích thước khung hình cũ không còn khớp
    # khung hình mới sẽ trích lại
    "transcribing": {"hardsub_box": None, "hardsub_frame_size": None},
    "synthesizing": {"tts_failed_segments": 0},
    "merging": {"subtitles_burned": False},
}

# File trên đĩa (jobs/{job_id}/<tên file>) cần xoá — KHÔNG phải mọi bước đều
# ghi file trùng tên cố định (VD merging có thể sinh subtitles.srt HOẶC .ass).
_RERUN_FILE_NAMES: dict[str, list[str]] = {
    "downloading": ["source.mp4"],
    "transcribing": [
        "transcript.json",
        "transcript_reviewed.json",
        "hardsub_frame.png",
        "hardsub_regions.json",
    ],
    "scripting": ["script.json", "script_original.json"],
    "synthesizing": ["voice.wav", "voice_timeline.json", "captions.json"],
    "merging": [
        "output.mp4",
        "background.wav",
        "subtitles.srt",
        "output_captioned.mp4.tmp",
        "source_blurred.mp4",
        "output_blurred.mp4.tmp",
    ],
}

# Thư mục cần xoá sạch khi chạy lại từ bước tương ứng (khác _RERUN_FILE_NAMES:
# đây là cả cây thư mục, không phải file lẻ).
_RERUN_DIR_NAMES: dict[str, list[str]] = {
    # tts/segment_synthesizer.py TỰ CACHE từng nhịp qua file segments/unit_*.wav
    # đã tồn tại (resume sau lỗi, không tính phí TTS lại nếu chạy 2 lần liền
    # với CÙNG giọng/provider) — nhưng cache này không phân biệt theo
    # voice_id/provider, nên rerun-from-step kèm ĐỔI GIỌNG mà không xoá
    # segments/ sẽ âm thầm tái dùng audio cũ, giọng KHÔNG hề đổi dù job.json
    # đã ghi đúng giọng mới (bug thật đã gặp: chọn lại giọng ở web UI xong
    # chạy lại vẫn ra giọng cũ). Phải xoá sạch mỗi lượt rerun từ synthesizing.
    "synthesizing": ["segments"],
    # Ảnh PNG từng dòng phụ đề (merge/text_renderer.py) — sinh lại mỗi lượt burn
    "merging": ["subtitle_frames"],
}


def rerun_from_step(job_id: str, target_step: str) -> dict:
    """
    Đặt job quay lại một bước TRƯỚC ĐÓ để chạy lại — xoá sạch artifact của
    bước đó và MỌI bước sau (job["artifacts"], file trên đĩa, cảnh báo liên
    quan), rồi đặt status = target_step. Chỗ gọi (API) tự lo `start_job()`
    sau khi hàm này trả về.

    Khác với `update_job_status()`: đây là RESET TRỰC TIẾP đi NGƯỢC state
    machine — không đi qua validation của `VALID_TRANSITIONS` (chỉ định nghĩa
    chiều XUÔI), cùng tinh thần với nhánh "resume sau lỗi" đã có trong
    `run_pipeline()`.

    Nếu `target_step` nằm ở/trước bước tách lời hoặc sinh kịch bản, chốt kiểm
    duyệt tương ứng (008) MẤT trạng thái đã duyệt — chốt đó phải qua lại từ đầu
    vì nội dung nó review sẽ được sinh lại.

    Raises:
        ValueError: `target_step` không phải một bước hợp lệ (`RERUN_STEPS`).
    """
    if target_step not in RERUN_STEPS:
        raise ValueError(
            f"Bước không hợp lệ: {target_step}. Chỉ chạy lại được từ: {RERUN_STEPS}"
        )

    job = read_job(job_id)
    job_dir = JOBS_DIR / job_id
    target_index = RERUN_STEPS.index(target_step)
    steps_to_clear = RERUN_STEPS[target_index:]

    for step in steps_to_clear:
        for key in _RERUN_ARTIFACT_KEYS.get(step, []):
            job["artifacts"][key] = None
        for key in _RERUN_WARNING_KEYS.get(step, []):
            job["warnings"][key] = False
        job.update(_RERUN_EXTRA_KEYS.get(step, {}))

    # Chốt đã duyệt (008) mất hiệu lực nếu bước sinh ra nội dung của nó chạy lại
    if target_index <= RERUN_STEPS.index("transcribing"):
        job.get("review_gates", {}).pop("transcript", None)
    if target_index <= RERUN_STEPS.index("scripting"):
        job.get("review_gates", {}).pop("script", None)
    job["review_gate"] = None
    job["error"] = None
    job["status"] = target_step
    _write_job(job_id, job)

    for step in steps_to_clear:
        for filename in _RERUN_FILE_NAMES.get(step, []):
            if "*" in filename:
                for match in job_dir.glob(filename):
                    match.unlink(missing_ok=True)
            else:
                (job_dir / filename).unlink(missing_ok=True)
        for dirname in _RERUN_DIR_NAMES.get(step, []):
            shutil.rmtree(job_dir / dirname, ignore_errors=True)

    return read_job(job_id)


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
        choices=["translate", "rewrite", "subtitle", "download"],
        help=(
            "Chế độ xử lý: 'translate' (dịch lồng tiếng), 'rewrite' (tự soạn "
            "lồng tiếng), 'subtitle' (giữ nguyên âm thanh gốc, chỉ thêm phụ "
            "đề), hoặc 'download' (chỉ tải video, không xử lý gì thêm)"
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
        choices=["edge-tts", "lucyai", "omnivoice"],
        help=(
            "Provider TTS: 'edge-tts' (mặc định, free), 'lucyai' (Vivibe, cần "
            "VIVIBE_API_KEY trong .env), hoặc 'omnivoice' (voice cloning qua "
            "OmniVoice service, cần OMNIVOICE_BASE_URL) — chỉ áp dụng với "
            "--script-mode translate/rewrite — 004-voice-selection-preview"
        ),
    )
    parser.add_argument(
        "--voice-id",
        dest="voice_id",
        default=None,
        help=(
            "Giọng đọc cụ thể (VD 'vi-VN-HoaiMyNeural' cho edge-tts, id giọng "
            "trong tài khoản Vivibe cho lucyai, hoặc voice_id đã nạp trong "
            "OmniVoice service cho omnivoice); để trống → dùng giọng mặc định "
            "hiện có — 004-voice-selection-preview"
        ),
    )
    parser.add_argument(
        "--supervised",
        dest="supervised",
        action="store_true",
        help=(
            "Bật chế độ quản lý pipeline: dừng chờ phê duyệt sau bước tách lời "
            "và sau bước sinh kịch bản. Chỉ có tác dụng với --script-mode "
            "translate/rewrite/subtitle (bị bỏ qua với download). Phê duyệt "
            "thực hiện trên web UI — 008-supervised-pipeline"
        ),
    )
    parser.add_argument(
        "--hardsub-blur",
        dest="hardsub_blur_enabled",
        action="store_true",
        help=(
            "Bật làm mờ phụ đề gốc + chèn phụ đề mới đúng vị trí. Chỉ có tác "
            "dụng với chế độ có hiển thị phụ đề (subtitle, hoặc translate/"
            "rewrite kèm --dynamic-captions); BẮT BUỘC kèm --supervised — "
            "vùng cần mờ do người dùng tự khoanh trên web UI tại chốt lời "
            "thoại, không còn OCR tự động — 009-hardsub-blur-reposition"
        ),
    )
    parser.add_argument(
        "--hardsub-no-ranges",
        dest="hardsub_no_ranges",
        default=None,
        help=(
            "Khoảng thời gian KHÔNG có phụ đề gốc, cú pháp giống "
            "--keep-original-ranges (VD '0:00-0:08, 0:15-end'). Chỉ có ý nghĩa "
            "khi --hardsub-blur được bật — 009-hardsub-blur-reposition"
        ),
    )
    parser.add_argument(
        "--job-id",
        dest="job_id",
        default=None,
        help="job_id đã tồn tại để resume; để trống → tạo job mới",
    )
    return parser.parse_args(argv)


# ─── Chốt kiểm duyệt (008-supervised-pipeline) ───────────────────────────────


def _prepare_transcript_gate(
    jid: str, transcript_path: Path | str, job_dir: Path
) -> tuple[Path, int]:
    """
    Dựng payload chốt lời thoại: cắt lại transcript theo ranh giới câu rồi ghi
    `transcript_reviewed.json` KHÔNG có 'words'.

    Vì sao resegment ở ĐÂY chứ không để bước scripting làm như job thường:
    `resegment_by_sentences()` dựng lại `text` từ mảng 'words', nên nếu chạy SAU
    khi người dùng sửa thì nó ghi đè sạch phần sửa tay. Chạy trước chốt vừa cho
    người dùng review đúng câu mà các bước sau thực sự dùng, vừa khiến bước
    scripting tự bỏ qua resegment (thiếu 'words' → giữ nguyên segment).
    Số lượt gọi LLM không tăng — chỉ dịch chuyển sớm hơn (research.md §3).

    Returns: (đường dẫn transcript_reviewed.json, số câu).
    """
    from script_gen.router_client import _chat_completion
    from script_gen.sentence_segmenter import resegment_by_sentences

    with open(transcript_path, encoding="utf-8") as f:
        segments = json.load(f).get("segments", [])

    # resegment_by_sentences() trả về CHÍNH list đầu vào ở mọi nhánh fallback
    # (tắt qua env, transcript cũ thiếu 'words', LLM lỗi, lệch số từ) — so sánh
    # identity là cách rẻ nhất để biết có cắt lại thật hay không.
    new_segments = resegment_by_sentences(segments, _chat_completion)
    resegmented = new_segments is not segments

    reviewed_path = gates.write_transcript_review(job_dir, new_segments, resegmented)
    print(
        f"[pipeline][{jid}] Chuẩn bị chốt lời thoại: {len(new_segments)} câu "
        f"(cắt lại theo câu: {'có' if resegmented else 'không'})"
    )
    return reviewed_path, len(new_segments)


# ─── Pipeline Orchestrator (T013 — nối luồng sau khi các module sẵn sàng) ──


def run_pipeline(
    url: str,
    script_mode: str,
    job_id: str | None = None,
    dynamic_captions: bool = False,
    tts_provider: str = "edge-tts",
    voice_id: str | None = None,
    supervised: bool = False,
    hardsub_blur_enabled: bool = False,
    hardsub_no_ranges: str | None = None,
) -> None:
    """
    Điều phối pipeline end-to-end.
    Import các module chỉ khi cần để tránh crash khi chưa install dependency.

    dynamic_captions (003-dubbing-fixes-subtitles, US4): chỉ áp dụng khi
    script_mode là 'translate'/'rewrite', bị bỏ qua với 'subtitle'.

    tts_provider/voice_id (004-voice-selection-preview): chỉ áp dụng khi
    script_mode là 'translate'/'rewrite'.

    supervised (008-supervised-pipeline): chỉ là GIÁ TRỊ MẶC ĐỊNH cho job tạo mới
    — job đã tồn tại luôn lấy cờ này từ job.json (xem `active_supervised` bên
    dưới), để resume/retry không truyền lại cờ vẫn giữ đúng chế độ quản lý.

    hardsub_blur_enabled/hardsub_no_ranges (009-hardsub-blur-reposition): cùng
    khuôn mẫu — chỉ là giá trị mặc định cho job tạo mới, giá trị dùng thật MUST
    đọc từ job.json (`active_hardsub_blur` bên dưới).
    """
    # Lazy imports — tránh ImportError crash khi chạy --help
    from asr.transcriber import transcribe
    from clean_video.detector import detect_watermark
    from downloader.f2_client import download_video
    from env_check import run_checks
    from hardsub.detector import extract_representative_frame
    from media_utils import get_media_duration, get_video_frame_size
    from merge.ffmpeg_merge import apply_anti_detect, merge_audio
    from merge.subtitle_burner import apply_hardsub_blur, burn_subtitles, write_srt
    from merge.text_renderer import render_cue_overlays
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
        try:
            job = create_job(
                url,
                platform,
                script_mode,
                dynamic_captions=dynamic_captions,
                tts_provider=tts_provider,
                voice_id=voice_id,
                supervised=supervised,
                hardsub_blur_enabled=hardsub_blur_enabled,
                hardsub_no_ranges=hardsub_no_ranges,
            )
        except ValueError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)
        job_id = job["job_id"]
        print(f"[pipeline] Tạo job mới {job_id}")

    jid = job["job_id"]
    job_dir = JOBS_DIR / jid

    # 008: cờ chế độ quản lý lấy từ job.json, KHÔNG từ tham số hàm — cùng lý do
    # đã sửa cho dynamic_captions (T035 của feature 005): resume/retry mà không
    # gõ lại cờ sẽ âm thầm mất chế độ quản lý và job chạy vọt qua các chốt.
    active_supervised = job.get("supervised", supervised)
    # 009: cùng lý do như active_supervised — đọc từ job.json, không từ tham số
    active_hardsub_blur = job.get("hardsub_blur_enabled", hardsub_blur_enabled)

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
            import download_registry

            dest_path = job_dir / "source.mp4"
            reuse = download_registry.lookup(url)
            if reuse and not (dest_path.exists() and dest_path.stat().st_size > 0):
                # Đã tải video này ở job trước → clone file, khỏi tải lại
                shutil.copy2(reuse["source_video"], dest_path)
                source_path = dest_path
                print(
                    f"[pipeline][{jid}] Tái dùng video đã tải "
                    f"(job {reuse.get('job_id')}), clone thay vì tải lại"
                )
            else:
                # Chọn client phù hợp theo platform
                if platform in ("tiktok", "douyin"):
                    source_path = download_video(url, job_dir, platform)
                else:
                    from downloader.ytdlp_client import download_video_ytdlp
                    source_path = download_video_ytdlp(url, job_dir)

            # Sửa mất tiếng (TikTok/Douyin) — áp dụng cho CẢ file clone lẫn file
            # mới tải: f2/yt-dlp hay lấy bản HEVC (bytevc1) tải về VIDEO-ONLY dù
            # "khai" có aac; chỉ bản h264 mới có tiếng thật. File không có audio
            # → tải lại ép h264. Vẫn câm = video thật sự không tiếng (slideshow)
            # → để nguyên cho transcriber báo đúng.
            from media_utils import has_audio_stream

            if platform in ("tiktok", "douyin") and not has_audio_stream(source_path):
                print(
                    f"[pipeline][{jid}] ⚠ Video không có tiếng (bản HEVC TikTok câm "
                    f"hoặc clone từ file câm cũ), tải lại bằng yt-dlp bản h264..."
                )
                from downloader.ytdlp_client import download_video_ytdlp

                Path(dest_path).unlink(missing_ok=True)
                try:
                    repaired = download_video_ytdlp(url, job_dir, prefer_audio=True)
                    source_path = repaired
                    if not has_audio_stream(source_path):
                        print(f"[pipeline][{jid}] Bản h264 vẫn không có tiếng — video gốc không có âm thanh")
                except Exception as refetch_err:
                    print(f"[pipeline][{jid}] Tải lại bản h264 thất bại: {refetch_err}")
                    # Giữ lại file gì đó để bước sau báo lỗi rõ ràng
                    if not Path(dest_path).exists():
                        source_path = (
                            download_video(url, job_dir, platform)
                            if platform in ("tiktok", "douyin")
                            else download_video_ytdlp(url, job_dir)
                        )

            # Ghi vào sổ để job sau tái dùng (chỉ ghi file CÓ tiếng — tránh lan
            # file câm cũ; giữ nguồn gốc nếu sổ đã có entry file tốt)
            if has_audio_stream(source_path) or platform not in ("tiktok", "douyin"):
                download_registry.register(url, platform, source_path, jid)

            print(f"[pipeline][{jid}] Download xong: {source_path}")

            # script_mode="download": chỉ tải, không xử lý gì thêm → xong luôn
            if script_mode == "download":
                update_job_status(
                    jid,
                    "done",
                    artifacts_update={
                        "source_video": str(source_path),
                        "output_video": str(source_path),
                    },
                )
                print(f"[pipeline][{jid}] Chế độ 'chỉ tải' — hoàn tất, không xử lý thêm")
                sys.exit(0)

            # 010: Anti-Detect Mode (crop micro + color grading + xoá metadata)
            # áp 1 LẦN DUY NHẤT ở đây — TRƯỚC transcribe/hardsub-detect — để
            # mọi toạ độ pixel tính từ source_video về sau (khung hình cho
            # user khoanh vùng hardsub, hardsub_regions.json, burn subtitle,
            # merge) đều nhất quán với video thật sự sẽ xuất ra. Trước đây áp
            # ở bước merge nên lệch toạ độ so với vùng hardsub đã khoanh trên
            # video gốc chưa crop (xem merge/ffmpeg_merge.py::apply_anti_detect).
            anti_detect_path = job_dir / "source_anti_detect.mp4"
            apply_anti_detect(source_path, anti_detect_path)
            source_path = anti_detect_path

            update_job_status(
                jid,
                "transcribing",
                artifacts_update={"source_video": str(source_path)},
            )
        except SystemExit:
            raise
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
            print(f"[pipeline][{jid}] Transcribe xong: {transcript_path}")

            # ── 009: trích khung hình đại diện để người dùng khoanh vùng ─────
            # Chạy theo active_hardsub_blur + script_mode có hiển thị phụ đề
            # (FR-009). Đặt TRƯỚC chốt 1 để job supervised kịp hiển thị khung
            # hình ở chốt (FR-012, research.md §6). Vùng thật sự được ghi ra
            # hardsub_regions.json ở lúc PHÊ DUYỆT chốt lời thoại (xem
            # web/backend/review_api.py), sau khi người dùng đã khoanh xong —
            # không phải ở đây. Lỗi trích khung hình KHÔNG được làm hỏng job —
            # coi như không có khung hình để khoanh (US3, research.md §6).
            hardsub_applicable = script_mode == "subtitle" or (
                script_mode in ("translate", "rewrite")
                and job.get("dynamic_captions", dynamic_captions)
            )
            if active_hardsub_blur and hardsub_applicable:
                try:
                    frame_path, frame_size = extract_representative_frame(
                        job["artifacts"]["source_video"], job_dir
                    )
                    job = read_job(jid)
                    job["artifacts"]["hardsub_frame"] = str(frame_path)
                    job["hardsub_frame_size"] = frame_size
                    _write_job(jid, job)
                except Exception as e:
                    print(f"[pipeline][{jid}] ⚠ Trích khung hình để khoanh vùng phụ đề gốc thất bại: {e}")

            # ── Chốt 1: lời thoại (008, FR-004) ─────────────────────────────
            # `is_approved` là cái chặn dừng lại lần hai sau retry (FR-023).
            if active_supervised and not gates.is_approved(job, gates.GATE_TRANSCRIPT):
                reviewed_path, count = _prepare_transcript_gate(jid, transcript_path, job_dir)
                job = read_job(jid)
                gates.mark_reached(job, gates.GATE_TRANSCRIPT, count)
                job["artifacts"]["transcript"] = str(transcript_path)
                job["artifacts"]["transcript_reviewed"] = str(reviewed_path)
                _write_job(jid, job)
                update_job_status(jid, "awaiting_review")
                print(
                    f"[pipeline][{jid}] ⏸ Dừng chờ duyệt tại chốt lời thoại "
                    f"({count} câu)."
                )
                print(
                    f"[pipeline][{jid}]   Review và phê duyệt trên web UI, hoặc "
                    "chạy lại với --job-id sau khi duyệt."
                )
                return

            update_job_status(
                jid,
                "scripting",
                artifacts_update={"transcript": str(transcript_path)},
            )
        except Exception as e:
            fail_job(jid, "transcribing", e)
            print(f"[ERROR][{jid}] Transcribe thất bại: {e}", file=sys.stderr)
            sys.exit(2)

    # ── Bước 4: Script Generation ────────────────────────────────────────────
    job = read_job(jid)
    if job["status"] == "scripting":
        print(f"[pipeline][{jid}] Bắt đầu scripting (mode={script_mode})...")
        try:
            # 008: job supervised dùng transcript ĐÃ QUA REVIEW làm đầu vào —
            # đây là chỗ FR-012 ("bước sau dùng nội dung đã sửa") thành hiện
            # thực. File đó không có 'words' nên resegment ở bước này tự bỏ qua,
            # giữ nguyên phần sửa tay (research.md §3).
            transcript_for_script = (
                job["artifacts"].get("transcript_reviewed")
                or job["artifacts"]["transcript"]
            )
            if script_mode == "subtitle":
                # US3: dịch theo segment (giữ mốc thời gian ASR gốc) thay vì
                # dịch nguyên khối — không cần source_duration (không TTS)
                script_path = generate_subtitle_script(transcript_for_script, job_dir)
            else:
                # 005: ngân sách ký tự nay tính theo TỪNG nhịp từ mốc ASR bên
                # trong generate_script() — không cần source_duration nữa
                script_path = generate_script(
                    transcript_for_script,
                    job_dir,
                    mode=script_mode,
                )
            print(f"[pipeline][{jid}] Script xong: {script_path}")

            # ── Chốt 2: kịch bản (008, FR-004) ──────────────────────────────
            # Chốt cuối còn sửa được bằng chữ — sau đây mọi thứ thành âm thanh
            # và hình ảnh. `is_approved` chặn dừng lại lần hai sau retry (FR-023).
            if active_supervised and not gates.is_approved(job, gates.GATE_SCRIPT):
                with open(script_path, encoding="utf-8") as f:
                    count = len(json.load(f).get("segments", []))
                job = read_job(jid)
                gates.mark_reached(job, gates.GATE_SCRIPT, count)
                job["artifacts"]["script"] = str(script_path)
                _write_job(jid, job)
                update_job_status(jid, "awaiting_review")
                print(
                    f"[pipeline][{jid}] ⏸ Dừng chờ duyệt tại chốt kịch bản "
                    f"({count} câu)."
                )
                print(
                    f"[pipeline][{jid}]   Review và phê duyệt trên web UI, hoặc "
                    "chạy lại với --job-id sau khi duyệt."
                )
                return

            update_job_status(
                jid,
                "synthesizing",
                artifacts_update={"script": str(script_path)},
            )
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
            # omnivoice bắt buộc người dùng chọn giọng cụ thể (không có
            # "giọng mặc định" hợp lý cho tài khoản/voice-clone riêng của họ)
            active_voice_id = job.get("voice_id") or (
                DEFAULT_VOICE if active_provider == "edge-tts" else None
            )
            # T035 (005): đọc từ job.json khi resume, giống tts_provider/
            # voice_id — trước đó chỉ dùng tham số CLI nên resume --job-id
            # mà quên gõ lại --dynamic-captions sẽ âm thầm mất phụ đề động
            active_dynamic_captions = job.get("dynamic_captions", dynamic_captions)
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
                    dynamic_captions=active_dynamic_captions,
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
            # 009: đọc TOÀN BỘ vùng đã phát hiện (kể cả detected=false/excluded)
            # — apply_hardsub_blur()/render_cue_overlays() tự lọc vùng dùng được.
            hardsub_regions_path = job["artifacts"].get("hardsub_regions")
            all_hardsub_regions: list[dict] = []
            if hardsub_regions_path and Path(hardsub_regions_path).exists():
                with open(hardsub_regions_path, encoding="utf-8") as f:
                    all_hardsub_regions = json.load(f).get("regions", [])
            has_usable_hardsub = any(
                r["detected"] and not r["excluded"] for r in all_hardsub_regions
            )

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
                    burn_source = job["artifacts"]["source_video"]
                    if has_usable_hardsub:
                        # 009: mờ đúng vùng TRƯỚC khi burn phụ đề mới đè lên
                        blurred_path = job_dir / "source_blurred.mp4"
                        apply_hardsub_blur(burn_source, blurred_path, all_hardsub_regions)
                        burn_source = blurred_path
                    # .srt chỉ là file kèm theo để tra cứu — việc burn dùng ảnh
                    # PNG vẽ bằng Pillow (xem merge/text_renderer.py)
                    write_srt(cues, job_dir / "subtitles.srt")
                    overlays = render_cue_overlays(
                        cues,
                        all_hardsub_regions,
                        get_video_frame_size(burn_source),
                        job_dir / "subtitle_frames",
                    )
                    output_path = burn_subtitles(burn_source, overlays, output_path)
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

                # Giữ nguyên audio gốc ở các khoảng nhạc/tiếng hát người dùng chỉ
                # định — phủ audio gốc lên bản đã lồng tiếng trong các khoảng đó
                keep_ranges_raw = job.get("keep_original_ranges")
                if keep_ranges_raw:
                    from merge.ffmpeg_merge import apply_keep_original_ranges, parse_time_ranges

                    total_dur = get_media_duration(job["artifacts"]["source_video"])
                    ranges = parse_time_ranges(keep_ranges_raw, total_dur)
                    if ranges:
                        print(f"[pipeline][{jid}] Giữ nguyên audio gốc ở các khoảng: {ranges}")
                        apply_keep_original_ranges(
                            output_path, job["artifacts"]["source_video"], ranges
                        )

                subtitles_burned = False
                # T035 (005): đọc từ job.json khi resume, cùng lý do như ở
                # bước synthesizing — job đã reload ở dòng 550 nên field mới
                # nhất luôn có sẵn
                active_dynamic_captions = job.get("dynamic_captions", dynamic_captions)
                if active_dynamic_captions:
                    # US4: burn phụ đề động LÊN TRÊN kết quả đã ghép; lỗi ở
                    # đây CHỈ cảnh báo, KHÔNG fail job (nội dung lồng tiếng
                    # vẫn có giá trị dù thiếu caption, khác US3)
                    captions_path = job_dir / "captions.json"
                    if captions_path.exists():
                        try:
                            with open(captions_path, encoding="utf-8") as f:
                                cues = json.load(f)
                            captioned_path = job_dir / "output_captioned.mp4.tmp"
                            burn_source = output_path
                            if has_usable_hardsub:
                                # 009: mờ đúng vùng trên output ĐÃ GHÉP (voice+nhạc
                                # nền), rồi burn phụ đề mới đè lên đúng vị trí
                                blurred_path = job_dir / "output_blurred.mp4.tmp"
                                apply_hardsub_blur(output_path, blurred_path, all_hardsub_regions)
                                burn_source = blurred_path
                            # .srt chỉ là file kèm theo để tra cứu — việc burn dùng
                            # ảnh PNG vẽ bằng Pillow (xem merge/text_renderer.py)
                            write_srt(cues, job_dir / "subtitles.srt")
                            overlays = render_cue_overlays(
                                cues,
                                all_hardsub_regions,
                                get_video_frame_size(burn_source),
                                job_dir / "subtitle_frames",
                            )
                            burn_subtitles(burn_source, overlays, captioned_path)
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
        supervised=args.supervised,
        hardsub_blur_enabled=args.hardsub_blur_enabled,
        hardsub_no_ranges=args.hardsub_no_ranges,
    )


if __name__ == "__main__":
    main()
