export type ProductAutocompleteSuggestion = {
  maker: string;
  product_name: string;
  model_number: string;
  category: string;
  tags: string;
  memo: string;
  official_url: string;
  manual_url: string;
  install_url: string;
  confidence: number;
  sources: string[];
  model_candidates: Array<{ model_number: string; score: number }>;
  page_title: string;
  notes: string[];
  matched_product: {
    id: number;
    maker: string;
    product_name: string;
    model_number: string;
    category: string;
    tags: string;
    memo: string;
    score: number;
  } | null;
};

export async function fetchProductAutocomplete(params: {
  modelNumber?: string;
  url?: string;
}): Promise<ProductAutocompleteSuggestion> {
  const response = await fetch("http://127.0.0.1:8000/autocomplete-product", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model_number: params.modelNumber?.trim() || "",
      url: params.url?.trim() || "",
    }),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      (data as { detail?: string }).detail || "自動補完に失敗しました"
    );
  }

  return response.json();
}

export const AUTOCOMPLETE_SOURCE_LABELS: Record<string, string> = {
  url: "Webページ",
  json_ld: "構造化データ",
  url_path: "URL内型番",
  model_rules: "型番ルール",
  database: "登録済みDB",
  text: "テキスト解析",
};
