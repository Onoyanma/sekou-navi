import Link from "next/link";
import { ExternalLink, Tag } from "lucide-react";

type ProductCardProduct = {
  id: number;
  maker: string;
  product_name: string;
  model_number: string;
  category: string;
  memo: string;
  tags: string;
  install_url: string;
  image_path: string;
};

const SOURCE_LABELS: Record<string, string> = {
  image: "画像類似",
  model: "型番一致",
  maker: "メーカー一致",
  name: "商品名一致",
  keyword: "キーワード一致",
  semantic: "意味が近い",
};

type ProductCardProps = {
  product: ProductCardProduct;
  darkMode: boolean;
  imageUrl: (path: string) => string;
  similarity?: number;
  combinedScore?: number;
  sources?: string[];
  ocrCandidate?: string;
};

export function ProductCard({
  product,
  darkMode,
  imageUrl,
  similarity,
  combinedScore,
  sources,
  ocrCandidate,
}: ProductCardProps) {
  const imagePath = product.image_path?.split(",")[0] || "";

  return (
    <article
      className={
        darkMode
          ? "overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-sm transition hover:border-slate-700"
          : "overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition hover:border-slate-300 hover:shadow-md"
      }
    >
      <div className="flex flex-col sm:flex-row">
        {imagePath && (
          <div
            className={
              darkMode
                ? "shrink-0 border-b border-slate-800 bg-slate-950 sm:w-44 sm:border-b-0 sm:border-r"
                : "shrink-0 border-b border-slate-100 bg-slate-50 sm:w-44 sm:border-b-0 sm:border-r"
            }
          >
            <img
              src={imageUrl(imagePath)}
              alt={product.product_name}
              loading="lazy"
              decoding="async"
              className="h-44 w-full object-cover sm:h-full sm:min-h-[11rem]"
            />
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col gap-4 p-5">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={
                  darkMode
                    ? "inline-flex items-center gap-1 rounded-full bg-slate-800 px-3 py-1 text-xs font-medium text-slate-200"
                    : "inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700"
                }
              >
                <Tag size={12} />
                {product.maker || "未登録"}
              </span>
              <span className="rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-700">
                {product.category}
              </span>
              {sources?.map((source) => (
                <span
                  key={source}
                  className={
                    source === "image"
                      ? "rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700"
                      : source === "model" || source === "keyword"
                        ? "rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-700"
                        : source === "maker"
                          ? "rounded-full bg-violet-100 px-3 py-1 text-xs font-semibold text-violet-700"
                          : source === "semantic"
                            ? "rounded-full bg-fuchsia-100 px-3 py-1 text-xs font-semibold text-fuchsia-700"
                            : "rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-700"
                  }
                >
                  {SOURCE_LABELS[source] || source}
                </span>
              ))}
              {similarity !== undefined && similarity > 0 && (
                <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
                  画像 {similarity.toFixed(2)}
                </span>
              )}
              {combinedScore !== undefined && combinedScore > 0 && (
                <span
                  className={
                    darkMode
                      ? "rounded-full bg-slate-800 px-3 py-1 text-xs font-medium text-slate-300"
                      : "rounded-full bg-slate-200 px-3 py-1 text-xs font-medium text-slate-600"
                  }
                >
                  スコア {combinedScore.toFixed(0)}
                </span>
              )}
            </div>

            {ocrCandidate && (
              <p
                className={
                  darkMode
                    ? "mt-2 text-xs text-blue-400"
                    : "mt-2 text-xs text-blue-600"
                }
              >
                読み取り型番: {ocrCandidate}
              </p>
            )}

            <h2
              className={
                darkMode
                  ? "mt-3 text-xl font-bold text-white"
                  : "mt-3 text-xl font-bold text-slate-900"
              }
            >
              {product.product_name}
            </h2>
            <p
              className={
                darkMode
                  ? "mt-1 font-mono text-sm text-slate-300"
                  : "mt-1 font-mono text-sm text-slate-600"
              }
            >
              {product.model_number}
            </p>
            {product.memo && (
              <p
                className={
                  darkMode
                    ? "mt-3 line-clamp-2 text-sm text-slate-400"
                    : "mt-3 line-clamp-2 text-sm text-slate-600"
                }
              >
                {product.memo}
              </p>
            )}
            {product.tags && (
              <p
                className={
                  darkMode
                    ? "mt-2 text-xs text-slate-500"
                    : "mt-2 text-xs text-slate-500"
                }
              >
                {product.tags}
              </p>
            )}
          </div>

          <div className="flex flex-wrap gap-2">
            <Link
              href={`/products/${product.id}`}
              className="inline-flex items-center justify-center rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700"
            >
              詳細を見る
            </Link>
            {product.install_url ? (
              <a
                href={product.install_url}
                target="_blank"
                rel="noreferrer"
                className={
                  darkMode
                    ? "inline-flex items-center gap-2 rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 hover:bg-slate-800"
                    : "inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                }
              >
                <ExternalLink size={16} />
                施工説明書
              </a>
            ) : (
              <span
                className={
                  darkMode
                    ? "inline-flex items-center rounded-xl bg-slate-800 px-4 py-2.5 text-sm text-slate-500"
                    : "inline-flex items-center rounded-xl bg-slate-100 px-4 py-2.5 text-sm text-slate-400"
                }
              >
                URL未登録
              </span>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}
