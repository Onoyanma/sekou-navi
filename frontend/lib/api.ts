/**
 * バックエンド API の接続先。
 * `.env.local` などで NEXT_PUBLIC_API_BASE_URL を設定すると切り替えられる。
 */
export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

/** API のパス（例: "/products"）から完全な URL を作る */
export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

/** DB に保存された画像パス（例: "images/1_xxx.jpg"）から表示用 URL を作る */
export function productImageUrl(imagePath: string): string {
  if (!imagePath) return "";
  if (/^https?:\/\//.test(imagePath)) return imagePath;

  const normalized = imagePath.startsWith("/")
    ? imagePath.slice(1)
    : imagePath;

  return `${API_BASE_URL}/${encodeURI(normalized)}`;
}
