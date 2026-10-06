import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode, FormEvent } from "react";
import {
  AlertCircle,
  ArrowLeft,
  Check,
  ChevronLeft,
  ChevronRight,
  Inbox,
  LoaderCircle,
  Search,
  X,
} from "./icons";
import { Link } from "react-router-dom";
import type { Entity, Field, Page } from "../types";
import { label } from "../utils/format";
import { AsyncSelect } from "./AsyncSelect";
import { DateTimePicker } from "./DateTimePicker";
import { DateRangeFilter } from "./DateRangeFilter";
import { inDateRange } from "../utils/dateFilter";
import { CustomSelect } from "./CustomSelect";
import { ContactLink } from "./ContactLink";
import { usePageMetadata } from "../hooks/usePageMetadata";
export function Badge({ value }: { value: unknown }) {
  const s = String(value || "UNKNOWN");
  return (
    <span
      className={`badge ${/ACTIVE|AVAILABLE|QUALIFIED|COMPLETED|PUBLISHED|CONFIRMED|ACCEPTED|DELIVERED|SUCCESS|DONE|SENT|READ/.test(s) ? "badge-green" : /FAILED|LOST|CANCELLED|SOLD|ERROR|REJECTED|DO_NOT_CALL|HOT/.test(s) ? "badge-red" : /PENDING|RESERVED|REQUESTED|PROCESSING|NEW|UPLOADED|PARSING|EMBEDDING|SCHEDULED|DIALING|REVIEW|CHECK_PAGES|WARM/.test(s) ? "badge-amber" : "badge-neutral"}`}
    >
      {label(value)}
    </span>
  );
}
export function PageHeader({
  title,
  description,
  action,
  back,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  back?: string;
}) {
  usePageMetadata(title, typeof description === "string" ? description : undefined);
  return (
    <div className="page-heading">
      <div>
        {back && (
          <Link className="back-link" to={back}>
            <ArrowLeft size={15} /> Back
          </Link>
        )}
        <h1>{title}</h1>
        {description && <p className="text-muted mt-2">{description}</p>}
      </div>
      {action && <div className="flex flex-wrap gap-2">{action}</div>}
    </div>
  );
}
export function Empty({
  title = "Nothing here yet",
  description = "Add your first record to get started.",
}: {
  title?: string;
  description?: string;
}) {
  return (
    <div className="empty-state">
      <Inbox size={30} />
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}
export function Loading() {
  return (
    <div role="status" aria-label="Loading" className="space-y-4 p-6">
      <div className="skeleton h-8 w-2/5" />
      <div className="skeleton h-24" />
      <div className="skeleton h-24" />
      <span className="sr-only">Loading…</span>
    </div>
  );
}
export function ErrorState({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  return (
    <div role="alert" className="error-state">
      <AlertCircle size={22} />
      <div>
        <h3>We couldn’t complete that request</h3>
        <p>{error instanceof Error ? error.message : String(error)}</p>
        {retry && (
          <button className="btn-secondary mt-3" onClick={retry}>
            Try again
          </button>
        )}
      </div>
    </div>
  );
}
export function Async({
  query,
  children,
}: {
  query: { isPending: boolean; error: unknown; refetch: () => unknown };
  children: ReactNode;
}) {
  return query.isPending ? (
    <Loading />
  ) : query.error ? (
    <ErrorState error={query.error} retry={() => query.refetch()} />
  ) : (
    <>{children}</>
  );
}
export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    d?.showModal();
    return () => d?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="modal-header">
        <h2>{title}</h2>
        <button
          className="icon-btn"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      <div className="p-6">{children}</div>
    </dialog>
  );
}
export function RecordForm({
  fields,
  initial = {},
  onSubmit,
  onCancel,
  submitLabel = "Save changes",
  danger = false,
}: {
  fields: Field[];
  initial?: Record<string, any>;
  onSubmit: (data: Record<string, any>) => Promise<void>;
  onCancel?: () => void;
  submitLabel?: string;
  danger?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [values, setValues] = useState(initial);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const values: Record<string, any> = {};
    for (const f of fields) {
      const value = String(fd.get(f.name) || "").trim();
      values[f.name] =
        f.type === "number"
          ? value === ""
            ? null
            : Number(value)
          : f.type === "datetime-local"
            ? value
              ? new Date(value).toISOString()
              : null
            : value || null;
    }
    const missing = fields.find(
      (field) => field.required && (values[field.name] == null || values[field.name] === ""),
    );
    if (missing) {
      setError(new Error(`${missing.label} is required.`));
      return;
    }
    for (const [min, max] of [
      ["budgetMin", "budgetMax"],
      ["areaMin", "areaMax"],
    ]) {
      if (
        values[min] != null &&
        values[max] != null &&
        values[min] > values[max]
      ) {
        setError(new Error(`${label(min)} must not exceed ${label(max)}.`));
        return;
      }
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit(values);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-5">
      {error != null && <ErrorState error={error} />}
      <div className="form-grid">
        {fields.map((f) => {
          let value = values[f.name] ?? "";
          if (
            f.type === "datetime-local" &&
            value &&
            /Z$|[+-]\d{2}:\d{2}$/.test(value)
          ) {
            const d = new Date(value);
            value = new Date(d.getTime() - d.getTimezoneOffset() * 60000)
              .toISOString()
              .slice(0, 16);
          }
          const props = {
            id: f.name,
            name: f.name,
            required: f.required,
            value: String(value),
            onChange: (
              e: React.ChangeEvent<
                HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
              >,
            ) =>
              setValues((previous) => {
                const next = { ...previous, [f.name]: e.target.value };
                for (const dependent of fields.filter(
                  (field) => field.dependsOn === f.name,
                )) {
                  next[dependent.name] = "";
                }
                return next;
              }),
            disabled: busy || !!(f.dependsOn && !values[f.dependsOn]),
          };
          return (
            <div key={f.name} className={f.wide ? "md:col-span-2" : ""}>
              <label className="field-label" htmlFor={f.name}>
                {f.label}
                {f.required && <span aria-hidden="true" className="text-red-500"> *</span>}
              </label>
              {f.remote ? (
                <AsyncSelect
                  key={`${f.name}:${f.dependsOn ? values[f.dependsOn] : ""}`}
                  id={f.name}
                  label={f.label}
                  value={String(value)}
                  values={values}
                  remote={f.remote}
                  required={f.required}
                  disabled={props.disabled}
                  onChange={(nextValue) => {
                    setValues((previous) => {
                      const next = { ...previous, [f.name]: nextValue };
                      for (const dependent of fields.filter(
                        (field) => field.dependsOn === f.name,
                      ))
                        next[dependent.name] = "";
                      return next;
                    });
                  }}
                />
              ) : f.type === "datetime-local" ? (
                <DateTimePicker
                  id={f.name}
                  label={f.label}
                  value={String(value)}
                  required={f.required}
                  disabled={props.disabled}
                  onChange={(nextValue) =>
                    setValues((previous) => ({ ...previous, [f.name]: nextValue }))
                  }
                />
              ) : f.options ? (
                <CustomSelect
                  id={f.name}
                  label={f.label}
                  value={String(value)}
                  required={f.required}
                  disabled={props.disabled}
                  placeholder={`Select ${f.label.toLowerCase()}`}
                  onChange={(nextValue) => props.onChange({ target: { value: nextValue } } as React.ChangeEvent<HTMLSelectElement>)}
                  options={f.options
                    .filter(
                      (o) =>
                        !f.dependsOn || o.parentValue === values[f.dependsOn],
                    )
                    .map((o) => ({ value: o.value, label: o.label }))}
                />
              ) : f.type === "textarea" ? (
                <textarea {...props} rows={f.name === "content" ? 10 : 3} />
              ) : (
                <input
                  {...props}
                  type={f.type || "text"}
                  min={f.min}
                  max={f.max}
                  step={f.step || "any"}
                  onKeyDown={(event) => {
                    if (f.type === "number" && ["ArrowUp", "ArrowDown"].includes(event.key))
                      event.preventDefault();
                  }}
                />
              )}{" "}
              {f.hint && <p className="field-hint">{f.hint}</p>}
            </div>
          );
        })}
      </div>
      <div className="flex justify-end gap-3 pt-2">
        {onCancel && (
          <button
            type="button"
            className="btn-secondary"
            onClick={onCancel}
            disabled={busy}
          >
            Cancel
          </button>
        )}
        <button className={danger ? "btn-danger" : "btn-primary"} disabled={busy} type="submit">
          {busy ? (
            <LoaderCircle size={16} className="animate-spin" />
          ) : (
            <Check size={16} />
          )}{" "}
          {busy ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
export type Column = {
  key: string;
  label: string;
  render?: (item: Entity) => ReactNode;
};
export function DataTable({
  data,
  columns,
  empty,
  actions,
  dateFilter = true,
}: {
  data: Entity[];
  columns: Column[];
  empty?: string;
  actions?: (item: Entity) => ReactNode;
  dateFilter?: boolean;
}) {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const dateColumn = columns.find((column) => /(?:At|Date|timestamp)$/i.test(column.key));
  const dateKey = dateColumn?.key || ["scheduledAt", "createdAt", "updatedAt", "lastAssignedAt"]
    .find((key) => data?.some((row) => typeof row[key] === "string"));
  const showDateFilter = dateFilter && !!dateKey;
  const rows = showDateFilter ? data.filter((row) => inDateRange(row[dateKey], dateFrom, dateTo)) : data;
  return (
    <div className="table-container">
      {showDateFilter && <div className="table-date-filter"><DateRangeFilter from={dateFrom} to={dateTo}
        onFrom={setDateFrom} onTo={setDateTo} /></div>}
      {!rows?.length ? <Empty title={empty || "No results found"}
        description="Try changing your filters or add a new record." /> : <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key}>{c.label}</th>
            ))}
            {actions && (
              <th>
                <span className="sr-only">Actions</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              {columns.map((c) => (
                <td key={c.key}>
                  {c.render ? c.render(row) : String(row[c.key] ?? "—")}
                </td>
              ))}
              {actions && <td>{actions(row)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      </div>}
    </div>
  );
}
export function Filters({
  search,
  onSearch,
  status,
  onStatus,
  statuses,
  sort,
  onSort,
  sortOptions,
  dateFrom,
  dateTo,
  onDateFrom,
  onDateTo,
}: {
  search: string;
  onSearch: (s: string) => void;
  status: string;
  onStatus: (s: string) => void;
  statuses: string[];
  sort?: string;
  onSort?: (s: string) => void;
  sortOptions?: { value: string; label: string }[];
  dateFrom?: string;
  dateTo?: string;
  onDateFrom?: (value: string) => void;
  onDateTo?: (value: string) => void;
}) {
  return (
    <div className="filters">
      <div className="search-box">
        <Search size={17} />
        <input
          className="search-box-input"
          aria-label="Search records"
          placeholder="Search records…"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
        />
      </div>
      <CustomSelect id="filter-status" label="Filter by status" value={status} onChange={onStatus} placeholder="All statuses" options={statuses.map((s) => ({ value: s, label: label(s) }))} />
      {onSort && (
        <CustomSelect id="sort-records" label="Sort records" value={sort || ""} onChange={onSort} options={sortOptions || [{ value: "createdAt,desc", label: "Newest first" }, { value: "createdAt,asc", label: "Oldest first" }]} />
      )}
      {onDateFrom && onDateTo && <DateRangeFilter from={dateFrom || ""} to={dateTo || ""}
        onFrom={onDateFrom} onTo={onDateTo} />}
    </div>
  );
}
export function Pagination({
  data,
  page,
  setPage,
}: {
  data?: Page;
  page: number;
  setPage: (v: number) => void;
}) {
  const total = data?.total || 0,
    size = data?.size || 10;
  return (
    <div className="pagination">
      <span>
        {total
          ? `${page * size + 1}–${Math.min((page + 1) * size, total)} of ${total} results`
          : "0 results"}
      </span>
      <div className="flex gap-2">
        <button
          className="icon-btn"
          disabled={page === 0}
          onClick={() => setPage(page - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft size={18} />
        </button>
        <span className="p-2">Page {page + 1}</span>
        <button
          className="icon-btn"
          disabled={(page + 1) * size >= total}
          onClick={() => setPage(page + 1)}
          aria-label="Next page"
        >
          <ChevronRight size={18} />
        </button>
      </div>
    </div>
  );
}
export function Details({
  data,
  fields,
}: {
  data: Record<string, any>;
  fields: string[];
}) {
  return (
    <dl className="details-grid">
      {fields.map((f) => (
        <div key={f}>
          <dt>{label(f.replace(/([A-Z])/g, " $1"))}</dt>
          <dd>
            {data[f] == null || data[f] === ""
              ? "Not provided"
              : (f === "phone" || f === "email") && typeof data[f] === "string"
                ? <ContactLink kind={f} value={data[f]} />
              : typeof data[f] === "object"
                ? JSON.stringify(data[f])
                : String(data[f])}
          </dd>
        </div>
      ))}
    </dl>
  );
}
const ToastContext = createContext<(message: string) => void>(() => {});
export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(() => setMessage(""), 4500);
    return () => clearTimeout(t);
  }, [message]);
  return (
    <ToastContext.Provider value={setMessage}>
      {children}
      {message && (
        <div role="status" className="toast">
          <Check size={18} />
          {message}
          <button
            aria-label="Dismiss notification"
            onClick={() => setMessage("")}
          >
            <X size={16} />
          </button>
        </div>
      )}
    </ToastContext.Provider>
  );
}
export const useToast = () => useContext(ToastContext);
