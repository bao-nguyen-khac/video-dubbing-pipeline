"""
publish/store.py — Lưu/đọc trạng thái đăng bài bằng file JSON.

Hai loại state (data-model.md §1, §3):
  - jobs/{job_id}/publishes/{attempt_id}.json — mỗi lượt đăng 1 file, nằm cạnh
    artifact của job đã sinh ra video ⇒ audit được cùng chỗ với job.
  - publish_data/state.json — profile_id Zernio + blocklist kênh đã ngắt.

Ghi file kiểu atomic (file tạm + os.replace) để runner nền và request HTTP đọc
cùng lúc không bao giờ thấy JSON dở dang.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pipeline import JOBS_DIR

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "publish_data"
STATE_PATH = STATE_DIR / "state.json"

# Trạng thái chưa kết thúc — dùng để chặn đăng trùng (FR-009)
ACTIVE_STATUSES = ("pending", "publishing")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise


# ── Publish attempts ────────────────────────────────────────────────────────


def publishes_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id / "publishes"


def attempt_path(job_id: str, attempt_id: str) -> Path:
    return publishes_dir(job_id) / f"{attempt_id}.json"


def create_attempt(
    job_id: str,
    platform: str,
    account_id: str,
    account_label: str,
    title: str,
) -> dict:
    """Tạo file attempt ở trạng thái 'pending' (ghi TRƯỚC khi gọi Zernio)."""
    attempt = {
        "attempt_id": str(uuid.uuid4()),
        "job_id": job_id,
        "platform": platform,
        "account_id": account_id,
        "account_label": account_label,
        "title": title,
        "status": "pending",
        "error": None,
        "error_kind": None,
        "provider_post_id": None,
        "post_url": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    _write_json_atomic(attempt_path(job_id, attempt["attempt_id"]), attempt)
    return attempt


def read_attempt(job_id: str, attempt_id: str) -> dict:
    path = attempt_path(job_id, attempt_id)
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy lượt đăng {attempt_id}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def update_attempt(job_id: str, attempt_id: str, **fields) -> dict:
    """Cập nhật một phần attempt; luôn refresh updated_at."""
    attempt = read_attempt(job_id, attempt_id)
    attempt.update(fields)
    attempt["updated_at"] = _now()
    _write_json_atomic(attempt_path(job_id, attempt_id), attempt)
    return attempt


def iter_attempts(job_id: str | None = None):
    """Yield mọi attempt đọc được (bỏ qua file hỏng), không sắp xếp."""
    if not JOBS_DIR.exists():
        return
    job_dirs = [JOBS_DIR / job_id] if job_id else sorted(JOBS_DIR.iterdir())
    for job_dir in job_dirs:
        pub_dir = job_dir / "publishes"
        if not pub_dir.is_dir():
            continue
        for attempt_file in sorted(pub_dir.glob("*.json")):
            try:
                with open(attempt_file, encoding="utf-8") as f:
                    yield json.load(f)
            except (json.JSONDecodeError, OSError):
                continue


def list_attempts(job_id: str | None = None) -> list[dict]:
    """Attempt mới nhất trước (FR-010)."""
    attempts = list(iter_attempts(job_id))
    attempts.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    return attempts


def find_attempt(attempt_id: str) -> dict | None:
    for attempt in iter_attempts():
        if attempt.get("attempt_id") == attempt_id:
            return attempt
    return None


def find_active_attempt(job_id: str, platform: str) -> dict | None:
    """
    Lượt đăng chưa kết thúc của cùng job + nền tảng (FR-009).

    Luôn quét file thay vì giữ biến in-memory — backend restart giữa chừng
    không được làm mất khoá chống trùng (cùng lý do find_running_job_id()).
    """
    for attempt in iter_attempts(job_id):
        if attempt.get("platform") == platform and attempt.get("status") in ACTIVE_STATUSES:
            return attempt
    return None


def published_platforms(job_id: str) -> list[str]:
    """Các nền tảng job này đã đăng thành công (data-model.md §4)."""
    return sorted(
        {a["platform"] for a in iter_attempts(job_id) if a.get("status") == "success"}
    )


# ── Local publish state ─────────────────────────────────────────────────────


def read_state() -> dict:
    if not STATE_PATH.exists():
        return {"profile_id": None, "disconnected_account_ids": [], "updated_at": None}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"profile_id": None, "disconnected_account_ids": [], "updated_at": None}
    state.setdefault("profile_id", None)
    state.setdefault("disconnected_account_ids", [])
    return state


def write_state(state: dict) -> dict:
    state["updated_at"] = _now()
    _write_json_atomic(STATE_PATH, state)
    return state


def set_profile_id(profile_id: str) -> None:
    state = read_state()
    state["profile_id"] = profile_id
    write_state(state)


def block_account(account_id: str) -> None:
    """Ngắt kết nối phía hệ thống này (FR-011)."""
    state = read_state()
    if account_id not in state["disconnected_account_ids"]:
        state["disconnected_account_ids"].append(account_id)
        write_state(state)


def unblock_account(account_id: str) -> None:
    """Gỡ chặn khi người dùng liên kết lại kênh."""
    state = read_state()
    if account_id in state["disconnected_account_ids"]:
        state["disconnected_account_ids"].remove(account_id)
        write_state(state)


def is_blocked(account_id: str) -> bool:
    return account_id in read_state()["disconnected_account_ids"]
