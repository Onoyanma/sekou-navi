"use client";

import { useEffect, useRef, useState } from "react";
import {
  Camera,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Image as ImageIcon,
  Loader2,
  Package,
  Search,
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
import {
  dangerButton,
  fieldClass,
  chip as chipLabel,
  primaryButton,
  secondaryButton,
  tonalButton,
} from "@/components/ui";

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
      description="登録済みの商品を探します"
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
  const [showModes, setShowModes] = useState(false);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // ホームの「写真で探す」から来たときは、最初から画像のタブを開く
    if (new URLSearchParams(window.location.search).get("tab") === "image") {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSearchTab("image");
    }
  }, []);

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

  const inputClass = `${fieldClass(darkMode)} pl-12 pr-4`;

  const chipClass = darkMode
    ? "min-h-10 rounded-full bg-ink-800 px-4 text-sm text-ink-200 hover:bg-ink-700"
    : "min-h-10 rounded-full bg-white px-4 text-sm text-ink-700 shadow-card hover:bg-brand-50";

  const muted = darkMode ? "text-ink-400" : "text-ink-500";
  const visibleImageResults = isLowConfidence
    ? similarImageResults.slice(0, LOW_CONFIDENCE_RESULT_LIMIT)
    : similarImageResults;
  const tabs = [
    { id: "keyword", label: "キーワード", icon: Search },
    { id: "image", label: "写真", icon: Camera },
  ] as const;
  const modeLabel: Record<TextSearchMode, string> = {
    hybrid: "おまかせ（おすすめ）",
    keyword: "キーワード一致",
    semantic: "意味で探す",
  };

  return (
    <div className="space-y-5">
      <div className="space-y-4">
        <div
          role="tablist"
          className={`flex rounded-2xl p-1 ${darkMode ? "bg-ink-900" : "bg-ink-200/60"}`}
        >
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const active = searchTab === tab.id;

            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setSearchTab(tab.id)}
                className={`flex min-h-11 flex-1 items-center justify-center gap-2 rounded-xl text-[15px] font-semibold transition ${
                  active
                    ? darkMode
                      ? "bg-ink-700 text-white shadow-sm"
                      : "bg-white text-ink-900 shadow-sm"
                    : muted
                }`}
              >
                <Icon size={18} />
                {tab.label}
              </button>
            );
          })}
        </div>

        {searchTab === "keyword" && (
          <div className="space-y-4">
            <div className="relative">
              <Search
                size={20}
                className={`pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 ${
                  darkMode ? "text-ink-500" : "text-ink-400"
                }`}
              />
              <input
                value={keyword}
                type="search"
                enterKeyHint="search"
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
                placeholder="型番・メーカー・商品名"
                className={inputClass}
              />
              {textSearchLoading && (
                <Loader2
                  size={18}
                  className="absolute right-4 top-1/2 -translate-y-1/2 animate-spin text-brand-500"
                />
              )}
            </div>

            <div>
              <button
                type="button"
                onClick={() => setShowModes((value) => !value)}
                aria-expanded={showModes}
                className={`inline-flex min-h-9 items-center gap-1 text-sm ${muted}`}
              >
                探し方：{modeLabel[textSearchMode]}
                <ChevronDown
                  size={16}
                  className={`transition ${showModes ? "rotate-180" : ""}`}
                />
              </button>

              {showModes && (
                <div className="mt-2 space-y-2">
                  <div
                    className={`flex rounded-xl p-1 ${darkMode ? "bg-ink-900" : "bg-ink-200/60"}`}
                  >
                    {(
                      [
                        { id: "hybrid", label: "おまかせ" },
                        { id: "keyword", label: "一致" },
                        { id: "semantic", label: "意味" },
                      ] as const
                    ).map((item) => {
                      const active = textSearchMode === item.id;

                      return (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => setTextSearchMode(item.id)}
                          className={`min-h-10 flex-1 whitespace-nowrap rounded-lg px-3 text-sm font-semibold transition ${
                            active
                              ? darkMode
                                ? "bg-ink-700 text-white"
                                : "bg-white text-ink-900 shadow-sm"
                              : muted
                          }`}
                        >
                          {item.label}
                        </button>
                      );
                    })}
                  </div>
                  <p className={`text-xs leading-relaxed ${muted}`}>
                    {modeHint[textSearchMode]}
                  </p>
                </div>
              )}
            </div>

            {suggestions.length > 0 && (
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
            )}

            {!hasKeywordSearch && (
              <div className="space-y-5 pt-1">
                {searchHistory.length > 0 && (
                  <div>
                    <p
                      className={`mb-2 flex items-center gap-1.5 text-sm font-semibold ${muted}`}
                    >
                      <Clock size={15} />
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

                <button
                  type="button"
                  onClick={() => setSearchTab("image")}
                  className={`${surfaceClass(darkMode)} flex w-full items-center gap-4 p-4 text-left transition active:scale-[0.99]`}
                >
                  <span
                    className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${
                      darkMode ? "bg-brand-950 text-brand-300" : "bg-brand-50 text-brand-600"
                    }`}
                  >
                    <Camera size={22} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[15px] font-bold">
                      型番がわからないときは、写真で探す
                    </span>
                    <span className={`mt-0.5 block text-sm ${muted}`}>
                      型番ラベルを撮ると、登録済みの商品を探します
                    </span>
                  </span>
                  <ChevronRight size={18} className={muted} />
                </button>
              </div>
            )}
          </div>
        )}

        {searchTab === "image" && (
          <div className="space-y-4">
            <details
              open={imageSearchFiles.length === 0}
              className={`group rounded-2xl px-4 py-3 ${
                darkMode ? "bg-ink-900" : "bg-brand-50"
              }`}
            >
              <summary
                className={`flex min-h-8 cursor-pointer list-none items-center justify-between text-sm font-bold ${
                  darkMode ? "text-brand-300" : "text-brand-800"
                }`}
              >
                うまく撮るコツ
                <ChevronDown
                  size={16}
                  className="transition group-open:rotate-180"
                />
              </summary>
              <ul
                className={`mt-2 list-inside list-disc space-y-1.5 text-sm leading-relaxed ${
                  darkMode ? "text-ink-300" : "text-ink-700"
                }`}
              >
                <li>型番ラベルに近づいて、文字が画面いっぱいになるように撮る</li>
                <li>照明の反射や影を避け、ラベルに正面から向ける</li>
                <li>読めないときは、ラベルだけを写した写真を追加する</li>
              </ul>
            </details>

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

            <div className="grid gap-2.5">
              <button
                type="button"
                onClick={() => cameraInputRef.current?.click()}
                disabled={imageSearchLoading}
                className={`${primaryButton} min-h-14 w-full text-base`}
              >
                {imageSearchLoading ? (
                  <Loader2 size={22} className="animate-spin" />
                ) : (
                  <Camera size={22} />
                )}
                {imageSearchFiles.length > 0 ? "写真を追加で撮る" : "写真を撮る"}
              </button>
              <button
                type="button"
                onClick={() => imageInputRef.current?.click()}
                disabled={imageSearchLoading}
                className={`${secondaryButton(darkMode)} w-full`}
              >
                <ImageIcon size={20} />
                アルバムから選ぶ
              </button>
            </div>

            {imageSearchFiles.length > 0 && (
              <div className="space-y-3">
                <div className="flex gap-3 overflow-x-auto pb-1 pt-2">
                  {imageSearchFiles.map((image) => (
                    <div key={image.id} className="relative shrink-0">
                      <img
                        src={image.previewUrl}
                        alt={image.file.name}
                        className="h-20 w-20 rounded-2xl object-cover shadow-card"
                      />
                      <button
                        type="button"
                        onClick={() => removeImageSearchFile(image.id)}
                        disabled={imageSearchLoading}
                        aria-label="この写真を外す"
                        className="absolute -right-2 -top-2 flex h-7 w-7 items-center justify-center rounded-full bg-ink-800 text-white shadow hover:bg-ink-900 disabled:opacity-50"
                      >
                        <X size={15} />
                      </button>
                    </div>
                  ))}
                </div>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className={`flex items-center gap-2 text-sm ${muted}`}>
                    {imageSearchLoading && (
                      <Loader2 size={15} className="animate-spin text-brand-500" />
                    )}
                    {imageSearchLoading
                      ? "解析しています（10秒ほどかかることがあります）"
                      : `${imageSearchFiles.length}枚で検索しました`}
                  </p>
                  {!imageSearchLoading && (
                    <button
                      type="button"
                      onClick={clearImageSearch}
                      className={`min-h-10 px-2 text-sm font-semibold ${
                        darkMode ? "text-red-400" : "text-red-600"
                      }`}
                    >
                      やり直す
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {imageSearchError && (
        <div
          role="alert"
          className={`flex flex-col gap-3 rounded-2xl px-4 py-3.5 text-sm sm:flex-row sm:items-center ${
            darkMode ? "bg-red-950/50 text-red-300" : "bg-red-50 text-red-800"
          }`}
        >
          <span className="flex-1 leading-relaxed">{imageSearchError}</span>
          {imageSearchFiles.length > 0 && (
            <button
              type="button"
              onClick={() => void runImageSearch()}
              className={dangerButton}
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
              className={`flex items-center gap-2 rounded-2xl px-4 py-3.5 text-sm font-semibold ${
                darkMode
                  ? "bg-brand-950 text-brand-300"
                  : "bg-brand-50 text-brand-800"
              }`}
            >
              <CheckCircle2 size={18} className="shrink-0" />
              型番が一致する商品が見つかりました
            </p>
          )}
          {imageSearchInsight.top_confidence === "medium" && (
            <p
              className={`flex items-center gap-2 rounded-2xl px-4 py-3.5 text-sm ${
                darkMode ? "bg-amber-950/50 text-amber-300" : "bg-amber-50 text-amber-900"
              }`}
            >
              <TriangleAlert size={18} className="shrink-0" />
              候補です。実物のラベルの型番と一致するか確認してください
            </p>
          )}
          {isLowConfidence && (
            <div
              role="status"
              className={`space-y-3 rounded-2xl px-4 py-3.5 text-sm ${
                darkMode ? "bg-amber-950/50 text-amber-300" : "bg-amber-50 text-amber-900"
              }`}
            >
              <div className="flex items-start gap-3">
                <TriangleAlert size={18} className="mt-0.5 shrink-0" />
                <span className="leading-relaxed">
                  自信を持って特定できませんでした。下の結果は参考です。型番がわかる場合は、型番を入力して探してください。
                </span>
              </div>
              <button
                type="button"
                onClick={() => switchToKeywordSearch(topOcrCandidate)}
                className={`inline-flex min-h-11 w-full items-center justify-center rounded-xl px-4 text-sm font-semibold transition sm:w-auto ${
                  darkMode
                    ? "bg-amber-900/60 text-amber-100 hover:bg-amber-900"
                    : "bg-white text-amber-900 shadow-card hover:bg-amber-100"
                }`}
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
        <section className="space-y-3">
          {!imageSearchLoading && (
            <h2 className="flex items-center gap-2 text-xl font-bold">
              {isLowConfidence ? "参考の候補" : "見つかった商品"}
              <span className={`text-sm font-medium ${muted}`}>
                {visibleImageResults.length}件
              </span>
            </h2>
          )}

          {imageSearchLoading ? (
            <div className="grid gap-3">
              {Array.from({ length: 2 }).map((_, index) => (
                <div
                  key={index}
                  className={`h-28 animate-pulse rounded-3xl ${
                    darkMode ? "bg-ink-900" : "bg-white/70"
                  }`}
                />
              ))}
            </div>
          ) : visibleImageResults.length > 0 ? (
            <div className="grid gap-3">
              {visibleImageResults.map((item, index) => (
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
            <div
              className={`${surfaceClass(darkMode)} px-6 py-10 text-center text-sm ${muted}`}
            >
              類似する商品が見つかりませんでした
            </div>
          )}

          {imageSearchInsight && !imageSearchLoading && (
            <details className="group pt-2">
              <summary
                className={`flex min-h-10 cursor-pointer list-none items-center gap-1 text-sm font-medium ${muted}`}
              >
                <ChevronRight
                  size={15}
                  className="transition group-open:rotate-90"
                />
                写真から読み取った内容
              </summary>
              <div className="mt-2 flex flex-wrap gap-2">
                {imageSearchInsight.detected_maker && (
                  <span className={chipLabel(darkMode)}>
                    メーカー: {imageSearchInsight.detected_maker}
                  </span>
                )}
                {imageSearchInsight.ocr_candidates
                  .slice(0, 4)
                  .map((candidate) => (
                    <span
                      key={candidate.model_number}
                      className={`${chipLabel(darkMode)} font-mono`}
                    >
                      {candidate.model_number}
                    </span>
                  ))}
                {!imageSearchInsight.detected_maker &&
                  imageSearchInsight.ocr_candidates.length === 0 && (
                    <span className={`text-sm ${muted}`}>
                      文字を読み取れませんでした
                    </span>
                  )}
              </div>
            </details>
          )}
        </section>
      ) : hasKeywordSearch ? (
        <section className="space-y-3">
          <h2 className="flex items-center gap-2 text-xl font-bold">
            検索結果
            <span className={`text-sm font-medium ${muted}`}>
              {textSearchLoading ? "" : `${searchResults.length}件`}
            </span>
          </h2>

          {textSearchLoading ? (
            <div className="grid gap-3">
              {Array.from({ length: 3 }).map((_, index) => (
                <div
                  key={index}
                  className={`h-28 animate-pulse rounded-3xl ${
                    darkMode ? "bg-ink-900" : "bg-white/70"
                  }`}
                />
              ))}
            </div>
          ) : searchResults.length > 0 ? (
            <div className="grid gap-3">
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
              className={`${surfaceClass(darkMode)} px-6 py-10 text-center ${muted}`}
            >
              <Package size={28} className="mx-auto mb-3 opacity-60" />
              <p className="text-sm">「{keyword.trim()}」に合う商品が見つかりませんでした</p>
              <button
                type="button"
                onClick={() => setSearchTab("image")}
                className={`mt-4 ${tonalButton(darkMode)}`}
              >
                <Camera size={18} />
                写真で探してみる
              </button>
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
