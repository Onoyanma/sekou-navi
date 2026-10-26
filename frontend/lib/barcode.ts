import { apiUrl } from "@/lib/api";

const CODE_QUERY_KEYS = [
  "model",
  "model_number",
  "modelno",
  "product_code",
  "code",
  "jan",
  "barcode",
  "sku",
  "品番",
  "型番",
];

export type ParsedBarcode = {
  raw: string;
  terms: string[];
  primary: string;
};

export type BarcodeRegisterDraft = {
  modelNumber: string;
  scannedCode: string;
  terms: string[];
};

export const BARCODE_REGISTER_DRAFT_KEY = "sekou_navi_barcode_register_draft";

/** スキャン値を検索用キーワードに分解（表示用・クライアント側） */
export function parseScannedCode(raw: string): ParsedBarcode {
  const trimmed = raw.trim();
  if (!trimmed) {
    return { raw: "", terms: [], primary: "" };
  }

  const terms: string[] = [];

  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      const data = JSON.parse(trimmed) as Record<string, unknown>;
      if (data && typeof data === "object" && !Array.isArray(data)) {
        for (const key of [
          "model_number",
          "model",
          "product_code",
          "jan",
          "barcode",
          "code",
          "品番",
          "型番",
        ]) {
          const value = data[key];
          if (typeof value === "string" && value.trim()) {
            terms.push(value.trim());
          }
        }
      }
    } catch {
      // ignore invalid JSON
    }
  }

  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
    try {
      const url = new URL(trimmed);
      for (const key of CODE_QUERY_KEYS) {
        const values = url.searchParams.getAll(key);
        for (const value of values) {
          if (value.trim()) {
            terms.push(value.trim());
          }
        }
      }
      for (const part of url.pathname.split("/")) {
        const decoded = decodeURIComponent(part).trim();
        if (decoded.length >= 4) {
          terms.push(decoded);
        }
      }
    } catch {
      terms.push(trimmed);
    }
  } else {
    terms.push(trimmed);
  }

  const seen = new Set<string>();
  const uniqueTerms: string[] = [];

  for (const term of terms) {
    const key = term.toLowerCase();
    if (!term || seen.has(key)) continue;
    seen.add(key);
    uniqueTerms.push(term);
  }

  return {
    raw: trimmed,
    terms: uniqueTerms,
    primary: uniqueTerms[0] || "",
  };
}

export function saveBarcodeRegisterDraft(draft: BarcodeRegisterDraft) {
  sessionStorage.setItem(BARCODE_REGISTER_DRAFT_KEY, JSON.stringify(draft));
}

export function loadBarcodeRegisterDraft(): BarcodeRegisterDraft | null {
  const raw = sessionStorage.getItem(BARCODE_REGISTER_DRAFT_KEY);
  if (!raw) return null;

  try {
    return JSON.parse(raw) as BarcodeRegisterDraft;
  } catch {
    return null;
  }
}

export function clearBarcodeRegisterDraft() {
  sessionStorage.removeItem(BARCODE_REGISTER_DRAFT_KEY);
}

export function buildRegisterUrl(draft: BarcodeRegisterDraft): string {
  const params = new URLSearchParams();
  params.set("model_number", draft.modelNumber);
  if (draft.scannedCode) {
    params.set("code", draft.scannedCode);
  }
  return `/register?${params.toString()}`;
}

export async function searchByBarcode(code: string) {
  const response = await fetch(
    apiUrl(`/barcode-search?code=${encodeURIComponent(code)}`)
  );

  if (!response.ok) {
    throw new Error("バーコード検索に失敗しました");
  }

  return response.json() as Promise<{
    results: Array<{
      product: Record<string, unknown>;
      score: number;
      match_types: string[];
      matched_term: string;
    }>;
    parsed: ParsedBarcode;
  }>;
}

export async function registerProduct(payload: {
  maker: string;
  product_name: string;
  model_number: string;
  category: string;
  memo?: string;
  tags?: string;
}) {
  const response = await fetch(apiUrl("/products"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      maker: payload.maker || "未登録",
      product_name: payload.product_name || "未登録",
      model_number: payload.model_number,
      category: payload.category,
      memo: payload.memo || "",
      tags: payload.tags || "",
    }),
  });

  if (!response.ok) {
    throw new Error("商品の登録に失敗しました");
  }

  return response.json() as Promise<{
    id: number;
    message: string;
    tags?: string;
    auto_tags_added?: string[];
  }>;
}
