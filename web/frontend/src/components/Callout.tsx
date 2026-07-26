// components/Callout.tsx — Khối thông báo. Phân biệt rõ error (job hỏng) với
// warning (job vẫn xong nhưng chất lượng có vấn đề) — trước đây cả 2 đều hiện
// màu đỏ giống nhau nên người dùng không phân biệt được mức độ.

import type { ReactNode } from "react";
import { IconAlert, IconCheck, IconInfo } from "./Icon";

type Tone = "error" | "warning" | "info" | "success";

const ICONS: Record<Tone, typeof IconAlert> = {
  error: IconAlert,
  warning: IconAlert,
  info: IconInfo,
  success: IconCheck,
};

export default function Callout({
  tone = "info",
  title,
  children,
}: {
  tone?: Tone;
  title?: string;
  children?: ReactNode;
}) {
  const Icon = ICONS[tone];
  return (
    <div className={`callout callout--${tone}`} role={tone === "error" ? "alert" : undefined}>
      <Icon className="callout__icon" />
      <div className="callout__body">
        {title && <div className="callout__title">{title}</div>}
        {children}
      </div>
    </div>
  );
}
