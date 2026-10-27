/**
 * Inline SVG icons (no icon font, no emoji). Decorative by default: the text next
 * to an icon carries the meaning, so screen readers skip the icon.
 */
export type IconName =
  | "check"
  | "alert"
  | "stop"
  | "home"
  | "think"
  | "shield"
  | "bell"
  | "gear"
  | "back"
  | "info"
  | "wallet"
  | "spark"
  | "edit"
  | "down"
  | "calendar";

const PATHS: Record<IconName, string> = {
  check: "M20 6 9 17l-5-5",
  alert: "M12 3 2 20h20L12 3Zm0 6v5m0 3.5v.5",
  stop: "M8 3h8l5 5v8l-5 5H8l-5-5V8l5-5Zm4 5v5m0 3.5v.5",
  home: "M3 11 12 4l9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1v-9Z",
  think: "M9 18h6m-5 3h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3Z",
  shield: "M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6l-8-3Zm-3 9 2 2 4-4",
  bell: "M6 16V11a6 6 0 1 1 12 0v5l2 2H4l2-2Zm4 4h4",
  gear: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7.5 7.5 0 0 0-2-1.2L14.5 3h-5l-.4 2.6a7.5 7.5 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7.5 7.5 0 0 0 2 1.2l.4 2.6h5l.4-2.6a7.5 7.5 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2Z",
  back: "M15 18 9 12l6-6",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-11v6m0-9v.5",
  wallet: "M3 7a2 2 0 0 1 2-2h13v4M3 7v10a2 2 0 0 0 2 2h15V9H5a2 2 0 0 1-2-2Zm13 7h.5",
  spark: "M10 3.5l1.6 4.9 4.9 1.6-4.9 1.6L10 16.5l-1.6-4.9L3.5 10l4.9-1.6L10 3.5ZM18 14l.8 2.2 2.2.8-2.2.8L18 20l-.8-2.2-2.2-.8 2.2-.8L18 14Z",
  edit: "M4 20h4L19 9l-4-4L4 16v4Zm9-13 4 4",
  down: "m6 9 6 6 6-6",
  calendar: "M4 6h16v14H4V6Zm0 4h16M8 3v4m8-4v4m-7 7 2 2 4-4",
};

type Props = { name: IconName; size?: number; className?: string; label?: string };

export function Icon({ name, size = 24, className = "", label }: Props) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`shrink-0 ${className}`}
      {...(label === undefined ? { "aria-hidden": true } : { role: "img", "aria-label": label })}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
