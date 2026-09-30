import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Search } from "./icons";

export type SelectOption = { value: string; label: string };

export function CustomSelect({ id, label, value, options, onChange, placeholder, disabled, required, name = id }: {
  id: string; label: string; value: string; options: SelectOption[]; onChange: (value: string) => void;
  placeholder?: string; disabled?: boolean; required?: boolean; name?: string;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const selected = options.find((option) => option.value === value);
  const filtered = useMemo(() => options.filter((option) => option.label.toLowerCase().includes(search.toLowerCase())), [options, search]);
  useEffect(() => {
    const close = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  return <div ref={root} className="async-select">
    <input type="hidden" name={name} value={value} />
    <button id={id} type="button" role="combobox" className="async-select-trigger" aria-label={label} aria-expanded={open} aria-controls={`${id}-options`} aria-haspopup="listbox" aria-required={required || undefined} disabled={disabled} onClick={() => setOpen((current) => !current)} onKeyDown={(event) => event.key === "Escape" && setOpen(false)}>
      <span className={selected ? "" : "async-select-placeholder"}>{selected?.label || placeholder || `Select ${label.toLowerCase()}`}</span><ChevronDown aria-hidden="true" size={18} />
    </button>
    {open && <div className="async-select-menu">
      {options.length > 6 && <div className="async-select-search"><Search aria-hidden="true" size={16} /><input autoFocus aria-label={`Search ${label.toLowerCase()} options`} placeholder={`Search ${label.toLowerCase()}…`} value={search} onChange={(event) => setSearch(event.target.value)} /></div>}
      <div id={`${id}-options`} role="listbox" aria-label={`${label} options`} className="custom-select-options">
        {filtered.map((option) => <button key={option.value} type="button" role="option" aria-selected={option.value === value} className="async-select-option" onClick={() => { onChange(option.value); setOpen(false); setSearch(""); }}><span>{option.label}</span>{option.value === value && <Check aria-label="Selected" size={16} />}</button>)}
        {!filtered.length && <p className="async-select-empty">No matching options.</p>}
      </div>
    </div>}
  </div>;
}
