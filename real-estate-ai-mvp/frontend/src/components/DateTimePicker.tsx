import { useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight, Clock } from "./icons";

type DateTimePickerProps = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  required?: boolean;
};

const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function parts(value: string) {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!match) return null;
  const [, year, month, day, hour, minute] = match;
  return { year: Number(year), month: Number(month) - 1, day: Number(day), hour, minute };
}

function localValue(date: Date, hour: string, minute: string) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}T${hour}:${minute}`;
}

function dateLabel(date: Date) {
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

export function DateTimePicker({
  id,
  label,
  value,
  onChange,
  disabled,
  required,
}: DateTimePickerProps) {
  const parsed = parts(value);
  const selectedDate = parsed
    ? new Date(parsed.year, parsed.month, parsed.day)
    : undefined;
  const [open, setOpen] = useState(false);
  const [visibleMonth, setVisibleMonth] = useState(
    () => new Date(parsed?.year ?? new Date().getFullYear(), parsed?.month ?? new Date().getMonth(), 1),
  );
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const hour = parsed?.hour ?? "09";
  const minute = parsed?.minute ?? "00";
  const [hourDraft, setHourDraft] = useState(hour);
  const [minuteDraft, setMinuteDraft] = useState(minute);
  const monthLabel = new Intl.DateTimeFormat("en-IN", {
    month: "long",
    year: "numeric",
  }).format(visibleMonth);
  const days = useMemo(() => {
    const firstDay = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), 1).getDay();
    const count = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() + 1, 0).getDate();
    return Array.from({ length: firstDay + count }, (_, index) =>
      index < firstDay ? undefined : new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), index - firstDay + 1),
    );
  }, [visibleMonth]);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  useEffect(() => {
    setHourDraft(hour);
    setMinuteDraft(minute);
  }, [hour, minute]);

  function setDate(date: Date) {
    onChange(localValue(date, hour, minute));
  }

  function setTime(nextHour: string, nextMinute: string) {
    onChange(localValue(selectedDate || new Date(), nextHour, nextMinute));
  }

  function commitTime(part: "hour" | "minute") {
    const draft = part === "hour" ? hourDraft : minuteDraft;
    const current = part === "hour" ? hour : minute;
    const maximum = part === "hour" ? 23 : 59;
    const numeric = Number(draft);
    const next = Number.isInteger(numeric) && numeric >= 0 && numeric <= maximum
      ? String(numeric).padStart(2, "0")
      : current;

    if (part === "hour") {
      setHourDraft(next);
      setTime(next, minute);
    } else {
      setMinuteDraft(next);
      setTime(hour, next);
    }
  }

  return (
    <div ref={root} className="date-time-picker">
      <input type="hidden" name={id} value={value} />
      <button
        id={id}
        ref={trigger}
        type="button"
        className="date-time-picker-trigger"
        aria-label="Select date and time"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls={`${id}-calendar`}
        aria-required={required || undefined}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
        }}
      >
        <span className="date-time-picker-value">
          <CalendarDays aria-hidden="true" size={17} />
          {selectedDate ? `${dateLabel(selectedDate)} · ${hour}:${minute}` : `Select ${label.toLowerCase()}`}
        </span>
        <ChevronDown aria-hidden="true" size={18} />
      </button>
      {open && (
        <div
          id={`${id}-calendar`}
          role="dialog"
          aria-label={`Choose ${label.toLowerCase()}`}
          className="date-time-picker-menu"
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              setOpen(false);
              trigger.current?.focus();
            }
          }}
        >
          <div className="date-time-picker-header">
            <button type="button" aria-label="Previous month" onClick={() => setVisibleMonth((month) => new Date(month.getFullYear(), month.getMonth() - 1, 1))}>
              <ChevronLeft size={17} />
            </button>
            <strong>{monthLabel}</strong>
            <button type="button" aria-label="Next month" onClick={() => setVisibleMonth((month) => new Date(month.getFullYear(), month.getMonth() + 1, 1))}>
              <ChevronRight size={17} />
            </button>
          </div>
          <div className="date-time-picker-weekdays">
            {weekdays.map((weekday) => <span key={weekday}>{weekday}</span>)}
          </div>
          <div className="date-time-picker-days">
            {days.map((date, index) =>
              date ? (
                <button
                  key={date.toISOString()}
                  type="button"
                  aria-label={new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric" }).format(date)}
                  aria-pressed={selectedDate?.getTime() === date.getTime()}
                  className={selectedDate?.getTime() === date.getTime() ? "selected" : ""}
                  onClick={() => setDate(date)}
                >
                  {date.getDate()}
                </button>
              ) : <span key={`blank-${index}`} />,
            )}
          </div>
          <div className="date-time-picker-time">
            <Clock aria-hidden="true" size={16} />
            <div className="date-time-picker-time-fields" aria-label="Time">
              <input
                aria-label="Hour"
                inputMode="numeric"
                maxLength={2}
                value={hourDraft}
                onChange={(event) => /^\d{0,2}$/.test(event.target.value) && setHourDraft(event.target.value)}
                onBlur={() => commitTime("hour")}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    commitTime("hour");
                    event.currentTarget.blur();
                  }
                }}
              />
              <span aria-hidden="true">:</span>
              <input
                aria-label="Minutes"
                inputMode="numeric"
                maxLength={2}
                value={minuteDraft}
                onChange={(event) => /^\d{0,2}$/.test(event.target.value) && setMinuteDraft(event.target.value)}
                onBlur={() => commitTime("minute")}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    commitTime("minute");
                    event.currentTarget.blur();
                  }
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
