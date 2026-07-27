"""
seed_job.py — Tạo sẵn 1 job ở trạng thái `scripting` từ fixture, để các task
verify của 005 chạy được luồng thật (scripting → synthesizing → merging) mà
không cần bước download/ASR.

Vì sao bỏ qua download + ASR: môi trường verify không tải được video (IP
datacenter bị chặn bot check), và cả 2 bước đó nằm NGOÀI phạm vi feature 005 —
005 bắt đầu từ `transcript.json`. Dùng transcript ground-truth còn chặt hơn ASR
thật cho việc đo SC-001 vì mốc khoảng lặng là con số biết trước.

Dùng:
    .venv/bin/python specs/005-natural-pause-dubbing/seed_job.py \
        --fixture pause --job-id verify-us1-edge \
        --script-mode translate --tts-provider edge-tts [--voice-id ...] \
        [--dynamic-captions]

Rồi chạy tiếp luồng thật (lệnh chính xác được in ra ở cuối, copy nguyên văn):
    .venv/bin/python pipeline.py --url https://www.tiktok.com/@fixture/video/0 \
        --script-mode translate --job-id verify-us1-edge

Vì sao URL trông vô nghĩa: `pipeline.py::detect_platform()` chỉ chấp nhận 3 nền
tảng (tiktok/douyin/youtube) và raise ValueError → exit 1 với mọi scheme lạ như
`fixture://`. Job đã seed sẵn ở trạng thái `scripting` nên URL KHÔNG được dùng
tới, chỉ cần qua được cửa validate. Đó là lý do dùng URL tiktok giả thay vì
`fixture://`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = Path(__file__).parent / "fixtures"

sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", choices=["pause", "dense"], required=True)
    ap.add_argument("--job-id", required=True)
    ap.add_argument(
        "--script-mode", choices=["translate", "rewrite", "subtitle"], required=True
    )
    ap.add_argument(
        "--tts-provider", choices=["edge-tts", "lucyai", "router-tts"], default="edge-tts"
    )
    ap.add_argument("--voice-id", default=None)
    ap.add_argument("--dynamic-captions", action="store_true")
    args = ap.parse_args()

    video = FIXTURE_DIR / f"video_{args.fixture}.mp4"
    transcript = FIXTURE_DIR / f"transcript_{args.fixture}.json"
    if not video.exists() or not transcript.exists():
        print(
            f"❌ Thiếu fixture {args.fixture}. Chạy trước: "
            "python specs/005-natural-pause-dubbing/verify_fixtures.py",
            file=sys.stderr,
        )
        return 1

    from pipeline import JOBS_DIR, create_job, read_job, _write_job

    job_dir = JOBS_DIR / args.job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)

    # URL giả nhưng phải qua được `detect_platform()` (chỉ nhận tiktok/douyin/
    # youtube) — job seed ở trạng thái `scripting` nên URL không bao giờ được
    # dùng để tải gì cả, chỉ cần hợp lệ về mặt validate.
    fake_url = f"https://www.tiktok.com/@fixture/video/{args.fixture}"

    create_job(
        url=fake_url,
        platform="tiktok",
        script_mode=args.script_mode,
        job_id=args.job_id,
        dynamic_captions=args.dynamic_captions,
        tts_provider=args.tts_provider,
        voice_id=args.voice_id,
    )

    shutil.copy2(video, job_dir / "source.mp4")
    shutil.copy2(transcript, job_dir / "transcript.json")

    job = read_job(args.job_id)
    job["status"] = "scripting"
    job["artifacts"]["source_video"] = str(job_dir / "source.mp4")
    job["artifacts"]["transcript"] = str(job_dir / "transcript.json")
    _write_job(args.job_id, job)

    meta = json.loads(transcript.read_text(encoding="utf-8"))
    print(
        f"✅ Job {args.job_id} sẵn sàng ở trạng thái 'scripting' "
        f"(fixture={args.fixture}, {len(meta['segments'])} ASR segment, "
        f"mode={args.script_mode}, provider={args.tts_provider})"
    )
    captions_flag = " --dynamic-captions" if args.dynamic_captions else ""
    print(
        f"   Chạy tiếp: .venv/bin/python pipeline.py --url {fake_url} "
        f"--script-mode {args.script_mode} --job-id {args.job_id}{captions_flag}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
