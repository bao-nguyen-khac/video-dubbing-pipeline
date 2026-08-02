// components/ConfirmDialog.tsx — hộp thoại xác nhận dùng chung, thay
// window.confirm() gốc trình duyệt bằng UI khớp theme app. Mount 1 lần ở App.

import { useEffect, useRef, useState } from "react";
import { registerConfirmRequester, type ConfirmOptions } from "../lib/confirm";
import { IconAlert } from "./Icon";

export default function ConfirmDialog() {
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const resolveRef = useRef<((value: boolean) => void) | null>(null);

  useEffect(() => {
    registerConfirmRequester(
      (opts) =>
        new Promise<boolean>((resolve) => {
          resolveRef.current = resolve;
          setOptions(opts);
        }),
    );
    return () => registerConfirmRequester(null);
  }, []);

  function close(result: boolean) {
    resolveRef.current?.(result);
    resolveRef.current = null;
    setOptions(null);
  }

  useEffect(() => {
    if (!options) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options]);

  if (!options) return null;

  const danger = options.tone === "danger";

  return (
    <div className="confirm-overlay" onMouseDown={() => close(false)}>
      <div
        className="confirm-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className={`confirm-dialog__icon${danger ? " confirm-dialog__icon--danger" : ""}`}>
          <IconAlert size={18} />
        </div>
        <div id="confirm-dialog-title" className="confirm-dialog__title">
          {options.title ?? (danger ? "Xác nhận thao tác không thể hoàn tác" : "Xác nhận")}
        </div>
        <p className="confirm-dialog__message">{options.message}</p>
        <div className="confirm-dialog__actions">
          <button type="button" className="btn btn--ghost" onClick={() => close(false)} autoFocus>
            {options.cancelLabel ?? "Huỷ"}
          </button>
          <button
            type="button"
            className={`btn ${danger ? "btn--danger" : "btn--primary"}`}
            onClick={() => close(true)}
          >
            {options.confirmLabel ?? "Xác nhận"}
          </button>
        </div>
      </div>
    </div>
  );
}
