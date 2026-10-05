export function dateBounds(from: string, to: string) {
  const start = from ? new Date(`${from}T00:00:00`) : null;
  const end = to ? new Date(`${to}T00:00:00`) : null;
  if (end) end.setDate(end.getDate() + 1);
  return {
    dateFrom: start && !Number.isNaN(start.getTime()) ? start.toISOString() : "",
    dateTo: end && !Number.isNaN(end.getTime()) ? end.toISOString() : "",
  };
}

export function inDateRange(value: unknown, from: string, to: string) {
  if (!from && !to) return true;
  if (typeof value !== "string" || !value) return false;
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return false;
  const bounds = dateBounds(from, to);
  return (!bounds.dateFrom || timestamp >= Date.parse(bounds.dateFrom))
    && (!bounds.dateTo || timestamp < Date.parse(bounds.dateTo));
}
