import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactElement } from "react";
import {
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Search,
  X,
} from "./icons";
import { useApi } from "../hooks/useApi";
import type { Entity, RemoteOptions } from "../types";
import { list } from "../utils/format";

type AsyncSelectProps = {
  id: string;
  label: string;
  remote: RemoteOptions;
  values?: Record<string, any>;
  disabled?: boolean;
  required?: boolean;
};
type SingleAsyncSelectProps = AsyncSelectProps & {
  value: string;
  onChange: (value: string) => void;
  multiple?: false;
};
type MultipleAsyncSelectProps = AsyncSelectProps & {
  value: string[];
  onChange: (value: string[]) => void;
  multiple: true;
};

/** A single control with a searchable, paginated option list. */
export function AsyncSelect(props: SingleAsyncSelectProps): ReactElement;
export function AsyncSelect(props: MultipleAsyncSelectProps): ReactElement;
export function AsyncSelect({
  id,
  label,
  value,
  onChange,
  remote,
  values = {},
  disabled,
  required,
  multiple = false,
}: SingleAsyncSelectProps | MultipleAsyncSelectProps) {
  const emit = onChange as (next: string | string[]) => void;
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [activeIndex, setActiveIndex] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const path =
    typeof remote.path === "function" ? remote.path(values) : remote.path;
  const selectedValues = useMemo(
    () => (Array.isArray(value) ? value : value ? [value] : []),
    [value],
  );
  const query = useApi(
    `${path}${path.includes("?") ? "&" : "?"}page=${page}&size=20&search=${encodeURIComponent(search)}`,
    !disabled,
  );
  const records: Entity[] = list(query.data);
  const singleValue = typeof value === "string" ? value : "";
  const selected = useApi(
    `${remote.detailPath}/${encodeURIComponent(singleValue)}`,
    !!singleValue &&
      !disabled &&
      !records.some((record) => record.id === singleValue),
  );
  const selectedRecord =
    records.find((record) => record.id === singleValue) || selected.data;
  const selectedLabels = selectedValues
    .map((selectedValue) => {
      const record = records.find((item) => item.id === selectedValue);
      return record
        ? remote.label(record)
        : selectedValue === singleValue
          ? selectedRecord && remote.label(selectedRecord)
          : undefined;
    });
  const hasMore = (page + 1) * 20 < (query.data?.total ?? records.length);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  function changePage(nextPage: number) {
    setPage(nextPage);
    setActiveIndex(0);
  }

  function choose(record: Entity) {
    if (multiple) {
      emit(
        selectedValues.includes(record.id)
          ? selectedValues.filter((item) => item !== record.id)
          : [...selectedValues, record.id],
      );
      return;
    }
    emit(record.id);
    setOpen(false);
    setSearch("");
  }

  function remove(selectedValue: string) {
    if (multiple) emit(selectedValues.filter((item) => item !== selectedValue));
    else emit("");
  }

  function onTriggerKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex(0);
    }
    if (event.key === "Escape") setOpen(false);
  }

  function onSearchKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) =>
        Math.max(0, Math.min(current + 1, records.length - 1)),
      );
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter" && records[activeIndex]) {
      event.preventDefault();
      choose(records[activeIndex]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const summary = selectedValues.length
    ? selectedLabels.every(Boolean)
      ? selectedLabels.join(", ")
      : `${selectedValues.length} selected`
    : `Select ${label.toLowerCase()}`;

  return (
    <div ref={root} className="async-select">
      {multiple
        ? selectedValues.map((selectedValue) => (
            <input
              key={selectedValue}
              type="hidden"
              name={id}
              value={selectedValue}
            />
          ))
        : <input type="hidden" name={id} value={singleValue} />}
      <button
        id={id}
        type="button"
        className="async-select-trigger"
        role="combobox"
        aria-label={label}
        aria-controls={`${id}-options`}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-required={required || undefined}
        aria-describedby={`${id}-options-state`}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={onTriggerKeyDown}
      >
        <span className={selectedValues.length ? "" : "async-select-placeholder"}>
          {summary}
        </span>
        <ChevronDown aria-hidden="true" size={18} />
      </button>
      {multiple && selectedValues.length > 0 && (
        <div className="async-select-tags" aria-label={`Selected ${label.toLowerCase()}`}>
          {selectedValues.map((selectedValue, index) => (
            <span key={selectedValue} className="async-select-tag">
              {selectedLabels[index] || `Selected record (${selectedValue})`}
              <button
                type="button"
                aria-label={`Remove ${selectedLabels[index] || selectedValue}`}
                onClick={() => remove(selectedValue)}
                disabled={disabled}
              >
                <X size={13} />
              </button>
            </span>
          ))}
        </div>
      )}
      {open && (
        <div className="async-select-menu">
          <div className="async-select-search">
            <Search aria-hidden="true" size={16} />
            <input
              autoFocus
              aria-label={`Search ${label.toLowerCase()} options`}
              aria-controls={`${id}-options`}
              aria-activedescendant={
                records[activeIndex] ? `${id}-option-${activeIndex}` : undefined
              }
              placeholder={`Search ${label.toLowerCase()}…`}
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(0);
                setActiveIndex(0);
              }}
              onKeyDown={onSearchKeyDown}
            />
          </div>
          <div
            id={`${id}-options`}
            role="listbox"
            aria-label={`${label} options`}
            aria-multiselectable={multiple || undefined}
          >
            {query.isPending ? (
              <p className="async-select-empty">Loading options…</p>
            ) : records.length ? (
              records.map((record, index) => {
                const isSelected = selectedValues.includes(record.id);
                return (
                  <button
                    key={record.id}
                    id={`${id}-option-${index}`}
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    className={`async-select-option ${index === activeIndex ? "is-active" : ""}`}
                    onMouseMove={() => setActiveIndex(index)}
                    onClick={() => choose(record)}
                  >
                    {multiple && (
                      <span
                        className={`async-select-check ${isSelected ? "is-selected" : ""}`}
                      >
                        <Check size={14} />
                      </span>
                    )}
                    <span>{remote.label(record)}</span>
                    {!multiple && isSelected && <Check aria-label="Selected" size={16} />}
                  </button>
                );
              })
            ) : (
              <p className="async-select-empty">
                No matching {label.toLowerCase()} found.
              </p>
            )}
          </div>
          <div id={`${id}-options-state`} className="async-select-footer">
            <span>{query.data?.total ?? records.length} matching records</span>
            <span className="async-select-pagination">
              <button
                type="button"
                aria-label={`Previous ${label.toLowerCase()} options`}
                disabled={query.isPending || page === 0}
                onClick={() => changePage(page - 1)}
              >
                <ChevronLeft size={15} />
              </button>
              <span>Page {page + 1}</span>
              <button
                type="button"
                aria-label={`Next ${label.toLowerCase()} options`}
                disabled={query.isPending || !hasMore}
                onClick={() => changePage(page + 1)}
              >
                <ChevronRight size={15} />
              </button>
            </span>
          </div>
          {query.error && (
            <div role="alert" className="async-select-error">
              {query.error.message}{" "}
              <button type="button" onClick={() => void query.refetch()}>
                Retry
              </button>
            </div>
          )}
        </div>
      )}
      {required && <span className="sr-only">{label} is required.</span>}
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
