import { useEffect, useId, useRef, type ReactNode } from "react";
import { X, Inbox } from "lucide-react";

export function Badge({ value }: { value: string }) {
  const label = value.replaceAll("_", " ").toLowerCase();
  const color =
    /^(online|install succeeded|download succeeded|available|admin)$/.test(
      label,
    )
      ? "green"
      : /failed|rejected|offline|disabled|withdrawn/.test(label)
        ? "red"
        : /waiting|pending|discovered|downloading|installing|operator/.test(
              label,
            )
          ? "blue"
          : "gray";
  return (
    <span className={`badge ${color}`}>
      <span />
      {label}
    </span>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <Inbox size={34} />
      <h3>{title}</h3>
      <p>{children || "New records will appear here when they are created."}</p>
    </div>
  );
}
export function Modal({
  title,
  children,
  close,
  busy = false,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
  busy?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="modal"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) close();
      }}
    >
      <header>
        <h2 id={titleId}>{title}</h2>
        <button
          type="button"
          className="icon-button"
          onClick={close}
          disabled={busy}
          aria-label="Close dialog"
        >
          <X size={20} />
        </button>
      </header>
      {children}
    </dialog>
  );
}
export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function Progress({ value }: { value: number | null }) {
  return (
    <div className="progress-row">
      <div className="progress-track">
        <span style={{ width: `${value ?? 0}%` }} />
      </div>
      <small>{value === null ? "Unknown" : `${value}%`}</small>
    </div>
  );
}
export function when(value?: string | null) {
  if (!value) return "Never";
  // SQLite timestamps are server UTC even when the driver omits a zone suffix.
  const normalized = /Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
  return new Date(normalized).toLocaleString();
}
export function bytes(value: number) {
  return value >= 1024 ** 3
    ? `${(value / 1024 ** 3).toFixed(2)} GB`
    : value >= 1024 ** 2
      ? `${(value / 1024 ** 2).toFixed(1)} MB`
      : `${value.toLocaleString()} bytes`;
}
