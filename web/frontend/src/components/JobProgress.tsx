// components/JobProgress.tsx — Thanh tiến trình + dải bước pipeline, dùng
// chung cho HomePage (job vừa submit) và JobDetailPage.
//
// Thay cho <progress> trần trước đây: người dùng thấy được job đang ở BƯỚC nào
// (tải / tách lời / kịch bản / giọng đọc / ghép) chứ không chỉ một con số %.

import { STAGES, stageStates, statusKind } from "../lib/labels";
import StatusBadge from "./StatusBadge";

export default function JobProgress({
  status,
  progressPercent,
  scriptMode,
}: {
  status: string;
  progressPercent: number;
  scriptMode?: string;
}) {
  const kind = statusKind(status);
  const states = stageStates(progressPercent, status, scriptMode);

  return (
    <div className="progress">
      <div className="progress__head">
        <StatusBadge status={status} />
        <span className="progress__pct">{progressPercent}%</span>
      </div>

      <div
        className="progress__bar"
        role="progressbar"
        aria-valuenow={progressPercent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={`progress__fill${kind === "done" ? " progress__fill--done" : ""}${
            kind === "failed" ? " progress__fill--failed" : ""
          }`}
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      <ol className="steps">
        {STAGES.map((stage, i) => {
          const state = states[i];
          return (
            <li key={stage.key} className={`step step--${state}`}>
              <span className="step__icon">
                {state === "done" ? "✓" : state === "failed" ? "!" : i + 1}
              </span>
              {stage.label}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
