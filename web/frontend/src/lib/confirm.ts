// lib/confirm.ts — thay window.confirm() bằng hộp thoại theo đúng theme app.
// ConfirmDialog (component) đăng ký hàm xử lý thật khi mount; confirm() ở đây
// chỉ là cổng gọi vào, an toàn dùng ở bất kỳ event handler nào không phải React.

export type ConfirmOptions = {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "default" | "danger";
};

type Requester = (options: ConfirmOptions) => Promise<boolean>;

let requester: Requester | null = null;

export function registerConfirmRequester(fn: Requester | null) {
  requester = fn;
}

export function confirm(options: ConfirmOptions | string): Promise<boolean> {
  const resolved = typeof options === "string" ? { message: options } : options;
  if (!requester) {
    // ConfirmDialog chưa mount (không nên xảy ra) — vẫn cho thao tác tiếp tục được
    return Promise.resolve(window.confirm(resolved.message));
  }
  return requester(resolved);
}
