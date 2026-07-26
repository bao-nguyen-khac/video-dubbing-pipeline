// components/StatusBadge.tsx — Badge trạng thái job, màu theo nhóm
// running/done/failed (chấm nhấp nháy khi đang chạy).

import { STATUS_LABELS, statusKind } from "../lib/labels";

export default function StatusBadge({ status }: { status: string }) {
  const kind = statusKind(status);
  return (
    <span className={`badge badge--${kind}`}>
      <span className="badge__dot" />
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}
