// components/AppShell.tsx — Khung chung: header (brand + điều hướng + đăng
// xuất), vùng nội dung, footer. Trang đăng nhập KHÔNG dùng shell này.

import type { ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { logout } from "../api/client";
import { IconLogout, IconWave } from "./Icon";

type Props = {
  children: ReactNode;
  /** Trang dạng form/chi tiết dùng khổ hẹp cho dễ đọc. */
  narrow?: boolean;
};

export default function AppShell({ children, narrow = false }: Props) {
  const navigate = useNavigate();

  async function handleLogout() {
    try {
      await logout();
    } catch {
      // Kể cả khi API lỗi vẫn đưa người dùng về trang đăng nhập — session phía
      // server hết hạn cũng cho ra cùng kết quả người dùng mong đợi
    }
    navigate("/login");
  }

  return (
    <>
      <header className="app-header">
        <div className="app-header__inner">
          <Link to="/" className="brand">
            <span className="brand__mark">
              <IconWave size={18} />
            </span>
            <span className="brand__text">
              <span>Video Dubbing</span>
              <span className="brand__sub">Tái tạo &amp; lồng tiếng video</span>
            </span>
          </Link>

          <nav className="app-nav">
            <NavLink to="/" end className="nav-link">
              Tạo job
            </NavLink>
            <NavLink to="/generate" className="nav-link">
              Tạo từ chủ đề
            </NavLink>
            <NavLink to="/script-to-video" className="nav-link">
              Script-to-video
            </NavLink>
            <NavLink to="/jobs" className="nav-link">
              Lịch sử
            </NavLink>
            <NavLink to="/downloads" className="nav-link">
              Video đã tải
            </NavLink>
            <NavLink to="/publish" className="nav-link">
              Đăng video
            </NavLink>
            <button
              type="button"
              className="btn btn--subtle"
              onClick={handleLogout}
              aria-label="Đăng xuất"
            >
              <IconLogout />
              {/* Trên màn hẹp chỉ còn icon — 3 mục chữ làm vỡ header ở 390px */}
              <span className="hide-sm">Đăng xuất</span>
            </button>
          </nav>
        </div>
      </header>

      <main className={narrow ? "app-main app-main--narrow" : "app-main"}>{children}</main>

      <footer className="app-footer">
        Tải video → tách lời → viết kịch bản tiếng Việt → lồng tiếng khớp nhịp → ghép video
      </footer>
    </>
  );
}
