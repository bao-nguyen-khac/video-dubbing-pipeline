// components/StudioTabs.tsx — Thanh chuyển đổi nhanh giữa 3 chế độ sáng tạo video trong Studio
import { Link, useLocation } from "react-router-dom";
import { IconFilm, IconSparkles, IconWave } from "./Icon";

export default function StudioTabs() {
  const location = useLocation();
  const path = location.pathname;

  const tabs = [
    {
      to: "/",
      label: "Lồng tiếng video",
      desc: "Từ TikTok, Douyin, YouTube hoặc file có sẵn",
      icon: IconWave,
      active: path === "/",
    },
    {
      to: "/generate",
      label: "Tạo từ chủ đề",
      desc: "Tự viết kịch bản, tìm ảnh minh hoạ & dựng video dọc",
      icon: IconSparkles,
      active: path.startsWith("/generate"),
    },
    {
      to: "/script-to-video",
      label: "Script-to-video",
      desc: "POV nhiều phần, Character Bible & Prompt Google Flow",
      icon: IconFilm,
      active: path.startsWith("/script-to-video"),
    },
  ];

  return (
    <div className="studio-tabs">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        return (
          <Link
            key={tab.to}
            to={tab.to}
            className={`studio-tab ${tab.active ? "studio-tab--active" : ""}`}
          >
            <div className="studio-tab__icon">
              <Icon size={18} />
            </div>
            <div className="studio-tab__text">
              <span className="studio-tab__title">{tab.label}</span>
              <span className="studio-tab__desc">{tab.desc}</span>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
