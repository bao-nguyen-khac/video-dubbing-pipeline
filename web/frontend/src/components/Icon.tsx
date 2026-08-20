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

export function IconPause({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <rect x="6" y="4" width="4" height="16" rx="1" />
      <rect x="14" y="4" width="4" height="16" rx="1" />
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

export function IconClose({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M18 6L6 18M6 6l12 12" />
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

export function IconShare({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M12 3v12m0-12l4 4m-4-4l-4 4M6 13v6a2 2 0 002 2h8a2 2 0 002-2v-6" />
    </svg>
  );
}

export function IconCopy({ size = 15, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
    </svg>
  );
}

export function IconSun({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <circle cx="12" cy="12" r="5" />
      <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
    </svg>
  );
}

export function IconMoon({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
    </svg>
  );
}

export function IconLaptop({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
      <path d="M1 20h22" />
    </svg>
  );
}

export function IconSearch({ size = 15, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <circle cx="11" cy="11" r="8" />
      <path d="M21 21l-4.35-4.35" />
    </svg>
  );
}

export function IconFilter({ size = 15, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
    </svg>
  );
}

export function IconUpload({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
    </svg>
  );
}

export function IconVideo({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <polygon points="23 7 16 12 23 17 23 7" />
      <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
    </svg>
  );
}

export function IconFilm({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18" />
      <line x1="7" y1="2" x2="7" y2="22" />
      <line x1="17" y1="2" x2="17" y2="22" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <line x1="2" y1="7" x2="7" y2="7" />
      <line x1="2" y1="17" x2="7" y2="17" />
      <line x1="17" y1="17" x2="22" y2="17" />
      <line x1="17" y1="7" x2="22" y2="7" />
    </svg>
  );
}

export function IconSparkles({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
    </svg>
  );
}

export function IconVolume({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
      <path d="M19.07 4.93a10 10 0 010 14.14M15.54 8.46a5 5 0 010 7.07" />
    </svg>
  );
}

export function IconVolumeMute({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
      <line x1="23" y1="9" x2="17" y2="15" />
      <line x1="17" y1="9" x2="23" y2="15" />
    </svg>
  );
}

export function IconBell({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 01-3.46 0" />
    </svg>
  );
}

export function IconSliders({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <line x1="4" y1="21" x2="4" y2="14" />
      <line x1="4" y1="10" x2="4" y2="3" />
      <line x1="12" y1="21" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12" y2="3" />
      <line x1="20" y1="21" x2="20" y2="16" />
      <line x1="20" y1="12" x2="20" y2="3" />
      <line x1="1" y1="14" x2="7" y2="14" />
      <line x1="9" y1="8" x2="15" y2="8" />
      <line x1="17" y1="16" x2="23" y2="16" />
    </svg>
  );
}

export function IconChevronDown({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}
