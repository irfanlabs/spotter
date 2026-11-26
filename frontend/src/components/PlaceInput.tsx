import { useEffect, useId, useRef, useState } from "react";
import { searchPlaces } from "../api";
import type { Place } from "../types";
import { IconPin } from "./Icons";

interface Props {
  label: string;
  value: string;
  place: Place | null;
  error?: string;
  placeholder?: string;
  onText: (text: string) => void;
  onPlace: (place: Place | null) => void;
}

export function PlaceInput({ label, value, place, error, placeholder, onText, onPlace }: Props) {
  const id = useId();
  const listId = `${id}-list`;
  const [options, setOptions] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [loading, setLoading] = useState(false);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Debounced, cancellable lookup. Skipped once a place has been chosen.
  useEffect(() => {
    if (place || value.trim().length < 3) {
      setOptions([]);
      setLoading(false);
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const { results } = await searchPlaces(value.trim(), ctrl.signal);
        setOptions(results);
        setLookupError(null);
        setActive(results.length ? 0 : -1);
      } catch (e) {
        if (ctrl.signal.aborted) return;
        setOptions([]);
        setLookupError("Search is unavailable right now. Try again in a moment.");
      } finally {
        if (!ctrl.signal.aborted) setLoading(false);
      }
    }, 280);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [value, place]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const choose = (p: Place) => {
    onPlace(p);
    onText(p.label);
    setOpen(false);
    setOptions([]);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (!open || !options.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % options.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a - 1 + options.length) % options.length);
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      choose(options[active]);
    } else if (e.key === "Escape") setOpen(false);
  };

  const showList = open && value.trim().length >= 3 && !place;

  return (
    <div className="field" ref={wrapRef}>
      <label htmlFor={id}>{label}</label>
      <div className={`input-wrap ${error ? "has-error" : ""}`}>
        <IconPin className="input-icon" />
        <input
          id={id}
          type="text"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-invalid={!!error}
          aria-describedby={error ? `${id}-err` : undefined}
          aria-activedescendant={active >= 0 && showList ? `${id}-opt-${active}` : undefined}
          autoComplete="off"
          placeholder={placeholder}
          value={value}
          onChange={(e) => {
            onText(e.target.value);
            if (place) onPlace(null);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKey}
        />
        {loading && <span className="spinner sm" aria-label="Searching" />}
      </div>
      {showList && (
        <ul className="suggestions" id={listId} role="listbox">
          {options.map((o, i) => (
            <li
              key={o.label}
              id={`${id}-opt-${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : ""}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(o);
              }}
              onMouseEnter={() => setActive(i)}
            >
              <IconPin width={15} height={15} />
              <span>{o.label}</span>
            </li>
          ))}
          {loading && !options.length && <li className="empty">Searching…</li>}
          {!loading && !options.length && <li className="empty">{lookupError ?? "No matches. Try adding a city or state."}</li>}
        </ul>
      )}
      {error && (
        <p className="field-error" id={`${id}-err`}>
          {error}
        </p>
      )}
    </div>
  );
}
