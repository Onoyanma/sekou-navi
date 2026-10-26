"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useTheme } from "@/components/AppShell";
import {
  fetchFieldSuggestions,
  loadFieldHistory,
  mergeSuggestions,
  saveFieldHistory,
  type SuggestionField,
} from "@/lib/fieldSuggestions";

type FieldAutocompleteInputProps = {
  field: SuggestionField;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  inputClassName?: string;
  labelClassName?: string;
  /** product_name の候補をメーカーで絞り込む */
  filterMaker?: string;
};

export function FieldAutocompleteInput({
  field,
  label,
  value,
  onChange,
  placeholder,
  disabled = false,
  inputClassName = "",
  labelClassName = "",
  filterMaker,
}: FieldAutocompleteInputProps) {
  const { darkMode } = useTheme();
  const listboxId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<number | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const loadSuggestions = useCallback(
    async (query: string) => {
      setLoading(true);

      try {
        const apiSuggestions = await fetchFieldSuggestions(field, query, {
          maker: field === "product_name" ? filterMaker : undefined,
        });
        const history = loadFieldHistory(field);
        setSuggestions(mergeSuggestions(apiSuggestions, history, query));
        setActiveIndex(-1);
      } catch (error) {
        console.error(error);
        const history = loadFieldHistory(field);
        setSuggestions(
          mergeSuggestions([], history, query).filter((item) =>
            query.trim()
              ? item.toUpperCase().includes(query.trim().toUpperCase())
              : true
          )
        );
      } finally {
        setLoading(false);
      }
    },
    [field, filterMaker]
  );

  useEffect(() => {
    if (!open) return;

    if (debounceRef.current) {
      window.clearTimeout(debounceRef.current);
    }

    debounceRef.current = window.setTimeout(() => {
      void loadSuggestions(value);
    }, 180);

    return () => {
      if (debounceRef.current) {
        window.clearTimeout(debounceRef.current);
      }
    };
  }, [value, open, loadSuggestions]);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, []);

  function commitValue(nextValue: string) {
    onChange(nextValue);
    saveFieldHistory(field, nextValue);
    setOpen(false);
    setActiveIndex(-1);
  }

  function handleBlur() {
    window.setTimeout(() => {
      if (value.trim()) {
        saveFieldHistory(field, value);
      }
      setOpen(false);
    }, 120);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      setOpen(true);
      return;
    }

    if (!open || suggestions.length === 0) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((prev) => (prev + 1) % suggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((prev) =>
        prev <= 0 ? suggestions.length - 1 : prev - 1
      );
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      commitValue(suggestions[activeIndex]);
    } else if (event.key === "Escape") {
      setOpen(false);
      setActiveIndex(-1);
    }
  }

  const dropdownClass = darkMode
    ? "absolute z-20 mt-1 max-h-52 w-full overflow-auto rounded-xl border border-slate-700 bg-slate-900 py-1 shadow-lg"
    : "absolute z-20 mt-1 max-h-52 w-full overflow-auto rounded-xl border border-slate-200 bg-white py-1 shadow-lg";

  const optionClass = (active: boolean) =>
    darkMode
      ? `flex w-full px-4 py-2.5 text-left text-sm ${
          active
            ? "bg-blue-600 text-white"
            : "text-slate-200 hover:bg-slate-800"
        }`
      : `flex w-full px-4 py-2.5 text-left text-sm ${
          active
            ? "bg-blue-600 text-white"
            : "text-slate-700 hover:bg-slate-50"
        }`;

  return (
    <div ref={containerRef} className="relative">
      <label className={labelClassName}>{label}</label>
      <input
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => {
          setOpen(true);
          void loadSuggestions(value);
        }}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        className={inputClassName}
        role="combobox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-autocomplete="list"
        autoComplete="off"
      />

      {open && (suggestions.length > 0 || loading) && (
        <ul id={listboxId} role="listbox" className={dropdownClass}>
          {loading && suggestions.length === 0 && (
            <li
              className={
                darkMode
                  ? "px-4 py-2.5 text-sm text-slate-400"
                  : "px-4 py-2.5 text-sm text-slate-500"
              }
            >
              候補を読み込み中...
            </li>
          )}
          {suggestions.map((suggestion, index) => (
            <li key={suggestion} role="option" aria-selected={activeIndex === index}>
              <button
                type="button"
                tabIndex={-1}
                className={optionClass(activeIndex === index)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => commitValue(suggestion)}
              >
                {suggestion}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
