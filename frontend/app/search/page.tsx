"use client";

import { useEffect, useRef, useState } from "react";
import {
  Camera,
  Clock,
  Image as ImageIcon,
  Images,
  Loader2,
  Package,
  Search,
  Sparkles,
  TriangleAlert,
  X,
} from "lucide-react";
import { AppShell, surfaceClass, useTheme } from "@/components/AppShell";
import { ProductCard, type MatchConfidence } from "@/components/ProductCard";
import { UnregisteredModelPanel } from "@/components/UnregisteredModelPanel";
import { downscaleImage } from "@/lib/image";
import {
  productImageUrl,
  toProduct,
  type Product,
} from "@/lib/products";
import { apiUrl } from "@/lib/api";

type SimilarImageResult = {
  similarity: number;
  combined_score?: number;
  sources?: string[];
  ocr_candidate?: string;
  confidence?: MatchConfidence;
  product: Product;
};

type ImageSearchInsight = {
  top_confidence: MatchConfidence | "none";
  detected_maker: string;
  ocr_candidates: Array<{ model_number: string; score: number }>;
  product_name_hints: string[];
};

type SelectedSearchImage = {
  id: string;
  file: File;
  previewUrl: string;
};

type SearchTab = "keyword" | "image";

// 自信を持って特定できなかったときは、関係の薄い候補を並べすぎない
const LOW_CONFIDENCE_RESULT_LIMIT = 3;
type TextSearchMode = "keyword" | "semantic" | "hybrid";

type TextSearchResult = {
  product: Product;
  score?: number;
  keyword_score?: number;
  semantic_score?: number;
  similarity?: number;
  sources?: string[];
};

export default function SearchPage() {
  return (
    <AppShell
      title="検索"
      description="キーワード・自然文・画像から、登録済みの施工商品を探します"
    >
      <SearchContent />
    </AppShell>
  );
}

function SearchContent() {
  const { darkMode } = useTheme();
  const [keyword, setKeyword] = useState("");
  const [textSearchMode, setTextSearchMode] = useState<TextSearchMode>("hybrid");
  const [searchResultsState, setSearchResults] = useState<TextSearchResult[]>(
    []
  );
  // キーワードが空のときは結果を表示しない
  const searchResults = keyword.trim() ? searchResultsState : [];
  const [textSearchLoading, setTextSearchLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [searchHistory, setSearchHistory] = useState<string[]>([]);
  const [searchTab, setSearchTab] = useState<SearchTab>("keyword");
  const [imageSearchFiles, setImageSearchFiles] = useState<SelectedSearchImage[]>(
    []
  );
  const [imageSearchLoading, setImageSearchLoading] = useState(false);
  const [similarImageResults, setSimilarImageResults] = useState<
    SimilarImageResult[]
  >([]);
  const [imageSearchInsight, setImageSearchInsight] =
    useState<ImageSearchInsight | null>(null);
  const [imageSearchError, setImageSearchError] = useState("");
  const imageInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // localStorage はブラウザでしか読めないため、表示後に一度だけ読み込む
    try {
      const savedHistory = localStorage.getItem("sekou_navi_search_history");
      if (savedHistory) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setSearchHistory(JSON.parse(savedHistory));
      }
    } catch {
      localStorage.removeItem("sekou_navi_search_history");
    }
  }, []);

  async function runTextSearch(
    searchKeyword: string,
    mode: TextSearchMode = textSearchMode
  ) {
    const trimmed = searchKeyword.trim();

    if (!trimmed) {
      setSearchResults([]);
      return;
    }

    setTextSearchLoading(true);

    try {
      const response = await fetch(
        apiUrl(`/ai-search?q=${encodeURIComponent(trimmed)}&mode=${mode}&limit=20`)
      );

      if (!response.ok) {
        setSearchResults([]);
        return;
      }

      const data = await response.json();

      setSearchResults(
        (data.results || []).map(
          (item: {
            product: Record<string, unknown>;
            score?: number;
            keyword_score?: number;
            semantic_score?: number;
            similarity?: number;
            sources?: string[];
          }) => ({
            product: toProduct(item.product),
            score: item.score,
            keyword_score: item.keyword_score,
            semantic_score: item.semantic_score,
            similarity: item.similarity,
            sources: item.sources,
          })
        )
      );
    } catch (error) {
      console.error(error);
      setSearchResults([]);
    } finally {
      setTextSearchLoading(false);
    }
  }

  useEffect(() => {
    if (searchTab !== "keyword") return;

    const trimmed = keyword.trim();
    if (!trimmed) return;

    const timer = window.setTimeout(() => {
      void runTextSearch(trimmed, textSearchMode);
    }, 300);

    return () => window.clearTimeout(timer);
  }, [keyword, textSearchMode, searchTab]);

  function revokeImagePreviews(images: SelectedSearchImage[]) {
    for (const image of images) {
      URL.revokeObjectURL(image.previewUrl);
    }
  }

  function clearImageSearch() {
    revokeImagePreviews(imageSearchFiles);
    setImageSearchFiles([]);
    setSimilarImageResults([]);
    setImageSearchInsight(null);
    setImageSearchError("");
    if (imageInputRef.current) {
      imageInputRef.current.value = "";
    }
    void runTextSearch(keyword, textSearchMode);
  }

  function removeImageSearchFile(id: string) {
    const removed = imageSearchFiles.find((image) => image.id === id);
    if (removed) {
      URL.revokeObjectURL(removed.previewUrl);
    }

    const nextFiles = imageSearchFiles.filter((image) => image.id !== id);
    setImageSearchFiles(nextFiles);
    if (imageInputRef.current) {
      imageInputRef.current.value = "";
    }

    if (nextFiles.length === 0) {
      setSimilarImageResults([]);
      setImageSearchInsight(null);
      void runTextSearch(keyword, textSearchMode);
      return;
    }

    runImageSearch(nextFiles.map((image) => image.file));
  }

  async function addImageSearchFiles(selectedFiles: File[]) {
    if (selectedFiles.length === 0) return;

    // 通信が遅くても待たされないよう、送る前に写真を縮小する
    const resizedFiles = await Promise.all(
      selectedFiles.map((file) => downscaleImage(file))
    );

    const newImages: SelectedSearchImage[] = resizedFiles.map((file) => ({
      id: `${file.name}_${file.lastModified}_${Math.random()}`,
      file,
      previewUrl: URL.createObjectURL(file),
    }));

    const nextFiles = [...imageSearchFiles, ...newImages];
    setImageSearchFiles(nextFiles);
    runImageSearch(nextFiles.map((image) => image.file));
  }

  async function runImageSearch(files?: File[]) {
    const targetFiles = files ?? imageSearchFiles.map((image) => image.file);
    if (targetFiles.length === 0) return;

    setImageSearchError("");

    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      setImageSearchError(
        "インターネットに接続されていません。電波の良い場所で再度お試しいただくか、型番がわかる場合はキーワード検索を使ってください。"
      );
      return;
    }

    setImageSearchLoading(true);
    setSimilarImageResults([]);
    setImageSearchInsight(null);

    const formData = new FormData();
    for (const file of targetFiles) {
      formData.append("files", file);
    }

    try {
      const response = await fetch(
        apiUrl("/similar-search?top_k=10"),
        { method: "POST", body: formData }
      );

      if (!response.ok) {
        setSimilarImageResults([]);
        setImageSearchError(
          "写真の解析に失敗しました。もう一度お試しください。"
        );
        return;
      }

      const data = await response.json();
      setSimilarImageResults(
        (data.results || []).map(
          (item: {
            product: Record<string, unknown>;
            similarity: number;
            combined_score?: number;
            sources?: string[];
            ocr_candidate?: string;
            confidence?: MatchConfidence;
          }) => ({
            similarity: item.similarity ?? 0,
            combined_score: item.combined_score,
            sources: item.sources,
            ocr_candidate: item.ocr_candidate,
            confidence: item.confidence,
            product: toProduct(item.product),
          })
        )
      );
      setImageSearchInsight({
        top_confidence: data.top_confidence || "none",
        detected_maker: data.detected_maker || "",
        ocr_candidates: data.ocr_candidates || [],
        product_name_hints: data.product_name_hints || [],
      });
    } catch (error) {
      console.error(error);
      setImageSearchError(
        "通信に失敗しました。電波の良い場所で、もう一度お試しください。"
      );
    } finally {
      setImageSearchLoading(false);
    }
  }

  async function fetchSuggestions(value: string) {
    if (!value) {
      setSuggestions([]);
      return;
    }

    const response = await fetch(
      apiUrl(`/search-suggestions?q=${encodeURIComponent(value)}`)
    );
    const data = await response.json();
    setSuggestions(data.suggestions || []);
  }

  function saveSearchHistory(value: string) {
    if (!value.trim()) return;

    const updatedHistory = [
      value,
      ...searchHistory.filter((item) => item !== value),
    ].slice(0, 8);

    setSearchHistory(updatedHistory);
    localStorage.setItem(
      "sekou_navi_search_history",
      JSON.stringify(updatedHistory)
    );
  }

  function switchToKeywordSearch(model: string) {
    revokeImagePreviews(imageSearchFiles);
    setImageSearchFiles([]);
    setSimilarImageResults([]);
    setImageSearchInsight(null);
    setImageSearchError("");
    setKeyword(model);
    setSearchTab("keyword");
  }

  const isImageSearchMode = imageSearchFiles.length > 0;
  const topOcrCandidate = imageSearchInsight?.ocr_candidates[0]?.model_number || "";
  const isLowConfidence =
    imageSearchInsight?.top_confidence === "low" ||
    imageSearchInsight?.top_confidence === "none";
  const hasKeywordSearch = keyword.trim().length > 0;

  const modeHint: Record<TextSearchMode, string> = {
    keyword: "型番・メーカー名などのキーワード一致で探します",
    semantic: "「トイレの水栓の部品」のような自然文で意味検索します",
    hybrid: "キーワード一致と意味検索の両方を組み合わせます（おすすめ）",
  };

  const placeholder: Record<TextSearchMode, string> = {
    keyword: "例：TOTO、TCF、トイレ",
    semantic: "例：トイレの止水栓の部品、キッチンの水栓",
    hybrid: "例：TOTO トイレ 部品、洗面の水栓を探したい",
  };

  const inputClass = darkMode
    ? "w-full rounded-xl border border-slate-700 bg-slate-950 py-3 pl-11 pr-4 text-white outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
    : "w-full rounded-xl border border-slate-200 bg-white py-3 pl-11 pr-4 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20";

  const chipClass = darkMode
    ? "rounded-full bg-slate-800 px-3 py-1.5 text-sm text-slate-200 hover:bg-blue-600 hover:text-white"
    : "rounded-full bg-slate-100 px-3 py-1.5 text-sm text-slate-700 hover:bg-blue-600 hover:text-white";

  const tabBase =
    "flex flex-1 items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition";

  return (
    <div className="space-y-6">
      <div className={`${surfaceClass(darkMode)} p-5 md:p-6`}>
        <div
          className={
            darkMode
              ? "mb-5 flex rounded-xl bg-slate-800 p-1"
              : "mb-5 flex rounded-xl bg-slate-100 p-1"
          }
        >
          <button
            type="button"
            onClick={() => setSearchTab("keyword")}
            className={
              searchTab === "keyword"
                ? `${tabBase} ${
                    darkMode
                      ? "bg-slate-900 text-white shadow-sm"
                      : "bg-white text-slate-900 shadow-sm"
                  }`
                : `${tabBase} ${darkMode ? "text-slate-400" : "text-slate-500"}`
            }
          >
            <Search size={18} />
            キーワード
          </button>
          <button
            type="button"
            onClick={() => setSearchTab("image")}
            className={
              searchTab === "image"
                ? `${tabBase} ${
                    darkMode
                      ? "bg-slate-900 text-white shadow-sm"
                      : "bg-white text-slate-900 shadow-sm"
                  }`
                : `${tabBase} ${darkMode ? "text-slate-400" : "text-slate-500"}`
            }
          >
            <Images size={18} />
            画像
          </button>
        </div>

        {searchTab === "keyword" && (
          <div className="space-y-4">
            <div
              className={
                darkMode
                  ? "flex flex-wrap gap-2 rounded-xl bg-slate-950 p-1"
                  : "flex flex-wrap gap-2 rounded-xl bg-slate-100 p-1"
              }
            >
              {(
                [
                  { id: "hybrid", label: "AI統合", icon: Sparkles },
                  { id: "keyword", label: "キーワード", icon: Search },
                  { id: "semantic", label: "意味検索", icon: Sparkles },
                ] as const
              ).map((item) => {
                const Icon = item.icon;
                const active = textSearchMode === item.id;

                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setTextSearchMode(item.id)}
                    className={
                      active
                        ? "inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white sm:text-sm"
                        : darkMode
                          ? "inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium text-slate-400 hover:bg-slate-800 sm:text-sm"
                          : "inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium text-slate-600 hover:bg-white sm:text-sm"
                    }
                  >
                    <Icon size={16} />
                    {item.label}
                  </button>
                );
              })}
            </div>

            <p
              className={
                darkMode ? "text-sm text-slate-400" : "text-sm text-slate-500"
              }
            >
              {modeHint[textSearchMode]}
            </p>

            <div className="relative">
              <Search
                size={18}
                className={
                  darkMode
                    ? "absolute left-4 top-1/2 -translate-y-1/2 text-slate-500"
                    : "absolute left-4 top-1/2 -translate-y-1/2 text-slate-400"
                }
              />
              <input
                value={keyword}
                onChange={(e) => {
                  const value = e.target.value;
                  setKeyword(value);
                  fetchSuggestions(value);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    void runTextSearch(keyword, textSearchMode);
                    saveSearchHistory(keyword);
                    setSuggestions([]);
                  }
                }}
                placeholder={placeholder[textSearchMode]}
                className={inputClass}
              />
              {textSearchLoading && (
                <Loader2
                  size={18}
                  className="absolute right-4 top-1/2 -translate-y-1/2 animate-spin text-blue-500"
                />
              )}
            </div>

            {searchHistory.length > 0 && (
              <div>
                <p
                  className={`mb-2 flex items-center gap-2 text-sm font-semibold ${
                    darkMode ? "text-slate-300" : "text-slate-600"
                  }`}
                >
                  <Clock size={16} />
                  最近の検索
                </p>
                <div className="flex flex-wrap gap-2">
                  {searchHistory.map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => {
                        setKeyword(item);
                        void runTextSearch(item, textSearchMode);
                      }}
                      className={chipClass}
                    >
                      {item}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {suggestions.length > 0 && (
              <div>
                <p
                  className={`mb-2 text-sm font-semibold ${
                    darkMode ? "text-slate-300" : "text-slate-600"
                  }`}
                >
                  候補
                </p>
                <div className="flex flex-wrap gap-2">
                  {suggestions.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => {
                        setKeyword(suggestion);
                        setSuggestions([]);
                        void runTextSearch(suggestion, textSearchMode);
                      }}
                      className={chipClass}
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {searchTab === "image" && (
          <div className="space-y-4">
            <p
              className={
                darkMode ? "text-sm text-slate-400" : "text-sm text-slate-500"
              }
            >
              写真から画像の類似・型番・メーカー・商品名を読み取り、登録済み商品を探します
            </p>
            <ul
              className={
                darkMode
                  ? "list-inside list-disc space-y-1 rounded-xl bg-slate-950 p-4 text-sm text-slate-400"
                  : "list-inside list-disc space-y-1 rounded-xl bg-slate-50 p-4 text-sm text-slate-600"
              }
            >
              <li>型番ラベルに近づいて、文字が画面いっぱいになるように撮る</li>
              <li>照明の反射や影を避け、ラベルに正面から向ける</li>
              <li>読めないときは、ラベルだけを写した写真を追加する</li>
            </ul>

            <input
              ref={imageInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={(e) => {
                void addImageSearchFiles(Array.from(e.target.files || []));
                e.target.value = "";
              }}
            />
            <input
              ref={cameraInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={(e) => {
                void addImageSearchFiles(Array.from(e.target.files || []));
                e.target.value = "";
              }}
            />

            <div className="flex flex-wrap items-start gap-3">
              <button
                type="button"
                onClick={() => cameraInputRef.current?.click()}
                disabled={imageSearchLoading}
                className="flex h-24 w-24 shrink-0 flex-col items-center justify-center gap-1 rounded-2xl bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                <Camera size={28} />
                <span className="text-sm font-semibold">撮影</span>
              </button>
              <button
                type="button"
                onClick={() => imageInputRef.current?.click()}
                disabled={imageSearchLoading}
                className={
                  darkMode
                    ? "flex h-24 w-24 shrink-0 flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed border-slate-700 bg-slate-950 text-slate-400 hover:border-emerald-500 hover:text-emerald-400 disabled:opacity-50"
                    : "flex h-24 w-24 shrink-0 flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed border-slate-300 bg-slate-50 text-slate-500 hover:border-emerald-500 hover:text-emerald-600 disabled:opacity-50"
                }
              >
                {imageSearchLoading ? (
                  <Loader2 size={24} className="animate-spin" />
                ) : (
                  <>
                    <ImageIcon size={24} />
                    <span className="text-xs font-medium">追加</span>
                  </>
                )}
              </button>

              {imageSearchFiles.map((image) => (
                <div key={image.id} className="relative shrink-0">
                  <img
                    src={image.previewUrl}
                    alt={image.file.name}
                    className="h-24 w-24 rounded-2xl border object-cover shadow-sm"
                  />
                  <button
                    type="button"
                    onClick={() => removeImageSearchFile(image.id)}
                    disabled={imageSearchLoading}
                    className="absolute -right-2 -top-2 flex h-7 w-7 items-center justify-center rounded-full bg-red-500 text-white shadow hover:bg-red-600 disabled:opacity-50"
                  >
                    <X size={16} />
                  </button>
                </div>
              ))}
            </div>

            {imageSearchFiles.length > 0 && (
              <div className="flex flex-wrap items-center gap-3">
                <p
                  className={
                    darkMode ? "text-sm text-slate-400" : "text-sm text-slate-500"
                  }
                >
                  {imageSearchLoading
                    ? `${imageSearchFiles.length}枚を解析中...（10秒ほどかかることがあります）`
                    : `${imageSearchFiles.length}枚で検索済み`}
                </p>
                {!imageSearchLoading && (
                  <button
                    type="button"
                    onClick={clearImageSearch}
                    className={
                      darkMode
                        ? "text-sm font-medium text-red-400 hover:text-red-300"
                        : "text-sm font-medium text-red-600 hover:text-red-700"
                    }
                  >
                    すべて削除
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {isImageSearchMode && imageSearchInsight && !imageSearchLoading && (
        <div className={`${surfaceClass(darkMode)} p-4 md:p-5`}>
          <p
            className={
              darkMode
                ? "text-sm font-semibold text-white"
                : "text-sm font-semibold text-slate-900"
            }
          >
            画像から読み取った情報
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {imageSearchInsight.detected_maker && (
              <span className="rounded-full bg-violet-100 px-3 py-1 text-xs font-semibold text-violet-700">
                メーカー: {imageSearchInsight.detected_maker}
              </span>
            )}
            {imageSearchInsight.ocr_candidates.slice(0, 4).map((candidate) => (
              <span
                key={candidate.model_number}
                className="rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-700"
              >
                型番 {candidate.model_number}
              </span>
            ))}
          </div>
        </div>
      )}

      {imageSearchError && (
        <div
          role="alert"
          className={
            darkMode
              ? "flex flex-wrap items-center gap-3 rounded-xl border border-red-900 bg-red-950/50 px-4 py-3 text-sm text-red-300"
              : "flex flex-wrap items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
          }
        >
          <span className="flex-1">{imageSearchError}</span>
          {imageSearchFiles.length > 0 && (
            <button
              type="button"
              onClick={() => void runImageSearch()}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700"
            >
              もう一度解析する
            </button>
          )}
        </div>
      )}

      {isImageSearchMode && imageSearchInsight && !imageSearchLoading && (
        <>
          {imageSearchInsight.top_confidence === "high" && (
            <p
              className={
                darkMode
                  ? "rounded-xl border border-emerald-800 bg-emerald-950/50 px-4 py-3 text-sm text-emerald-300"
                  : "rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800"
              }
            >
              型番が一致する商品が見つかりました。
            </p>
          )}
          {imageSearchInsight.top_confidence === "medium" && (
            <p
              className={
                darkMode
                  ? "rounded-xl border border-amber-800 bg-amber-950/50 px-4 py-3 text-sm text-amber-300"
                  : "rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
              }
            >
              候補です。実物のラベルの型番と一致するか確認してください。
            </p>
          )}
          {isLowConfidence && (
            <div
              role="status"
              className={
                darkMode
                  ? "flex flex-col gap-3 rounded-xl border border-amber-800 bg-amber-950/50 px-4 py-3 text-sm text-amber-300 sm:flex-row sm:items-center"
                  : "flex flex-col gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 sm:flex-row sm:items-center"
              }
            >
              <div className="flex flex-1 items-start gap-3">
                <TriangleAlert size={18} className="mt-0.5 shrink-0" />
                <span>
                  自信を持って特定できませんでした。表示している結果は参考です。型番がわかる場合は、型番を入力して探してください。
                </span>
              </div>
              <button
                type="button"
                onClick={() => switchToKeywordSearch(topOcrCandidate)}
                className="rounded-lg bg-amber-600 px-4 py-3 text-sm font-semibold text-white hover:bg-amber-700 sm:shrink-0 sm:py-2"
              >
                型番を入力して探す
              </button>
            </div>
          )}
          {isLowConfidence && topOcrCandidate && (
            <UnregisteredModelPanel
              darkMode={darkMode}
              modelNumber={topOcrCandidate}
              maker={imageSearchInsight.detected_maker}
            />
          )}
        </>
      )}

      {isImageSearchMode ? (
        <section className="space-y-4">
          <h2
            className={`flex items-center gap-2 text-lg font-bold ${
              darkMode ? "text-white" : "text-slate-900"
            }`}
          >
            <Images size={20} className="text-emerald-600" />
            類似画像の商品
            <span
              className={
                darkMode
                  ? "rounded-full bg-slate-800 px-2.5 py-0.5 text-sm font-medium text-slate-300"
                  : "rounded-full bg-slate-100 px-2.5 py-0.5 text-sm font-medium text-slate-600"
              }
            >
              {similarImageResults.length}件
            </span>
          </h2>

          {similarImageResults.length > 0 ? (
            <div className="grid gap-4">
              {(isLowConfidence
                ? similarImageResults.slice(0, LOW_CONFIDENCE_RESULT_LIMIT)
                : similarImageResults
              ).map((item, index) => (
                <ProductCard
                  key={`${item.product.id}_${index}`}
                  product={item.product}
                  darkMode={darkMode}
                  imageUrl={productImageUrl}
                  similarity={item.similarity}
                  combinedScore={item.combined_score}
                  sources={item.sources}
                  ocrCandidate={item.ocr_candidate}
                  confidence={item.confidence}
                />
              ))}
            </div>
          ) : (
            !imageSearchLoading && (
              <div
                className={`${surfaceClass(darkMode)} p-10 text-center text-sm ${
                  darkMode ? "text-slate-400" : "text-slate-500"
                }`}
              >
                類似する商品が見つかりませんでした
              </div>
            )
          )}
        </section>
      ) : hasKeywordSearch ? (
        <section className="space-y-4">
          <h2
            className={`flex items-center gap-2 text-lg font-bold ${
              darkMode ? "text-white" : "text-slate-900"
            }`}
          >
            <Package size={20} className="text-blue-600" />
            検索結果
            <span
              className={
                darkMode
                  ? "rounded-full bg-slate-800 px-2.5 py-0.5 text-sm font-medium text-slate-300"
                  : "rounded-full bg-slate-100 px-2.5 py-0.5 text-sm font-medium text-slate-600"
              }
            >
              {searchResults.length}件
            </span>
          </h2>

          {textSearchLoading ? (
            <div
              className={`${surfaceClass(darkMode)} flex items-center justify-center gap-2 p-10 text-sm`}
            >
              <Loader2 size={18} className="animate-spin" />
              AIが検索しています...
            </div>
          ) : searchResults.length > 0 ? (
            <div className="grid gap-4">
              {searchResults.map((item) => (
                <ProductCard
                  key={item.product.id}
                  product={item.product}
                  darkMode={darkMode}
                  imageUrl={productImageUrl}
                  combinedScore={item.score}
                  similarity={item.similarity}
                  sources={item.sources}
                />
              ))}
            </div>
          ) : (
            <div
              className={`${surfaceClass(darkMode)} p-10 text-center text-sm ${
                darkMode ? "text-slate-400" : "text-slate-500"
              }`}
            >
              商品が見つかりませんでした
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
