// components/AppShell.tsx — Khung ứng dụng: Brand + Điều hướng + Theme Toggle + Thông báo + Logout
import { useState, useEffect, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { logout } from "../api/client";
import { IconBell, IconFilm, IconInbox, IconLogout, IconShare, IconWave } from "./Icon";
import ThemeToggle from "./ThemeToggle";
import { useToast } from "../context/ToastContext";

type Props = {
  children: ReactNode;
  /** Trang dạng form/chi tiết dùng khổ hẹp cho dễ đọc. */
  narrow?: boolean;
};

export default function AppShell({ children, narrow = false }: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const [notificationState, setNotificationState] = useState<NotificationPermission>("default");

  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window) {
      setNotificationState(Notification.permission);
    }
  }, []);

  async function requestNotificationPermission() {
    if (typeof window !== "undefined" && "Notification" in window) {
      const perm = await Notification.requestPermission();
      setNotificationState(perm);
      if (perm === "granted") {
        toast.success("Đã bật thông báo Desktop khi job xử lý xong!");
      } else {
        toast.info("Đã từ chối nhận thông báo.");
      }
    }
  }

  async function handleLogout() {
    try {
      await logout();
    } catch {
      // Session hết hạn vẫn điều hướng về login
    }
    navigate("/login");
  }

  const isStudioActive =
    location.pathname === "/" ||
    location.pathname.startsWith("/generate") ||
    location.pathname.startsWith("/script-to-video");

  return (
    <>
      <header className="app-header">
        <div className="app-header__inner">
          <Link to="/" className="brand">
            <span className="brand__mark">
              <IconWave size={18} />
            </span>
            <span className="brand__text">
              <span>Video Studio</span>
              <span className="brand__sub">Tái tạo &amp; Sáng tạo video AI</span>
            </span>
          </Link>

          <nav className="app-nav">
            <NavLink
              to="/"
              className={`nav-link ${isStudioActive ? "nav-link--active" : ""}`}
            >
              <IconFilm size={15} />
              <span>Studio</span>
            </NavLink>

            <NavLink to="/jobs" className="nav-link">
              <IconInbox size={15} />
              <span>Lịch sử</span>
            </NavLink>

            <NavLink to="/downloads" className="nav-link">
              <span>Video đã tải</span>
            </NavLink>

            <NavLink to="/publish" className="nav-link">
              <IconShare size={15} />
              <span>Đăng video</span>
            </NavLink>
          </nav>

          <div className="app-header__tools">
            {typeof window !== "undefined" && "Notification" in window && notificationState !== "granted" && (
              <button
                type="button"
                className="btn btn--subtle"
                onClick={requestNotificationPermission}
                title="Bật thông báo Desktop khi job hoàn tất hoặc cần duyệt"
                aria-label="Bật thông báo"
              >
                <IconBell size={16} />
              </button>
            )}

            <ThemeToggle />

            <button
              type="button"
              className="btn btn--subtle"
              onClick={handleLogout}
              aria-label="Đăng xuất"
              title="Đăng xuất"
            >
              <IconLogout size={16} />
              <span className="hide-sm">Đăng xuất</span>
            </button>
          </div>
        </div>
      </header>

      <main className={narrow ? "app-main app-main--narrow" : "app-main"}>{children}</main>

      <footer className="app-footer">
        <div className="app-footer__inner">
          <span>AI Video Generation &amp; Supervised Dubbing Studio</span>
          <span>·</span>
          <span>Tách lời → Viết kịch bản tiếng Việt → Lồng tiếng khớp nhịp → Ghép video &amp; Đăng tự động</span>
        </div>
      </footer>
    </>
  );
}
