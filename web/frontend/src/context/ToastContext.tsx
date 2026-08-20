import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { IconCheck, IconClose, IconInfo, IconWave } from "../components/Icon";

export type ToastType = "success" | "error" | "info" | "copy";

export interface ToastItem {
  id: string;
  type: ToastType;
  title?: string;
  message: string;
  duration?: number;
}

interface ToastContextType {
  toast: {
    success: (message: string, title?: string) => void;
    error: (message: string, title?: string) => void;
    info: (message: string, title?: string) => void;
    copy: (message?: string) => void;
  };
  removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback(
    (type: ToastType, message: string, title?: string, duration = 3500) => {
      const id = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      const newToast: ToastItem = { id, type, message, title, duration };
      setToasts((prev) => [...prev.slice(-4), newToast]);

      if (duration > 0) {
        setTimeout(() => {
          removeToast(id);
        }, duration);
      }
    },
    [removeToast],
  );

  const toast = {
    success: (message: string, title?: string) => addToast("success", message, title),
    error: (message: string, title?: string) => addToast("error", message, title, 5000),
    info: (message: string, title?: string) => addToast("info", message, title),
    copy: (message = "Đã sao chép vào bộ nhớ tạm!") => addToast("copy", message, "Đã sao chép", 2000),
  };

  return (
    <ToastContext.Provider value={{ toast, removeToast }}>
      {children}
      <div className="toast-container" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast--${t.type}`} role="status">
            <div className="toast__icon">
              {t.type === "success" && <IconCheck size={16} />}
              {t.type === "error" && <IconClose size={16} />}
              {t.type === "info" && <IconInfo size={16} />}
              {t.type === "copy" && <IconWave size={16} />}
            </div>
            <div className="toast__content">
              {t.title && <div className="toast__title">{t.title}</div>}
              <div className="toast__message">{t.message}</div>
            </div>
            <button
              type="button"
              className="toast__close"
              onClick={() => removeToast(t.id)}
              aria-label="Đóng thông báo"
            >
              <IconClose size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context.toast;
}
