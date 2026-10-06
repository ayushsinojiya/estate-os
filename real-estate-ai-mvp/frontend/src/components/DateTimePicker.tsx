import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight, Clock } from "./icons";

type DateTimePickerProps = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  required?: boolean;
  dateOnly?: boolean;
};

const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function parts(value: string) {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);
  if (!match) return null;
  const [, year, month, day, hour, minute] = match;
  return { year: Number(year), month: Number(month) - 1, day: Number(day), hour: hour || "09", minute: minute || "00" };
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
  dateOnly = false,
}: DateTimePickerProps) {
  const parsed = parts(value);
  const selectedDate = parsed
    ? new Date(parsed.year, parsed.month, parsed.day)
    : undefined;
  const [open, setOpen] = useState(false);
  const [calendarView, setCalendarView] = useState<"days" | "months" | "years">("days");
  const [visibleMonth, setVisibleMonth] = useState(
    () => new Date(parsed?.year ?? new Date().getFullYear(), parsed?.month ?? new Date().getMonth(), 1),
  );
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const hour = parsed?.hour ?? "09";
  const minute = parsed?.minute ?? "00";
  const [hourDraft, setHourDraft] = useState(hour);
  const [minuteDraft, setMinuteDraft] = useState(minute);
  const monthName = new Intl.DateTimeFormat("en-IN", { month: "long" }).format(visibleMonth);
  const yearStart = visibleMonth.getFullYear() - 5;
  const days = useMemo(() => {
    const firstDay = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), 1).getDay();
    const count = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() + 1, 0).getDate();
    return Array.from({ length: firstDay + count }, (_, index) =>
      index < firstDay ? undefined : new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), index - firstDay + 1),
    );
  }, [visibleMonth]);
  const today = new Date();
  const todayKey = `${today.getFullYear()}-${today.getMonth()}-${today.getDate()}`;

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

  useLayoutEffect(() => {
    if (!open) return;

    function positionMenu() {
      const button = trigger.current;
      const popup = menu.current;
      if (!button || !popup) return;

      const viewport = window.visualViewport;
      const viewportLeft = viewport?.offsetLeft ?? 0;
      const viewportTop = viewport?.offsetTop ?? 0;
      const viewportWidth = viewport?.width ?? window.innerWidth;
      const viewportHeight = viewport?.height ?? window.innerHeight;
      const margin = 16;
      const gap = 6;
      const dialog = root.current?.closest("dialog")?.getBoundingClientRect();
      const leftLimit = Math.max(viewportLeft + margin, (dialog?.left ?? viewportLeft) + margin);
      const rightLimit = Math.min(viewportLeft + viewportWidth - margin, (dialog?.right ?? viewportLeft + viewportWidth) - margin);
      const width = Math.min(440, Math.max(1, rightLimit - leftLimit));
      const buttonRect = button.getBoundingClientRect();

      popup.style.position = "fixed";
      popup.style.width = `${width}px`;
      popup.style.maxHeight = `${Math.max(1, viewportHeight - margin * 2)}px`;
      popup.style.left = `${Math.max(leftLimit, Math.min(buttonRect.left, rightLimit - width))}px`;

      const popupHeight = Math.min(popup.getBoundingClientRect().height, viewportHeight - margin * 2);
      const bottomLimit = viewportTop + viewportHeight - margin;
      const below = bottomLimit - buttonRect.bottom - gap;
      const above = buttonRect.top - viewportTop - margin - gap;
      const preferredTop = below >= popupHeight || below >= above
        ? buttonRect.bottom + gap
        : buttonRect.top - popupHeight - gap;
      popup.style.top = `${Math.max(viewportTop + margin, Math.min(preferredTop, bottomLimit - popupHeight))}px`;
    }

    positionMenu();
    document.addEventListener("scroll", positionMenu, true);
    window.addEventListener("resize", positionMenu);
    window.visualViewport?.addEventListener("resize", positionMenu);
    window.visualViewport?.addEventListener("scroll", positionMenu);
    return () => {
      document.removeEventListener("scroll", positionMenu, true);
      window.removeEventListener("resize", positionMenu);
      window.visualViewport?.removeEventListener("resize", positionMenu);
      window.visualViewport?.removeEventListener("scroll", positionMenu);
    };
  }, [open, visibleMonth, calendarView]);

  function setDate(date: Date) {
    onChange(dateOnly ? localValue(date, hour, minute).slice(0, 10) : localValue(date, hour, minute));
    if (dateOnly) setOpen(false);
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
        aria-label={dateOnly ? `Select ${label.toLowerCase()}` : "Select date and time"}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls={`${id}-calendar`}
        aria-required={required || undefined}
        disabled={disabled}
        onClick={() => { setCalendarView("days"); setOpen((current) => !current); }}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
        }}
      >
        <span className="date-time-picker-value">
          <CalendarDays aria-hidden="true" size={17} />
          {selectedDate ? `${dateLabel(selectedDate)}${dateOnly ? "" : ` · ${hour}:${minute}`}` : `Select ${label.toLowerCase()}`}
        </span>
        <ChevronDown aria-hidden="true" size={18} />
      </button>
      {open && (
        <div
          ref={menu}
          id={`${id}-calendar`}
          role="dialog"
          aria-label={`Choose ${label.toLowerCase()}`}
          className={`date-time-picker-menu${dateOnly ? " date-only" : ""}`}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              setOpen(false);
              trigger.current?.focus();
            }
          }}
        >
          <div className="date-time-picker-header">
            <button type="button" aria-label={calendarView === "days" ? "Previous month" : calendarView === "months" ? "Previous year" : "Previous 12 years"} onClick={() => setVisibleMonth((month) => new Date(month.getFullYear() - (calendarView === "years" ? 12 : calendarView === "months" ? 1 : 0), month.getMonth() - (calendarView === "days" ? 1 : 0), 1))}>
              <ChevronLeft size={17} />
            </button>
            <div className="date-time-picker-heading">
              <button type="button" aria-label="Choose month" aria-pressed={calendarView === "months"} onClick={() => setCalendarView(calendarView === "months" ? "days" : "months")}>{monthName}</button>
              <button type="button" aria-label="Choose year" aria-pressed={calendarView === "years"} onClick={() => setCalendarView(calendarView === "years" ? "days" : "years")}>{visibleMonth.getFullYear()}</button>
            </div>
            <button type="button" aria-label={calendarView === "days" ? "Next month" : calendarView === "months" ? "Next year" : "Next 12 years"} onClick={() => setVisibleMonth((month) => new Date(month.getFullYear() + (calendarView === "years" ? 12 : calendarView === "months" ? 1 : 0), month.getMonth() + (calendarView === "days" ? 1 : 0), 1))}>
              <ChevronRight size={17} />
            </button>
          </div>
          {calendarView === "days" && <><div className="date-time-picker-weekdays">
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
                  aria-current={`${date.getFullYear()}-${date.getMonth()}-${date.getDate()}` === todayKey ? "date" : undefined}
                  className={`${selectedDate?.getTime() === date.getTime() ? "selected" : ""} ${`${date.getFullYear()}-${date.getMonth()}-${date.getDate()}` === todayKey ? "today" : ""}`.trim()}
                  onClick={() => setDate(date)}
                >
                  {date.getDate()}
                </button>
              ) : <span key={`blank-${index}`} />,
            )}
          </div></>}
          {calendarView === "months" && <div className="date-time-picker-choices">
            {Array.from({ length: 12 }, (_, month) => <button key={month} type="button"
              aria-pressed={visibleMonth.getMonth() === month}
              onClick={() => { setVisibleMonth(new Date(visibleMonth.getFullYear(), month, 1)); setCalendarView("days"); }}>
              {new Intl.DateTimeFormat("en-IN", { month: "long" }).format(new Date(2026, month, 1))}
            </button>)}
          </div>}
          {calendarView === "years" && <div className="date-time-picker-choices">
            {Array.from({ length: 12 }, (_, offset) => yearStart + offset).map((year) => <button key={year} type="button"
              aria-pressed={visibleMonth.getFullYear() === year}
              onClick={() => { setVisibleMonth(new Date(year, visibleMonth.getMonth(), 1)); setCalendarView("days"); }}>
              {year}
            </button>)}
          </div>}
          <div className="date-time-picker-footer">
            <button type="button" onClick={() => { setVisibleMonth(new Date(today.getFullYear(), today.getMonth(), 1)); setDate(today); }}>Today</button>
          </div>
          {!dateOnly && <div className="date-time-picker-time">
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
          </div>}
        </div>
      )}
    </div>
  );
}
