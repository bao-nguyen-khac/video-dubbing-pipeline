// components/Icon.tsx — Bộ icon inline (SVG stroke), không thêm dependency.
// Kích thước mặc định 16px, màu kế thừa currentColor.

type IconProps = {
  size?: number;
  className?: string;
};

function base(size: number, className?: string) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    focusable: false,
    className,
  };
}

export function IconWave({ size = 20, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M4 12v1M8 8v8M12 4v16M16 8v8M20 12v1" />
    </svg>
  );
}

export function IconPlay({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M6 4l14 8-14 8V4z" />
    </svg>
  );
}

export function IconDownload({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 19h16" />
    </svg>
  );
}

export function IconRetry({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M20 11a8 8 0 10-2.3 5.7M20 5v6h-6" />
    </svg>
  );
}

export function IconArrowLeft({ size = 15, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M19 12H5m0 0l6-6m-6 6l6 6" />
    </svg>
  );
}

export function IconAlert({ size = 17, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M12 8v5m0 3h.01M10.3 3.9L2.4 17a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />
    </svg>
  );
}

export function IconInfo({ size = 17, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5m0-8h.01" />
    </svg>
  );
}

export function IconCheck({ size = 17, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}

export function IconInbox({ size = 40, className }: IconProps) {
  return (
    <svg {...base(size, className)} strokeWidth={1.5}>
      <path d="M3 13h4l2 3h6l2-3h4" />
      <path d="M4.5 5.5h15l1.5 7.5v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5l1.5-7.5z" />
    </svg>
  );
}

export function IconLogout({ size = 15, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M15 17l5-5-5-5M20 12H9M12 20H6a2 2 0 01-2-2V6a2 2 0 012-2h6" />
    </svg>
  );
}

export function IconPin({ size = 14, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M12 17v5M8 4h8l-1 6 3 3v2H6v-2l3-3-1-6z" />
    </svg>
  );
}

export function IconTrash({ size = 14, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M4 7h16M9 7V4h6v3M6 7l1 13a2 2 0 002 2h6a2 2 0 002-2l1-13M10 11v6M14 11v6" />
    </svg>
  );
}
