// pages/PublishPage.tsx — Tab "Đăng video" (006-publish-video-tab).
//
// 3 khu vực: kết nối kênh (FR-005/FR-006/FR-011), form đăng (FR-002/FR-003/
// FR-004/FR-007), lịch sử lượt đăng (FR-010).

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  cancelAttempt,
  createPublish,
  disconnectChannel,
  getAttempt,
  listAttempts,
  listConnections,
  listPublishableVideos,
  startConnect,
  type CancelledAttemptSummary,
  type ChannelConnection,
  type PublishAttempt,
  type PublishableVideo,
  type PublishMode,
} from "../api/client";
import AppShell from "../components/AppShell";
import Callout from "../components/Callout";
import { IconInbox } from "../components/Icon";
import {
  PLATFORM_LABELS,
  PUBLISH_ATTEMPT_STATUS_LABELS,
  absoluteTime,
  formatScheduledFor,
  localDatetimeToUtcIso,
  relativeTime,
} from "../lib/labels";

// Chặng 1 chỉ bàn giao TikTok (plan.md → Thứ tự bàn giao); YouTube Shorts thêm
// ở Phase 4 — thêm 1 dòng vào mảng này là đủ ở phía UI.
const PLATFORMS = [{ value: "tiktok", label: "TikTok" }];

const ATTEMPT_POLL_MS = 2000;
// "scheduled" KHÔNG nằm trong active — bài đã hẹn giờ không cần poll liên tục,
// nó sẽ chuyển success/failed qua đối soát lười khi mở lại giao diện
// (007-schedule-publish, research.md §4)
const ACTIVE_STATUSES = new Set(["pending", "publishing"]);

// Chỉ để hiển thị gợi ý ngay trên form — backend luôn là nguồn sự thật
// (publish/limits.py::check_schedule_time)
const MIN_SCHEDULE_LEAD_MINUTES = 15;
const MAX_SCHEDULE_LEAD_DAYS = 3;

function attemptBadgeKind(status: string): string {
  if (status === "success") return "done";
  if (status === "failed") return "failed";
  if (status === "cancelled") return "idle";
  return "running";
}

function defaultScheduleValue(): string {
  const in20Min = new Date(Date.now() + 20 * 60 * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${in20Min.getFullYear()}-${pad(in20Min.getMonth() + 1)}-${pad(in20Min.getDate())}` +
    `T${pad(in20Min.getHours())}:${pad(in20Min.getMinutes())}`
  );
}

export default function PublishPage() {
  const [videos, setVideos] = useState<PublishableVideo[] | null>(null);
  const [connections, setConnections] = useState<ChannelConnection[] | null>(null);
  const [attempts, setAttempts] = useState<PublishAttempt[]>([]);

  const [platform, setPlatform] = useState(PLATFORMS[0].value);
  const [jobId, setJobId] = useState("");
  const [accountId, setAccountId] = useState("");
  const [title, setTitle] = useState("");
  const [publishMode, setPublishMode] = useState<PublishMode>("now");
  const [scheduleValue, setScheduleValue] = useState(defaultScheduleValue());

  const [configError, setConfigError] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [current, setCurrent] = useState<PublishAttempt | null>(null);
  const [scheduledAttempts, setScheduledAttempts] = useState<PublishAttempt[]>([]);
  const [cancellingId, setCancellingId] = useState<string | null>(null);

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

  const refreshScheduled = useCallback(async () => {
    try {
      const res = await listAttempts(undefined, "scheduled");
      setScheduledAttempts(res.attempts);
    } catch {
      // Danh sách chờ lỗi không nên chặn thao tác đăng
    }
  }, []);

  useEffect(() => {
    listPublishableVideos()
      .then((res) => setVideos(res.videos))
      .catch(() => setVideos([]));
    refreshConnections();
    refreshAttempts();
    refreshScheduled();
  }, [refreshConnections, refreshAttempts, refreshScheduled]);

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

      const cancelled: CancelledAttemptSummary[] = res.cancelled_attempts ?? [];
      if (cancelled.length > 0) {
        // FR-015: người dùng PHẢI biết những bài nào vừa bị huỷ theo
        const list = cancelled
          .map((a) => `"${a.title}" (${formatScheduledFor(a.scheduled_for)})`)
          .join(", ");
        setNotice(
          `Đã huỷ ${cancelled.length} bài đang chờ đăng lên kênh này: ${list}.`,
        );
        refreshScheduled();
        refreshAttempts();
      }

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

    let scheduledForUtc: string | undefined;
    if (publishMode === "scheduled") {
      if (!scheduleValue) {
        setFormError("Hãy chọn thời điểm hẹn giờ");
        return;
      }
      const leadMinutes = (new Date(scheduleValue).getTime() - Date.now()) / 60000;
      // Gợi ý tức thời cho người dùng — backend (check_schedule_time) vẫn là
      // nguồn sự thật, kể cả khi đồng hồ máy người dùng lệch (research.md §7)
      if (leadMinutes < MIN_SCHEDULE_LEAD_MINUTES) {
        setFormError(`Phải hẹn cách hiện tại ít nhất ${MIN_SCHEDULE_LEAD_MINUTES} phút`);
        return;
      }
      if (leadMinutes > MAX_SCHEDULE_LEAD_DAYS * 24 * 60) {
        setFormError(`Chỉ hẹn được tối đa ${MAX_SCHEDULE_LEAD_DAYS} ngày`);
        return;
      }
      scheduledForUtc = localDatetimeToUtcIso(scheduleValue);
    }

    setSubmitting(true);
    try {
      const { attempt_id } = await createPublish(
        jobId,
        platform,
        accountId,
        title.trim(),
        publishMode,
        scheduledForUtc,
      );
      const attempt = await getAttempt(attempt_id);
      if (publishMode === "scheduled") {
        // Bài hẹn giờ không cần poll (Zernio tự lo phần chờ) — chỉ cần refetch
        // danh sách đang chờ để hiện ngay trong khu vực bên dưới
        setCurrent(null);
        setNotice(
          `Đã đặt lịch đăng lúc ${formatScheduledFor(scheduledForUtc!)}. Bài sẽ tự lên đúng giờ, kể cả khi bạn tắt hệ thống.`,
        );
        refreshScheduled();
      } else {
        setCurrent(attempt);
        startPolling(attempt_id);
      }
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

  async function handleCancel(attemptId: string) {
    setCancellingId(attemptId);
    try {
      await cancelAttempt(attemptId);
      await Promise.all([refreshScheduled(), refreshAttempts()]);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Huỷ lượt đăng thất bại");
    } finally {
      setCancellingId(null);
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

            <div className="field">
              <label className="field__label">Thời điểm đăng</label>
              <div className="mode-grid">
                <label className="mode-option">
                  <input
                    type="radio"
                    name="publish-mode"
                    value="now"
                    checked={publishMode === "now"}
                    onChange={() => setPublishMode("now")}
                  />
                  <span className="mode-option__body">
                    <span className="mode-option__name">Đăng ngay</span>
                    <span className="mode-option__desc">Lên công khai ngay khi bấm Đăng</span>
                  </span>
                </label>
                <label className="mode-option">
                  <input
                    type="radio"
                    name="publish-mode"
                    value="scheduled"
                    checked={publishMode === "scheduled"}
                    onChange={() => setPublishMode("scheduled")}
                  />
                  <span className="mode-option__body">
                    <span className="mode-option__name">Hẹn giờ</span>
                    <span className="mode-option__desc">
                      Tự đăng đúng giờ, kể cả khi tắt hệ thống này
                    </span>
                  </span>
                </label>
              </div>
            </div>

            {publishMode === "scheduled" && (
              <div className="field">
                <label className="field__label" htmlFor="publish-schedule">
                  Ngày giờ đăng (giờ Việt Nam)
                </label>
                <input
                  id="publish-schedule"
                  type="datetime-local"
                  className="input"
                  value={scheduleValue}
                  onChange={(e) => setScheduleValue(e.target.value)}
                />
                <p className="field__hint">
                  Phải cách hiện tại ít nhất {MIN_SCHEDULE_LEAD_MINUTES} phút, tối đa{" "}
                  {MAX_SCHEDULE_LEAD_DAYS} ngày.
                </p>
              </div>
            )}

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
              {publishing
                ? "Đang đăng..."
                : submitting
                  ? "Đang gửi..."
                  : publishMode === "scheduled"
                    ? "Đặt lịch"
                    : "Đăng"}
            </button>
          </form>

          {notice && <Callout tone="info">{notice}</Callout>}

          {/* ── Đang chờ đăng (007-schedule-publish, FR-010/FR-011) ───── */}
          <div className="card">
            <div className="card__title">Đang chờ đăng</div>

            {scheduledAttempts.length === 0 && (
              <p className="field__hint">Chưa có bài nào đang chờ đăng.</p>
            )}

            {scheduledAttempts.map((attempt) => (
              <div key={attempt.attempt_id} className="job-row">
                <div className="job-row__url" title={attempt.title}>
                  {attempt.title}
                </div>
                <div className="job-row__meta">
                  <span>{PLATFORM_LABELS[attempt.platform] ?? attempt.platform}</span>
                  <span>·</span>
                  <span>{attempt.account_label}</span>
                  <span>·</span>
                  <span>
                    Đăng lúc {attempt.scheduled_for ? formatScheduledFor(attempt.scheduled_for) : "?"}
                  </span>
                </div>
                <div className="job-row__status">
                  <button
                    type="button"
                    className="btn btn--subtle"
                    onClick={() => handleCancel(attempt.attempt_id)}
                    disabled={cancellingId === attempt.attempt_id}
                  >
                    {cancellingId === attempt.attempt_id ? "Đang huỷ..." : "Huỷ"}
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* ── Tiến trình lượt đăng hiện tại ─────────────────────────── */}
          {current && (
            <div className="card">
              <div className="card__title">Lượt đăng hiện tại</div>
              <p>
                <span className={`badge badge--${attemptBadgeKind(current.status)}`}>
                  <span className="badge__dot" />
                  {PUBLISH_ATTEMPT_STATUS_LABELS[current.status] ?? current.status}
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
                    {PUBLISH_ATTEMPT_STATUS_LABELS[attempt.status] ?? attempt.status}
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
