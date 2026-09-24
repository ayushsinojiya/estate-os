export const label = (v: unknown) =>
  String(v ?? "—")
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
export const money = (v: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
    notation: "compact",
  }).format(v || 0);
export const date = (v: string | undefined) =>
  v
    ? new Date(v).toLocaleString("en-IN", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Not scheduled";
export const bytes = (value: number | undefined) => {
  const size = Number(value || 0);
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
};
export const options = (items: string[]) =>
  items.map((value) => ({ value, label: label(value) }));
export const languages = [
  { value: "en", label: "English" },
  { value: "hi", label: "हिन्दी · Hindi" },
  { value: "gu", label: "ગુજરાતી · Gujarati" },
  { value: "mr", label: "मराठी · Marathi" },
];
export const list = (data: any) =>
  Array.isArray(data) ? data : data?.items || [];
