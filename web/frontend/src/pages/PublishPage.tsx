// pages/PublishPage.tsx — Tab "Đăng video" (006-publish-video-tab).
//
// 3 khu vực: kết nối kênh (FR-005/FR-006/FR-011), form đăng (FR-002/FR-003/
// FR-004/FR-007), lịch sử lượt đăng (FR-010).

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  createPublish,
  disconnectChannel,
  getAttempt,
  listAttempts,
  listConnections,
  listPublishableVideos,
  startConnect,
  type ChannelConnection,
  type PublishAttempt,
  type PublishableVideo,
} from "../api/client";
import AppShell from "../components/AppShell";
import Callout from "../components/Callout";
import { IconInbox } from "../components/Icon";
import { PLATFORM_LABELS, absoluteTime, relativeTime } from "../lib/labels";

// Chặng 1 chỉ bàn giao TikTok (plan.md → Thứ tự bàn giao); YouTube Shorts thêm
// ở Phase 4 — thêm 1 dòng vào mảng này là đủ ở phía UI.
const PLATFORMS = [{ value: "tiktok", label: "TikTok" }];

const ATTEMPT_POLL_MS = 2000;
const ACTIVE_STATUSES = new Set(["pending", "publishing"]);

const ATTEMPT_STATUS_LABELS: Record<string, string> = {
  pending: "Đang chuẩn bị",
  publishing: "Đang đăng",
  success: "Thành công",
  failed: "Thất bại",
};

function attemptBadgeKind(status: string): string {
  if (status === "success") return "done";
  if (status === "failed") return "failed";
  return "running";
}

export default function PublishPage() {
  const [videos, setVideos] = useState<PublishableVideo[] | null>(null);
  const [connections, setConnections] = useState<ChannelConnection[] | null>(null);
  const [attempts, setAttempts] = useState<PublishAttempt[]>([]);

  const [platform, setPlatform] = useState(PLATFORMS[0].value);
  const [jobId, setJobId] = useState("");
  const [accountId, setAccountId] = useState("");
  const [title, setTitle] = useState("");

  const [configError, setConfigError] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [current, setCurrent] = useState<PublishAttempt | null>(null);

  const pollRef = useRef<number | null>(null);

  const refreshConnections = useCallback(async () => {
    try {
      const res = await listConnections();
      setConnections(res.connections);
      setConnectionError(null);
      setConfigError(null);
    } catch (err) {
      setConnections([]);
      if (err instanceof ApiError && err.status === 503) {
        setConfigError(err.message);
      } else {
        setConnectionError(
          err instanceof ApiError ? err.message : "Không tải được danh sách kênh",
        );
      }
    }
  }, []);

  const refreshAttempts = useCallback(async () => {
    try {
      const res = await listAttempts();
      setAttempts(res.attempts);
    } catch {
      // Lịch sử lỗi không nên chặn thao tác đăng
    }
  }, []);

  useEffect(() => {
    listPublishableVideos()
      .then((res) => setVideos(res.videos))
      .catch(() => setVideos([]));
    refreshConnections();
    refreshAttempts();
  }, [refreshConnections, refreshAttempts]);

  // Người dùng cấp quyền ở tab khác rồi quay lại — làm mới danh sách kênh
  useEffect(() => {
    function onFocus() {
      refreshConnections();
    }
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refreshConnections]);

  function stopPolling() {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  useEffect(() => stopPolling, []);

  function startPolling(attemptId: string) {
    stopPolling();
    pollRef.current = window.setInterval(async () => {
      try {
        const attempt = await getAttempt(attemptId);
        setCurrent(attempt);
        if (!ACTIVE_STATUSES.has(attempt.status)) {
          stopPolling();
          refreshAttempts();
          if (attempt.status === "success") {
            listPublishableVideos()
              .then((res) => setVideos(res.videos))
              .catch(() => undefined);
          }
        }
      } catch {
        stopPolling();
      }
    }, ATTEMPT_POLL_MS);
  }

  const platformConnections = (connections ?? []).filter((c) => c.platform === platform);
  const usableConnections = platformConnections.filter((c) => c.status === "connected");
  const selectedVideo = videos?.find((v) => v.job_id === jobId) ?? null;
  const publishing = current !== null && ACTIVE_STATUSES.has(current.status);

  async function handleConnect() {
    setConnectionError(null);
    try {
      const { authorize_url } = await startConnect(platform, window.location.href);
      window.open(authorize_url, "_blank", "noopener");
      setNotice(
        "Đã mở trang cấp quyền ở tab mới. Hoàn tất trên nền tảng rồi quay lại đây — danh sách kênh sẽ tự làm mới.",
      );
    } catch (err) {
      setConnectionError(
        err instanceof ApiError ? err.message : "Không lấy được liên kết cấp quyền",
      );
    }
  }

  async function handleDisconnect(connection: ChannelConnection) {
    setConnectionError(null);
    try {
      const res = await disconnectChannel(connection.account_id);
      if (res.warning) setConnectionError(res.warning);
      if (accountId === connection.account_id) setAccountId("");
      await refreshConnections();
    } catch (err) {
      setConnectionError(
        err instanceof ApiError ? err.message : "Ngắt kết nối kênh thất bại",
      );
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setNotice(null);

    if (!jobId) {
      setFormError("Hãy chọn 1 video đã xử lý xong");
      return;
    }
    if (!accountId) {
      setFormError("Hãy chọn kênh để đăng");
      return;
    }
    if (!title.trim()) {
      setFormError("Tiêu đề là bắt buộc");
      return;
    }

    setSubmitting(true);
    try {
      const { attempt_id } = await createPublish(jobId, platform, accountId, title.trim());
      const attempt = await getAttempt(attempt_id);
      setCurrent(attempt);
      startPolling(attempt_id);
      refreshAttempts();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setFormError(`${err.message} — chờ lượt đăng đó xong rồi thử lại.`);
      } else {
        setFormError(err instanceof ApiError ? err.message : "Không tạo được lượt đăng");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell narrow>
      <div className="page-head">
        <h1>Đăng video</h1>
        <p className="page-head__lead">
          Đăng thẳng video đã xử lý lên kênh của bạn. Bài đăng là công khai ngay và
          không sửa/xoá được từ đây.
        </p>
      </div>

      {configError && (
        <Callout tone="warning" title="Chưa cấu hình dịch vụ đăng bài">
          {configError}
        </Callout>
      )}

      {!configError && (
        <>
          {/* ── Kết nối kênh ─────────────────────────────────────────── */}
          <div className="card">
            <div className="card__title">Kênh đã liên kết</div>

            {connectionError && (
              <Callout tone="error" title="Lỗi kết nối kênh">
                {connectionError}
              </Callout>
            )}

            {connections === null && <div className="skeleton skeleton--row" />}

            {connections !== null && platformConnections.length === 0 && (
              <p className="field__hint">
                Chưa liên kết kênh {PLATFORM_LABELS[platform] ?? platform} nào.
              </p>
            )}

            {platformConnections.map((connection) => (
              <div key={connection.account_id} className="job-row">
                <div className="job-row__url">{connection.label}</div>
                <div className="job-row__meta">
                  <span>{PLATFORM_LABELS[connection.platform] ?? connection.platform}</span>
                  <span>·</span>
                  <span>
                    {connection.status === "connected" && "Đang hoạt động"}
                    {connection.status === "expired" && "Hết hạn quyền truy cập"}
                    {connection.status === "disconnected" && "Đã ngắt kết nối"}
                  </span>
                </div>
                <div className="job-row__status">
                  <button
                    type="button"
                    className="btn btn--subtle"
                    onClick={() => handleDisconnect(connection)}
                    disabled={connection.status === "disconnected"}
                  >
                    Ngắt kết nối
                  </button>
                </div>
              </div>
            ))}

            <div className="result__actions">
              <button type="button" className="btn btn--ghost" onClick={handleConnect}>
                Kết nối kênh {PLATFORM_LABELS[platform] ?? platform}
              </button>
            </div>

            <p className="field__hint">
              Ngắt kết nối ở đây chặn mọi lượt đăng tới kênh đó. Muốn thu hồi quyền
              hoàn toàn, làm thêm trong cài đặt ứng dụng của nền tảng.
            </p>
          </div>

          {/* ── Form đăng ────────────────────────────────────────────── */}
          <form className="card" onSubmit={handleSubmit}>
            <div className="card__title">Đăng video mới</div>

            <div className="field">
              <label className="field__label" htmlFor="publish-platform">
                Nền tảng
              </label>
              <select
                id="publish-platform"
                className="select"
                value={platform}
                onChange={(e) => {
                  setPlatform(e.target.value);
                  setAccountId("");
                }}
              >
                {PLATFORMS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label className="field__label" htmlFor="publish-video">
                Video đã xử lý xong
              </label>
              <select
                id="publish-video"
                className="select"
                value={jobId}
                onChange={(e) => setJobId(e.target.value)}
              >
                <option value="">— Chọn video —</option>
                {(videos ?? []).map((video) => (
                  <option key={video.job_id} value={video.job_id}>
                    {video.job_id} · {video.duration_seconds}s
                    {video.already_published_to.length > 0
                      ? ` · đã đăng: ${video.already_published_to.join(", ")}`
                      : ""}
                  </option>
                ))}
              </select>
              {videos !== null && videos.length === 0 && (
                <p className="field__hint">
                  Chưa có video nào xử lý xong. <Link to="/">Tạo job mới</Link> trước đã.
                </p>
              )}
              {selectedVideo && selectedVideo.already_published_to.includes(platform) && (
                <p className="field__hint">
                  Video này đã từng đăng lên {PLATFORM_LABELS[platform] ?? platform}.
                </p>
              )}
            </div>

            <div className="field">
              <label className="field__label" htmlFor="publish-account">
                Kênh đích
              </label>
              <select
                id="publish-account"
                className="select"
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
              >
                <option value="">— Chọn kênh —</option>
                {usableConnections.map((connection) => (
                  <option key={connection.account_id} value={connection.account_id}>
                    {connection.label}
                  </option>
                ))}
              </select>
              {connections !== null && usableConnections.length === 0 && (
                <p className="field__hint">
                  Chưa có kênh nào dùng được — hãy kết nối kênh ở phần trên.
                </p>
              )}
            </div>

            <div className="field">
              <label className="field__label" htmlFor="publish-title">
                Tiêu đề (bắt buộc)
              </label>
              <input
                id="publish-title"
                className="input"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Tiêu đề hiển thị trên bài đăng"
              />
            </div>

            {formError && (
              <Callout tone="error" title="Chưa đăng được">
                {formError}
              </Callout>
            )}

            <button
              type="submit"
              className="btn btn--primary btn--block"
              disabled={submitting || publishing}
            >
              {publishing ? "Đang đăng..." : submitting ? "Đang gửi..." : "Đăng"}
            </button>
          </form>

          {notice && <Callout tone="info">{notice}</Callout>}

          {/* ── Tiến trình lượt đăng hiện tại ─────────────────────────── */}
          {current && (
            <div className="card">
              <div className="card__title">Lượt đăng hiện tại</div>
              <p>
                <span className={`badge badge--${attemptBadgeKind(current.status)}`}>
                  <span className="badge__dot" />
                  {ATTEMPT_STATUS_LABELS[current.status] ?? current.status}
                </span>{" "}
                {current.title}
              </p>

              {current.status === "success" && current.post_url && (
                <Callout tone="success" title="Đã đăng công khai">
                  <a href={current.post_url} target="_blank" rel="noreferrer">
                    Xem bài đăng trên {PLATFORM_LABELS[current.platform] ?? current.platform}
                  </a>
                </Callout>
              )}

              {current.status === "failed" && (
                <Callout tone="error" title="Đăng thất bại">
                  {current.error}
                  {current.error_kind === "auth_expired" && (
                    <div className="result__actions">
                      <button type="button" className="btn btn--ghost" onClick={handleConnect}>
                        Liên kết lại kênh
                      </button>
                    </div>
                  )}
                </Callout>
              )}
            </div>
          )}

          {/* ── Lịch sử ──────────────────────────────────────────────── */}
          <div className="card">
            <div className="card__title">Lịch sử đăng</div>

            {attempts.length === 0 && (
              <div className="empty">
                <IconInbox className="empty__icon" />
                <div className="empty__title">Chưa có lượt đăng nào</div>
              </div>
            )}

            {attempts.map((attempt) => (
              <div key={attempt.attempt_id} className="job-row">
                <div className="job-row__url" title={attempt.title}>
                  {attempt.title}
                </div>
                <div className="job-row__meta">
                  <span>{PLATFORM_LABELS[attempt.platform] ?? attempt.platform}</span>
                  <span>·</span>
                  <span>{attempt.account_label}</span>
                  <span>·</span>
                  <span title={absoluteTime(attempt.created_at)}>
                    {relativeTime(attempt.created_at)}
                  </span>
                </div>
                <div className="job-row__status">
                  <span className={`badge badge--${attemptBadgeKind(attempt.status)}`}>
                    <span className="badge__dot" />
                    {ATTEMPT_STATUS_LABELS[attempt.status] ?? attempt.status}
                  </span>
                  {attempt.post_url && (
                    <a href={attempt.post_url} target="_blank" rel="noreferrer">
                      Xem bài
                    </a>
                  )}
                </div>
                {attempt.status === "failed" && attempt.error && (
                  <p className="field__hint">{attempt.error}</p>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </AppShell>
  );
}
