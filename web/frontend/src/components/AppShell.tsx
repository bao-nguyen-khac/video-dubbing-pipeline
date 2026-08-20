// components/AppShell.tsx — Khung ứng dụng: Brand + Điều hướng + Theme Toggle + Thông báo + Logout
import { useState, useEffect, type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { logout } from "../api/client";
import { IconBell, IconFilm, IconInbox, IconLogout, IconVideo, IconWave } from "./Icon";
import ThemeToggle from "./ThemeToggle";
import { useToast } from "../context/ToastContext";

type Props = {
  children: ReactNode;
  /** Trang dạng form/chi tiết dùng khổ hẹp cho dễ đọc. */
  narrow?: boolean;
};

export default function AppShell({ children, narrow = false }: Props) {
  const navigate = useNavigate();
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
              <span className="brand__sub">Lồng tiếng &amp; Tái tạo video AI</span>
            </span>
          </Link>

          <nav className="app-nav">
            <NavLink to="/" className="nav-link" end>
              <IconFilm size={15} />
              <span>Lồng tiếng</span>
            </NavLink>

            <NavLink to="/jobs" className="nav-link">
              <IconInbox size={15} />
              <span>Lịch sử job</span>
            </NavLink>

            <NavLink to="/downloads" className="nav-link">
              <IconVideo size={15} />
              <span>Tải hàng loạt</span>
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
          <span>AI Video Dubbing Studio</span>
          <span>·</span>
          <span>Tách lời → Viết kịch bản tiếng Việt → Lồng tiếng khớp nhịp → Ghép video &amp; Phụ đề</span>
        </div>
      </footer>
    </>
  );
}
