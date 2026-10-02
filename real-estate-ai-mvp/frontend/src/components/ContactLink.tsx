export function ContactLink({ kind, value }: { kind: "phone" | "email"; value: string }) {
  const text = value.trim();
  if (kind === "phone") {
    const number = text.replace(/[^\d+]/g, "");
    if (/^\+?\d{6,15}$/.test(number)) {
      return <a className="text-link" href={`tel:${number}`}>{text}</a>;
    }
  } else if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text)) {
    return <a className="text-link" href={`mailto:${text}`}>{text}</a>;
  }
  return <>{text || "Not provided"}</>;
}
