/**
 * 施工説明書を探すための外部検索リンク。
 * 登録済みの商品に説明書の URL が無いときや、未登録の型番を見つけたときの入り口として使う。
 */
export type ManualLink = {
  label: string;
  url: string;
};

function googleSearchUrl(query: string): string {
  return `https://www.google.com/search?q=${encodeURIComponent(query)}`;
}

export function buildManualSearchLinks(
  maker: string,
  modelNumber: string
): ManualLink[] {
  const model = modelNumber.trim();
  if (!model) return [];

  const makerName = maker.trim();
  const base = makerName ? `${makerName} ${model}` : model;

  return [
    { label: "施工説明書を検索", url: googleSearchUrl(`${base} 施工説明書`) },
    { label: "取扱説明書（PDF）を検索", url: googleSearchUrl(`${base} 取扱説明書 PDF`) },
  ];
}
