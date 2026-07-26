import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, listJobs, type JobSummary } from "../api/client";

export default function JobListPage() {
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listJobs()
      .then((res) => setJobs(res.jobs))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Không tải được danh sách job"));
  }, []);

  return (
    <div className="page job-list-page">
      <h1>Lịch sử job</h1>
      <p>
        <Link to="/">← Quay lại trang chủ</Link>
      </p>

      {error && <p className="error">{error}</p>}

      {jobs === null && !error && <p>Đang tải...</p>}

      {jobs !== null && jobs.length === 0 && <p>Chưa có job nào.</p>}

      {jobs !== null && jobs.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>URL</th>
              <th>Nền tảng</th>
              <th>Trạng thái</th>
              <th>%</th>
              <th>Tạo lúc</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.job_id}>
                <td>
                  <Link to={`/jobs/${job.job_id}`}>{job.source_url}</Link>
                </td>
                <td>{job.platform}</td>
                <td>{job.status}</td>
                <td>{job.progress_percent}%</td>
                <td>{new Date(job.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
