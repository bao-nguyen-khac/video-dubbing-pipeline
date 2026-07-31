// components/StatusBadge.tsx — Badge trạng thái job, màu theo nhóm
// running/waiting/done/failed (chấm nhấp nháy khi đang chạy).
//
// 008: job "awaiting_review" là nhóm màu RIÊNG và nói rõ đang chờ duyệt tại chốt
// nào — người dùng phải phân biệt được ngay với job đang xử lý và job lỗi
// (FR-006), vì việc cần làm ở mỗi trường hợp khác nhau hoàn toàn.

import { REVIEW_GATE_LABELS, STATUS_LABELS, statusKind } from "../lib/labels";

export default function StatusBadge({
  status,
  reviewGate,
}: {
  status: string;
  reviewGate?: string | null;
}) {
  const kind = statusKind(status);
  const label = STATUS_LABELS[status] ?? status;
  const gateLabel = reviewGate ? (REVIEW_GATE_LABELS[reviewGate] ?? reviewGate) : null;

  return (
    <span className={`badge badge--${kind}`}>
      <span className="badge__dot" />
      {kind === "waiting" && gateLabel ? `${label} · ${gateLabel}` : label}
    </span>
  );
}
