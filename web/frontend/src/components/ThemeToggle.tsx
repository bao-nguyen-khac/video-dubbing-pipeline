// components/ThemeToggle.tsx — Nút chuyển đổi giao diện Sáng / Tối / Tự động
import { useState, useRef, useEffect } from "react";
import { useTheme, type Theme } from "../context/ThemeContext";
import { IconLaptop, IconMoon, IconSun } from "./Icon";

export default function ThemeToggle() {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [open]);

  const options: { value: Theme; label: string; icon: typeof IconSun }[] = [
    { value: "light", label: "Giao diện sáng", icon: IconSun },
    { value: "dark", label: "Giao diện tối", icon: IconMoon },
    { value: "system", label: "Theo hệ thống", icon: IconLaptop },
  ];

  return (
    <div className="theme-toggle-wrap" ref={dropdownRef}>
      <button
        type="button"
        className="btn btn--subtle theme-toggle-btn"
        onClick={() => setOpen((prev) => !prev)}
        title={`Giao diện: ${theme === "system" ? "Tự động" : theme === "dark" ? "Tối" : "Sáng"}`}
        aria-label="Đổi giao diện"
      >
        {resolvedTheme === "dark" ? <IconMoon size={16} /> : <IconSun size={16} />}
      </button>

      {open && (
        <div className="theme-dropdown">
          {options.map((opt) => {
            const Icon = opt.icon;
            const active = theme === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                className={`theme-dropdown__item${active ? " theme-dropdown__item--active" : ""}`}
                onClick={() => {
                  setTheme(opt.value);
                  setOpen(false);
                }}
              >
                <Icon size={15} />
                <span>{opt.label}</span>
                {active && <span className="theme-dropdown__check">✓</span>}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
