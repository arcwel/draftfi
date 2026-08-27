interface IconProps {
  size?: number
  className?: string
}

export function GripIcon({ size = 14, className }: IconProps): React.JSX.Element {
  return (
    <svg
      width={size * 0.7}
      height={size}
      viewBox="0 0 10 16"
      fill="currentColor"
      className={className}
    >
      <circle cx="2.5" cy="3" r="1.4" />
      <circle cx="7.5" cy="3" r="1.4" />
      <circle cx="2.5" cy="8" r="1.4" />
      <circle cx="7.5" cy="8" r="1.4" />
      <circle cx="2.5" cy="13" r="1.4" />
      <circle cx="7.5" cy="13" r="1.4" />
    </svg>
  )
}

export function CloseIcon({ size = 13, className }: IconProps): React.JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      className={className}
    >
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  )
}

export function BackIcon({ size = 16, className }: IconProps): React.JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M15 18l-6-6 6-6" />
    </svg>
  )
}

export function ForwardIcon({ size = 16, className }: IconProps): React.JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M9 18l6-6-6-6" />
    </svg>
  )
}

export function ReloadIcon({ size = 15, className }: IconProps): React.JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M21 12a9 9 0 1 1-2.64-6.36" />
      <path d="M21 3v6h-6" />
    </svg>
  )
}

export function DeckIcon({ size = 14, className }: IconProps): React.JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
      className={className}
    >
      <rect x="3" y="3" width="11" height="11" rx="1.5" />
      <rect x="17" y="3" width="4" height="11" rx="1.5" />
      <rect x="3" y="17" width="18" height="4" rx="1.5" />
    </svg>
  )
}

export function PopOutIcon({ size = 13, className }: IconProps): React.JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M14 4h6v6" />
      <path d="M20 4L11 13" />
      <path d="M20 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h5" />
    </svg>
  )
}

export function GlobeIcon({ size = 14, className }: IconProps): React.JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className={className}
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.5 2.6 3.8 5.7 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.7-3.8-9s1.3-6.4 3.8-9z" />
    </svg>
  )
}

export function MinusIcon({ size = 13, className }: IconProps): React.JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      className={className}
    >
      <path d="M5 12h14" />
    </svg>
  )
}

export function BlockTypeIcon({
  type,
  size = 15,
  className
}: IconProps & { type: 'editor' | 'files' | 'terminal' | 'agents' | 'logs' }): React.JSX.Element {
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    className
  }
  switch (type) {
    case 'editor':
      return (
        <svg {...common}>
          <path d="M8 6l-5 6 5 6M16 6l5 6-5 6" />
        </svg>
      )
    case 'files':
      return (
        <svg {...common}>
          <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        </svg>
      )
    case 'terminal':
      return (
        <svg {...common}>
          <path d="M5 8l5 4-5 4M12 17h7" />
        </svg>
      )
    case 'agents':
      return (
        <svg {...common}>
          <rect x="5" y="8" width="14" height="11" rx="2" />
          <path d="M12 8V4M9 13h.01M15 13h.01" />
        </svg>
      )
    case 'logs':
      return (
        <svg {...common}>
          <path d="M4 6h16M4 12h16M4 18h10" />
        </svg>
      )
  }
}

export function DockInIcon({ size = 13, className }: IconProps): React.JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M15 9l-6 6M9 9h6v6" />
    </svg>
  )
}
