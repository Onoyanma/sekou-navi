import { apiUrl } from "@/lib/api";

export type SuggestionField = "maker" | "product_name";

const HISTORY_KEY_PREFIX = "sekou_navi_history_";
const MAX_HISTORY = 20;

function historyKey(field: SuggestionField) {
  return `${HISTORY_KEY_PREFIX}${field}`;
}

export function loadFieldHistory(field: SuggestionField): string[] {
  if (typeof window === "undefined") return [];

  const raw = localStorage.getItem(historyKey(field));
  if (!raw) return [];

  try {
    const parsed = JSON.parse(raw) as string[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveFieldHistory(field: SuggestionField, value: string) {
  const trimmed = value.trim();
  if (!trimmed || trimmed === "未登録") return;

  const history = loadFieldHistory(field).filter(
    (item) => item.toLowerCase() !== trimmed.toLowerCase()
  );

  const next = [trimmed, ...history].slice(0, MAX_HISTORY);
  localStorage.setItem(historyKey(field), JSON.stringify(next));
}

function scoreLocalMatch(query: string, value: string): number {
  const q = query.trim().toUpperCase();
  const v = value.toUpperCase();

  if (!q) return 40;
  if (v.startsWith(q)) return 90 + q.length;
  if (v.includes(q)) return 75;
  return 0;
}

export function mergeSuggestions(
  apiSuggestions: string[],
  localHistory: string[],
  query: string,
  limit = 8
): string[] {
  const merged: Array<{ value: string; score: number }> = [];
  const seen = new Set<string>();

  for (const [index, value] of apiSuggestions.entries()) {
    const key = value.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push({ value, score: 120 - index });
  }

  for (const value of localHistory) {
    const key = value.toLowerCase();
    if (seen.has(key)) continue;

    const score = scoreLocalMatch(query, value);
    if (!query.trim() || score > 0) {
      seen.add(key);
      merged.push({ value, score: score + 10 });
    }
  }

  return merged
    .sort((a, b) => b.score - a.score || a.value.localeCompare(b.value, "ja"))
    .slice(0, limit)
    .map((item) => item.value);
}

export async function fetchFieldSuggestions(
  field: SuggestionField,
  query: string,
  options?: { maker?: string; limit?: number }
) {
  const params = new URLSearchParams({
    field,
    q: query,
    limit: String(options?.limit ?? 8),
  });

  if (options?.maker?.trim()) {
    params.set("maker", options.maker.trim());
  }

  const response = await fetch(
    apiUrl(`/field-suggestions?${params.toString()}`)
  );

  if (!response.ok) {
    return [];
  }

  const data = await response.json();
  return (data.suggestions || []) as string[];
}
