import { useState } from "react";
import { useApi } from "../hooks/useApi";
import type { Entity, RemoteOptions } from "../types";
import { list } from "../utils/format";

/** Native select keeps browser validation and keyboard support; search and paging are server-side. */
export function AsyncSelect({
  id,
  label,
  value,
  onChange,
  remote,
  values = {},
  disabled,
  required,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  remote: RemoteOptions;
  values?: Record<string, any>;
  disabled?: boolean;
  required?: boolean;
}) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const path =
    typeof remote.path === "function" ? remote.path(values) : remote.path;
  const query = useApi(
    `${path}${path.includes("?") ? "&" : "?"}page=${page}&size=20&search=${encodeURIComponent(search)}`,
    !disabled,
  );
  const records: Entity[] = list(query.data);
  const selected = useApi(
    `${remote.detailPath}/${encodeURIComponent(value)}`,
    !!value && !disabled && !records.some((r) => r.id === value),
  );
  const selectedRecord = records.find((r) => r.id === value) || selected.data;
  return (
    <div className="space-y-2">
      <input
        aria-label={`Search ${label.toLowerCase()} options`}
        placeholder={`Search ${label.toLowerCase()}…`}
        value={search}
        disabled={disabled}
        onChange={(event) => {
          setSearch(event.target.value);
          setPage(0);
        }}
      />
      <select
        id={id}
        name={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        required={required}
        aria-describedby={`${id}-options-state`}
      >
        <option value="">Select {label.toLowerCase()}</option>
        {value && !records.some((r) => r.id === value) && (
          <option value={value}>
            {selectedRecord
              ? remote.label(selectedRecord)
              : `Selected record (${value})`}
          </option>
        )}
        {records.map((record) => (
          <option key={record.id} value={record.id}>
            {remote.label(record)}
          </option>
        ))}
      </select>
      <div
        id={`${id}-options-state`}
        className="flex items-center justify-between gap-2 text-xs text-muted"
      >
        <span>
          {disabled
            ? "Select the related record first"
            : query.isPending
              ? "Loading options…"
              : `${query.data?.total ?? records.length} matching records · Page ${page + 1}`}
        </span>
        <span className="flex gap-2">
          <button
            type="button"
            className="text-link"
            disabled={disabled || query.isPending || page === 0}
            aria-label={`Previous ${label.toLowerCase()} options`}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </button>
          <button
            type="button"
            className="text-link"
            disabled={
              disabled ||
              query.isPending ||
              (page + 1) * 20 >= (query.data?.total ?? records.length)
            }
            aria-label={`Next ${label.toLowerCase()} options`}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </span>
      </div>
      {query.error && (
        <div role="alert" className="text-xs text-red-700">
          {query.error.message}{" "}
          <button
            type="button"
            className="text-link"
            onClick={() => void query.refetch()}
          >
            Retry options
          </button>
        </div>
      )}
      {selected.error && (
        <p role="alert" className="text-xs text-red-700">
          The selected record could not be loaded. Its saved ID is preserved.
        </p>
      )}
    </div>
  );
}

export function EntityName({
  path,
  id,
  fallback,
  field = "name",
}: {
  path: string;
  id?: string;
  fallback?: string;
  field?: string;
}) {
  const query = useApi(`${path}/${id}`, !!id && !fallback);
  if (fallback) return <>{fallback}</>;
  if (!id) return <>Not selected</>;
  return (
    <>
      {query.data?.[field] || (query.isPending ? "Loading…" : `Record ${id}`)}
    </>
  );
}
