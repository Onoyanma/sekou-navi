import Link from "next/link";
import { ChevronRight, ExternalLink, Package } from "lucide-react";
import { surfaceClass } from "@/components/AppShell";
import { buildManualSearchLinks } from "@/lib/manualLinks";

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
  image: "画像が似ている",
  model: "型番が一致",
  maker: "メーカーが一致",
  name: "商品名が一致",
  keyword: "キーワードが一致",
  semantic: "意味が近い",
};

export type MatchConfidence = "high" | "medium" | "low";

const CONFIDENCE_BADGES: Record<
  MatchConfidence,
  { label: string; light: string; dark: string }
> = {
  high: {
    label: "確度 高",
    light: "bg-brand-600 text-white",
    dark: "bg-brand-500 text-brand-950",
  },
  medium: {
    label: "確度 中・型番を確認",
    light: "bg-amber-100 text-amber-800",
    dark: "bg-amber-900/60 text-amber-200",
  },
  low: {
    label: "確度 低・参考",
    light: "bg-ink-100 text-ink-600",
    dark: "bg-ink-800 text-ink-300",
  },
};

type ProductCardProps = {
  product: ProductCardProduct;
  darkMode: boolean;
  imageUrl: (path: string) => string;
  similarity?: number;
  combinedScore?: number;
  sources?: string[];
  ocrCandidate?: string;
  confidence?: MatchConfidence;
};

export function ProductCard({
  product,
  darkMode,
  imageUrl,
  similarity,
  combinedScore,
  sources,
  ocrCandidate,
  confidence,
}: ProductCardProps) {
  const imagePath = product.image_path?.split(",")[0] || "";
  const manualSearchLink = buildManualSearchLinks(
    product.maker,
    product.model_number
  )[0];
  const manualUrl = product.install_url || manualSearchLink?.url || "";
  const manualLabel = product.install_url ? "施工説明書" : "説明書を検索";

  const muted = darkMode ? "text-ink-400" : "text-ink-500";
  const hasEvidence =
    (sources && sources.length > 0) ||
    ocrCandidate ||
    (similarity !== undefined && similarity > 0) ||
    (combinedScore !== undefined && combinedScore > 0);

  return (
    <article className={`${surfaceClass(darkMode)} relative overflow-hidden p-3 sm:p-4`}>
      <div className="flex gap-3.5">
        <div
          className={`flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-2xl sm:h-24 sm:w-24 ${
            darkMode ? "bg-ink-800 text-ink-500" : "bg-ink-100 text-ink-300"
          }`}
        >
          {imagePath ? (
            <img
              src={imageUrl(imagePath)}
              alt=""
              loading="lazy"
              decoding="async"
              className="h-full w-full object-cover"
            />
          ) : (
            <Package size={28} />
          )}
        </div>

        <div className="min-w-0 flex-1">
          {confidence && (
            <span
              className={`mb-1.5 inline-block rounded-full px-2.5 py-0.5 text-xs font-bold ${
                darkMode
                  ? CONFIDENCE_BADGES[confidence].dark
                  : CONFIDENCE_BADGES[confidence].light
              }`}
            >
              {CONFIDENCE_BADGES[confidence].label}
            </span>
          )}

          <p className={`truncate text-xs ${muted}`}>
            {[product.maker, product.category].filter(Boolean).join(" ・ ") ||
              "未分類"}
          </p>
          <h2 className="mt-0.5 line-clamp-2 text-[17px] font-bold leading-snug">
            <Link
              href={`/products/${product.id}`}
              className="after:absolute after:inset-0 after:content-['']"
            >
              {product.product_name}
            </Link>
          </h2>
          <p
            className={`mt-0.5 truncate font-mono text-sm ${
              darkMode ? "text-ink-300" : "text-ink-600"
            }`}
          >
            {product.model_number}
          </p>
        </div>

        <ChevronRight
          size={20}
          className={`mt-1 hidden shrink-0 sm:block ${
            darkMode ? "text-ink-600" : "text-ink-300"
          }`}
        />
      </div>

      {product.memo && (
        <p className={`mt-3 line-clamp-2 text-sm leading-relaxed ${muted}`}>
          {product.memo}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {manualUrl && (
          <a
            href={manualUrl}
            target="_blank"
            rel="noreferrer noopener"
            className={`relative z-10 inline-flex min-h-10 items-center gap-1.5 rounded-full px-4 text-sm font-semibold transition ${
              product.install_url
                ? darkMode
                  ? "bg-brand-950 text-brand-300 hover:bg-brand-900"
                  : "bg-brand-50 text-brand-700 hover:bg-brand-100"
                : darkMode
                  ? "bg-ink-800 text-ink-300 hover:bg-ink-700"
                  : "bg-ink-100 text-ink-600 hover:bg-ink-200"
            }`}
          >
            <ExternalLink size={15} />
            {manualLabel}
          </a>
        )}
        {product.tags &&
          product.tags
            .split(",")
            .filter(Boolean)
            .slice(0, 3)
            .map((tag) => (
              <span
                key={tag}
                className={`rounded-full px-2.5 py-1 text-xs ${
                  darkMode ? "bg-ink-800 text-ink-400" : "bg-ink-50 text-ink-500"
                }`}
              >
                {tag}
              </span>
            ))}
      </div>

      {hasEvidence && (
        <details className="relative z-10 mt-3 group">
          <summary
            className={`flex min-h-8 cursor-pointer list-none items-center gap-1 text-xs font-medium ${muted}`}
          >
            <ChevronRight
              size={14}
              className="transition group-open:rotate-90"
            />
            判定の根拠
          </summary>
          <div className={`mt-2 space-y-1.5 text-xs ${muted}`}>
            {ocrCandidate && (
              <p>
                読み取った型番:{" "}
                <span className="font-mono font-semibold">{ocrCandidate}</span>
              </p>
            )}
            {sources && sources.length > 0 && (
              <p>{sources.map((s) => SOURCE_LABELS[s] || s).join(" ・ ")}</p>
            )}
            <p>
              {similarity !== undefined && similarity > 0 && (
                <>画像の類似度 {similarity.toFixed(2)}　</>
              )}
              {combinedScore !== undefined && combinedScore > 0 && (
                <>総合スコア {combinedScore.toFixed(0)}</>
              )}
            </p>
          </div>
        </details>
      )}
    </article>
  );
}
