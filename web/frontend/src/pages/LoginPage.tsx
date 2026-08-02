import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { login, ApiError } from "../api/client";
import Callout from "../components/Callout";
import { IconWave } from "../components/Icon";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Đăng nhập thất bại");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="login-head">
          <span className="brand">
            <span className="brand__mark">
              <IconWave size={18} />
            </span>
            <span className="brand__text">
              <span>Video Dubbing</span>
            </span>
          </span>
          <h1>Đăng nhập</h1>
          <p>Dùng tài khoản cấu hình trong .env của máy chủ.</p>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="card">
            <div className="field">
              <label className="field__label" htmlFor="username">
                Tài khoản
              </label>
              <input
                id="username"
                className="input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                required
              />
            </div>

            <div className="field">
              <label className="field__label" htmlFor="password">
                Mật khẩu
              </label>
              <input
                id="password"
                className="input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>

            <div className="field">
              <button type="submit" className="btn btn--primary btn--block" disabled={loading}>
                {loading && <span className="btn__spinner" />}
                {loading ? "Đang đăng nhập..." : "Đăng nhập"}
              </button>
            </div>
          </div>
        </form>

        {error && (
          <Callout tone="error" title="Không đăng nhập được">
            {error}
          </Callout>
        )}
      </div>
    </div>
  );
}
