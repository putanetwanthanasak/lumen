/**
 * Two logo options (DESIGN.md section 2). Abstract and friendly; never an organ.
 * A: "Bean": a soft bean shape with a small smile and a coin dot ("think, then keep").
 * B: "Filter": three rounded layers narrowing to one coin ("only what fits passes").
 * The app uses A; B is kept for comparison in DESIGN.md.
 */
type Props = { size?: number; title?: string };

export function LogoBean({ size = 40, title = "KidNee" }: Props) {
  return (
    <svg viewBox="0 0 48 48" width={size} height={size} role="img" aria-label={title}>
      <path
        d="M14 8c6-4 15-3 20 2 4 4 3 9 0 12-2 2-2 4 0 6 4 4 4 11-2 15-6 4-16 4-22-2C4 35 4 25 6 19c1.5-5 4-9 8-11Z"
        fill="var(--color-leaf-600)"
      />
      <path
        d="M16 13c3-2 7-2 10 0"
        stroke="var(--color-leaf-200)"
        strokeWidth="3"
        strokeLinecap="round"
        fill="none"
      />
      <circle cx="17" cy="25" r="2" fill="#ffffff" />
      <circle cx="26" cy="25" r="2" fill="#ffffff" />
      <path
        d="M17 31c2.5 2.5 6.5 2.5 9 0"
        stroke="#ffffff"
        strokeWidth="2.5"
        strokeLinecap="round"
        fill="none"
      />
      <circle cx="37" cy="36" r="6" fill="var(--color-sun-400)" />
      <path d="M37 33v6" stroke="var(--color-leaf-900)" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function LogoFilter({ size = 40, title = "KidNee" }: Props) {
  return (
    <svg viewBox="0 0 48 48" width={size} height={size} role="img" aria-label={title}>
      <rect x="6" y="7" width="36" height="8" rx="4" fill="var(--color-leaf-300)" />
      <rect x="11" y="18" width="26" height="8" rx="4" fill="var(--color-leaf-500)" />
      <rect x="16" y="29" width="16" height="8" rx="4" fill="var(--color-leaf-700)" />
      <circle cx="24" cy="43" r="4" fill="var(--color-sun-400)" />
    </svg>
  );
}
