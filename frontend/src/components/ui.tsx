/**
 * Small building blocks (DESIGN.md section 5): buttons, cards, fields, toggles,
 * alerts and the shared loading, error and settings-missing states.
 * Every tap target is at least 44px high; body text is 16px.
 */
import { useId, type ReactNode } from "react";
import { ACCENT, OUTLINE, type Marked } from "../accent.ts";
import { COMMON } from "../copy.ts";
import { Icon, type IconName } from "./Icon.tsx";

// ---- Button -----------------------------------------------------------------

type ButtonProps = {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "buffer" | "bank";
  type?: "button" | "submit";
  disabled?: boolean;
  busy?: boolean;
  size?: "md" | "lg";
  icon?: IconName;
  /** The form it submits when it sits outside it (the action bar). */
  form?: string;
  /** The id of the text that says why it is disabled. */
  describedBy?: string | undefined;
};

const BUTTON_VARIANTS = {
  primary: "bg-leaf-700 text-white hover:bg-leaf-800 active:bg-leaf-900 disabled:bg-leaf-300",
  secondary:
    "bg-card text-leaf-800 border-2 border-leaf-700 hover:bg-leaf-50 active:bg-leaf-100 disabled:border-line disabled:text-ink-muted",
  ghost: "bg-transparent text-leaf-800 hover:bg-leaf-50 active:bg-leaf-100 disabled:text-ink-muted",
  // A feature's own action, in its accent (accent.ts): the buffer, the bank's offer.
  buffer: `${OUTLINE.buffer} disabled:border-line disabled:text-ink-muted`,
  bank: `${OUTLINE.bank} disabled:border-line disabled:text-ink-muted`,
};

export function Button({
  children,
  onClick,
  variant = "primary",
  type = "button",
  disabled = false,
  busy = false,
  size = "md",
  icon,
  form,
  describedBy,
}: ButtonProps) {
  const height = size === "lg" ? "min-h-14 text-lead" : "min-h-12 text-body";
  return (
    <button
      type={type}
      form={form}
      onClick={onClick}
      disabled={disabled || busy}
      aria-describedby={describedBy}
      aria-busy={busy}
      className={`inline-flex w-full cursor-pointer items-center justify-center gap-2 rounded-pill px-5 font-semibold transition-colors duration-200 disabled:cursor-not-allowed ${height} ${BUTTON_VARIANTS[variant]}`}
    >
      {icon !== undefined && <Icon name={icon} size={size === "lg" ? 24 : 20} />}
      {children}
    </button>
  );
}

// ---- Card ---------------------------------------------------------------------

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-card bg-card p-5 shadow-card ${className}`}>{children}</section>;
}

// ---- Fields -------------------------------------------------------------------

type FieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  help?: string;
  error?: string | null;
  suffix?: string;
  inputMode?: "decimal" | "numeric" | "text";
  /** Leaving the field: the form shows its error from then on (เช็กก่อนผ่อน, UI-37). */
  onBlur?: () => void;
  placeholder?: string;
  maxLength?: number;
};

/**
 * A labelled text field. Money uses inputMode="decimal" with type="text", never
 * a number input: the browser must not turn "12000.50" into a float or round it.
 */
export function Field({
  label,
  value,
  onChange,
  help,
  error,
  suffix,
  inputMode = "text",
  placeholder,
  maxLength,
  onBlur,
}: FieldProps) {
  const id = useId();
  const helpId = `${id}-help`;
  const errorId = `${id}-error`;
  const describedBy = [help !== undefined ? helpId : "", error ? errorId : ""].join(" ").trim();
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-body font-semibold text-ink">
        {label}
      </label>
      <div
        className={`flex min-h-12 items-center rounded-field border-2 bg-card px-4 focus-within:border-leaf-600 ${
          error ? "border-risk-line" : "border-line"
        }`}
      >
        <input
          id={id}
          type="text"
          inputMode={inputMode}
          autoComplete="off"
          value={value}
          placeholder={placeholder}
          maxLength={maxLength}
          onChange={(event) => onChange(event.target.value)}
          onBlur={onBlur}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy === "" ? undefined : describedBy}
          className="min-w-0 flex-1 bg-transparent py-2 text-lead text-ink outline-none placeholder:text-ink-muted/70"
        />
        {suffix !== undefined && <span className="pl-2 text-body text-ink-muted">{suffix}</span>}
      </div>
      {help !== undefined && (
        <p id={helpId} className="text-body text-ink-muted">
          {help}
        </p>
      )}
      {error ? (
        <p id={errorId} role="alert" className="flex items-center gap-1.5 text-body font-semibold text-risk-ink">
          <Icon name="alert" size={16} />
          {error}
        </p>
      ) : null}
    </div>
  );
}

// ---- Toggle -------------------------------------------------------------------

type ToggleProps = { label: string; checked: boolean; onChange: (checked: boolean) => void; help?: string };

export function Toggle({ label, checked, onChange, help }: ToggleProps) {
  const id = useId();
  return (
    <div className="flex items-start justify-between gap-4">
      <label htmlFor={id} className="flex flex-col gap-1 py-2">
        <span className="text-body font-semibold text-ink">{label}</span>
        {help !== undefined && <span className="text-body text-ink-muted">{help}</span>}
      </label>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative mt-1 inline-flex h-11 w-16 shrink-0 cursor-pointer items-center rounded-pill transition-colors duration-200 ${
          checked ? "bg-leaf-700" : "bg-line"
        }`}
      >
        <span
          className={`inline-block h-8 w-8 rounded-pill bg-white shadow transition-transform duration-200 ${
            checked ? "translate-x-7" : "translate-x-1.5"
          }`}
        />
      </button>
    </div>
  );
}

// ---- Checkbox -----------------------------------------------------------------

type CheckboxProps = { label: string; checked: boolean; onChange: (checked: boolean) => void; error?: string | null };

export function Checkbox({ label, checked, onChange, error }: CheckboxProps) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="flex min-h-11 cursor-pointer items-start gap-3 py-1">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(event.target.checked)}
          className="mt-0.5 h-6 w-6 shrink-0 cursor-pointer accent-leaf-700"
        />
        <span className="text-body text-ink">{label}</span>
      </label>
      {error ? (
        <p role="alert" className="flex items-center gap-1.5 text-body font-semibold text-risk-ink">
          <Icon name="alert" size={16} />
          {error}
        </p>
      ) : null}
    </div>
  );
}

// ---- Alert ----------------------------------------------------------------------

export type Tone = "ok" | "warn" | "risk" | "info" | "buffer";

const TONES: Record<Tone, { box: string; icon: IconName }> = {
  ok: { box: "bg-ok-bg border-ok-line text-ok-ink", icon: "check" },
  buffer: { box: `${ACCENT.buffer.tint} ${ACCENT.buffer.line} ${ACCENT.buffer.ink}`, icon: ACCENT.buffer.icon },
  warn: { box: "bg-warn-bg border-warn-line text-warn-ink", icon: "alert" },
  risk: { box: "bg-risk-bg border-risk-line text-risk-ink", icon: "stop" },
  info: { box: "bg-info-bg border-info-line text-info-ink", icon: "info" },
};

export function Alert({ tone, title, children }: { tone: Tone; title?: string; children?: ReactNode }) {
  const style = TONES[tone];
  return (
    <div role={tone === "risk" || tone === "warn" ? "alert" : "status"} className={`flex gap-3 rounded-field border-2 p-4 ${style.box}`}>
      <Icon name={style.icon} className="mt-0.5" />
      <div className="flex flex-col gap-1">
        {title !== undefined && <p className="text-body font-bold">{title}</p>}
        {children !== undefined && <div className="text-body">{children}</div>}
      </div>
    </div>
  );
}

/** A coloured line: its icon and its text in the accent's ink, never colour only. */
export function MarkedText({ item, className = "" }: { item: Marked; className?: string }) {
  return (
    <span className={`flex items-start gap-2 text-body ${ACCENT[item.accent].ink} ${className}`}>
      <Icon name={item.icon} size={20} className="mt-0.5" />
      {item.text}
    </span>
  );
}

// ---- Shared states --------------------------------------------------------------

export function Loading({ lines = 3 }: { lines?: number }) {
  return (
    <div role="status" aria-label={COMMON.loading} className="flex flex-col gap-4">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="h-24 animate-pulse rounded-card bg-card/70 shadow-card" />
      ))}
      <span className="sr-only">{COMMON.loading}</span>
    </div>
  );
}

export function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card className="flex flex-col gap-4">
      <Alert tone="info" title={COMMON.errorTitle}>
        {COMMON.errorBody}
      </Alert>
      <Button variant="secondary" onClick={onRetry}>
        {COMMON.retry}
      </Button>
    </Card>
  );
}

export function SettingsMissing({ onSetUp }: { onSetUp: () => void }) {
  return (
    <Card className="flex flex-col gap-4">
      <Alert tone="info" title={COMMON.settingsMissingTitle}>
        {COMMON.settingsMissingBody}
      </Alert>
      <Button onClick={onSetUp} icon="gear">
        {COMMON.settingsMissingAction}
      </Button>
    </Card>
  );
}
