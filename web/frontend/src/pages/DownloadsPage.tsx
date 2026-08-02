import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, listDownloads, type DownloadedVideo } from "../api/client";
import AppShell from "../components/AppShell";
import Callout from "../components/Callout";
import { IconInbox } from "../components/Icon";
import { PLATFORM_LABELS, relativeTime, absoluteTime, shortUrl } from "../lib/labels";

export default function DownloadsPage() {
  const [videos, setVideos] = useState<DownloadedVideo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    listDownloads()
      .then((res) => setVideos(res.videos))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Không tải được danh sách"),
      );
  }, []);

  // "Dùng lại": điền link sẵn vào trang tạo job — job mới sẽ clone file đã tải
  // thay vì tải lại (pipeline tự tra download_registry).
  function reuse(url: string) {
    navigate(`/?url=${encodeURIComponent(url)}`);
  }

  return (
    <AppShell>
      <div className="page-head">
        <h1>Video đã tải</h1>
        <p className="page-head__lead">
          {videos === null
            ? "Đang tải..."
            : `${videos.length} video đã lưu. Tạo job với cùng link sẽ dùng lại file, không tải lại.`}
        </p>
      </div>

      {error && (
        <Callout tone="error" title="Không tải được danh sách">
          {error}
        </Callout>
      )}

      {videos === null && !error && (
        <div>
          <div className="skeleton skeleton--row" />
          <div className="skeleton skeleton--row" />
        </div>
      )}

      {videos !== null && videos.length === 0 && (
        <div className="card">
          <div className="empty">
            <IconInbox className="empty__icon" />
            <div className="empty__title">Chưa có video nào được lưu</div>
            <p>Sau khi tải video (bất kỳ chế độ nào), link sẽ xuất hiện ở đây.</p>
          </div>
        </div>
      )}

      {videos !== null && videos.length > 0 && (
        <div className="job-list">
          {videos.map((v) => (
            <div key={v.url} className="job-row job-row--static">
              <div className="job-row__url" title={v.url}>
                <a href={v.url} target="_blank" rel="noreferrer">
                  {shortUrl(v.url)}
                </a>
              </div>
              <div className="job-row__meta">
                <span>{PLATFORM_LABELS[v.platform] ?? v.platform}</span>
                <span>·</span>
                <span title={absoluteTime(v.created_at)}>{relativeTime(v.created_at)}</span>
                {!v.available && (
                  <>
                    <span>·</span>
                    <span className="text-danger">file đã mất</span>
                  </>
                )}
              </div>
              <div className="job-row__status">
                <button
                  type="button"
                  className="btn btn--subtle"
                  onClick={() => reuse(v.url)}
                  disabled={!v.available}
                  title={v.available ? "Tạo job mới, dùng lại file này" : "File nguồn không còn trên đĩa"}
                >
                  Dùng lại
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </AppShell>
  );
}
