import { useId } from "react";
import { DateTimePicker } from "./DateTimePicker";

export function DateRangeFilter({ from, to, onFrom, onTo }: {
  from: string;
  to: string;
  onFrom: (value: string) => void;
  onTo: (value: string) => void;
}) {
  const id = useId().replace(/:/g, "");
  return <div className="date-range-filter" role="group" aria-label="Date range">
    <DateTimePicker id={`${id}-from`} label="From date" value={from} dateOnly
      onChange={(value) => { onFrom(value); if (to && value > to) onTo(""); }} />
    <span className="date-range-separator" aria-hidden="true">–</span>
    <DateTimePicker id={`${id}-to`} label="To date" value={to} dateOnly
      onChange={(value) => { onTo(value); if (from && value < from) onFrom(""); }} />
    {(from || to) && <button type="button" className="date-range-clear" aria-label="Clear dates"
      onClick={() => { onFrom(""); onTo(""); }}>Clear</button>}
  </div>;
}
