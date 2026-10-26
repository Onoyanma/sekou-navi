"use client";

import { useEffect, useRef, useState } from "react";
import {
  ClipboardList,
  Image as ImageIcon,
  Images,
  Loader2,
  PackagePlus,
  Sparkles,
  X,
} from "lucide-react";
import { AppShell, surfaceClass, useTheme } from "@/components/AppShell";
import { LazyBarcodeScanner } from "@/components/LazyBarcodeScanner";
import { FieldAutocompleteInput } from "@/components/FieldAutocompleteInput";
import { saveFieldHistory } from "@/lib/fieldSuggestions";
import {
  AUTOCOMPLETE_SOURCE_LABELS,
  fetchProductAutocomplete,
  type ProductAutocompleteSuggestion,
} from "@/lib/productAutocomplete";
import {
  clearBarcodeRegisterDraft,
  loadBarcodeRegisterDraft,
  parseScannedCode,
  searchByBarcode,
} from "@/lib/barcode";
import { apiUrl, productImageUrl } from "@/lib/api";

type OcrCandidate = {
  model_number: string;
  score: number;
};

type MatchedProduct = {
  ocr_candidate: string;
  score: number;
  product: {
    id: number;
    maker: string;
    product_name: string;
    model_number: string;
    category: string;
    image_path: string;
    memo: string;
    tags: string;
  };
};

type SimilarProduct = {
  similarity: number;
  product: {
    id: number;
    maker: string;
    product_name: string;
    model_number: string;
    category: string;
    image_path: string;
    memo: string;
    tags: string;
  };
};

type SelectedImage = {
  id: string;
  file: File;
  previewUrl: string;
  imageType: string;
};

type UnifiedProductCandidate = {
  product: MatchedProduct["product"];
  ocrCandidate?: string;
  matchScore?: number;
  similarity?: number;
  sources: Array<"ocr" | "image">;
};

function mergeProductCandidates(
  matched: MatchedProduct[],
  similar: SimilarProduct[]
): UnifiedProductCandidate[] {
  const map = new Map<number, UnifiedProductCandidate>();

  for (const item of matched) {
    const existing = map.get(item.product.id);

    if (existing) {
      existing.ocrCandidate = item.ocr_candidate;
      existing.matchScore = item.score;

      if (!existing.sources.includes("ocr")) {
        existing.sources.push("ocr");
      }
    } else {
      map.set(item.product.id, {
        product: item.product,
        ocrCandidate: item.ocr_candidate,
        matchScore: item.score,
        sources: ["ocr"],
      });
    }
  }

  for (const item of similar) {
    const existing = map.get(item.product.id);

    if (existing) {
      existing.similarity = Math.max(
        existing.similarity ?? 0,
        item.similarity
      );

      if (!existing.product.image_path && item.product.image_path) {
        existing.product = {
          ...existing.product,
          image_path: item.product.image_path,
        };
      }

      if (!existing.sources.includes("image")) {
        existing.sources.push("image");
      }
    } else {
      map.set(item.product.id, {
        product: item.product,
        similarity: item.similarity,
        sources: ["image"],
      });
    }
  }

  return Array.from(map.values()).sort((a, b) => {
    const rank = (entry: UnifiedProductCandidate) => {
      const hasBoth =
        entry.sources.includes("ocr") && entry.sources.includes("image");
      const matchPart = (entry.matchScore ?? 0) / 100;
      const imagePart = entry.similarity ?? 0;

      return (hasBoth ? 10 : 0) + matchPart + imagePart;
    };

    return rank(b) - rank(a);
  });
}

export default function RegisterPage() {
  return (
    <AppShell
      title="商品登録"
      description="型番・URL・画像・QRから商品情報をAIで自動入力できます"
    >
      <RegisterContent />
    </AppShell>
  );
}

function RegisterContent() {
  const { darkMode } = useTheme();
  const imageInputRef = useRef<HTMLInputElement>(null);

  const inputClass = darkMode
    ? "w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-white outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
    : "w-full rounded-xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20";

  const labelClass = darkMode
    ? "text-sm font-semibold text-slate-300"
    : "text-sm font-semibold text-slate-600";

  const sectionTitleClass = darkMode
    ? "flex items-center gap-2 text-lg font-bold text-white"
    : "flex items-center gap-2 text-lg font-bold text-slate-900";

  const [images, setImages] = useState<SelectedImage[]>([]);
  const [maker, setMaker] = useState("");
  const [productName, setProductName] = useState("未登録");
  const [modelNumber, setModelNumber] = useState("");
  const [category, setCategory] = useState("その他");
  const [tags, setTags] = useState("");
  const [memo, setMemo] = useState("");
  const [officialUrl, setOfficialUrl] = useState("");

  const [autocompleteLoading, setAutocompleteLoading] = useState(false);
  const [autocompletePreviewState, setAutocompletePreview] =
    useState<ProductAutocompleteSuggestion | null>(null);
  // 型番・URL が両方空のときはプレビューを表示しない
  const autocompletePreview =
    modelNumber.trim() || officialUrl.trim() ? autocompletePreviewState : null;

  const [candidates, setCandidates] = useState<OcrCandidate[]>([]);
  const [matchedProducts, setMatchedProducts] = useState<MatchedProduct[]>([]);
  const [similarProducts, setSimilarProducts] = useState<SimilarProduct[]>([]);
  const [texts, setTexts] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const draft = loadBarcodeRegisterDraft();
    const params = new URLSearchParams(window.location.search);
    const modelFromUrl = params.get("model_number") || params.get("model");
    const codeFromUrl = params.get("code");

    const modelNumber = draft?.modelNumber || modelFromUrl || "";
    const scannedCode = draft?.scannedCode || codeFromUrl || "";

    if (!modelNumber && !scannedCode) {
      return;
    }

    if (modelNumber) {
      // 検索画面やスキャン画面から引き継いだ値を初回表示時に一度だけ反映する
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setModelNumber(modelNumber);
    }

    if (scannedCode) {
      setMemo((prev) =>
        prev ? prev : `QR/バーコード: ${scannedCode}`
      );
      void handleBarcodeScan(scannedCode);
    } else if (modelNumber) {
      void matchSelectedModel(modelNumber);
      setMessage(`検索画面から引き継ぎ: 型番 ${modelNumber}`);
    }

    clearBarcodeRegisterDraft();
  }, []);

  function resetAiResults() {
    setCandidates([]);
    setMatchedProducts([]);
    setSimilarProducts([]);
    setTexts([]);
  }

  function addImages(selectedFiles: File[]) {
    if (selectedFiles.length === 0) return;

    const newImages: SelectedImage[] = selectedFiles.map((file) => ({
      id: `${file.name}_${file.lastModified}_${Math.random()}`,
      file,
      previewUrl: URL.createObjectURL(file),
      imageType: "その他",
    }));

    setImages((prev) => [...prev, ...newImages]);
    resetAiResults();
  }

  function removeImage(id: string) {
    const removed = images.find((image) => image.id === id);

    if (removed) {
      URL.revokeObjectURL(removed.previewUrl);
    }

    setImages((prev) => prev.filter((image) => image.id !== id));
    resetAiResults();
  }

  function clearAllImages() {
    for (const image of images) {
      URL.revokeObjectURL(image.previewUrl);
    }

    setImages([]);
    resetAiResults();
  }

  function updateImageType(id: string, imageType: string) {
    setImages((prev) =>
      prev.map((image) =>
        image.id === id ? { ...image, imageType } : image
      )
    );
    resetAiResults();
  }

  async function analyzeImage() {
    if (images.length === 0) {
      setMessage("AI解析するには画像を追加してください。");
      return;
    }

    setLoading(true);
    setMessage("");

    try {
      let allCandidates: OcrCandidate[] = [];
      let allTexts: string[] = [];

      const labelImages = images.filter(
        (image) => image.imageType === "型番ラベル"
      );

      const ocrTargetImages =
        labelImages.length > 0 ? labelImages : images;

      for (const image of ocrTargetImages) {
        const formData = new FormData();
        formData.append("file", image.file);

        const response = await fetch(apiUrl("/ocr"), {
          method: "POST",
          body: formData,
        });

        const data = await response.json();

        allCandidates = [...allCandidates, ...(data.candidates || [])];
        allTexts = [...allTexts, ...(data.texts || [])];
      }

      const ocrCandidates = allCandidates.sort((a, b) => b.score - a.score);

      if (ocrCandidates.length === 0 && labelImages.length > 0) {
        for (const image of images) {
          const formData = new FormData();
          formData.append("file", image.file);

          const response = await fetch(apiUrl("/ocr"), {
            method: "POST",
            body: formData,
          });

          const data = await response.json();

          allCandidates = [...allCandidates, ...(data.candidates || [])];
          allTexts = [...allTexts, ...(data.texts || [])];
        }
      }

      const finalOcrCandidates = allCandidates.sort((a, b) => b.score - a.score);
      const finalOcrTexts = allTexts;

      const filteredCandidates = finalOcrCandidates
        .filter((candidate) => candidate.score >= 85)
        .slice(0, 5);

      setCandidates(filteredCandidates);
      setTexts(finalOcrTexts);

      if (finalOcrCandidates.length > 0) {
        const matchResponse = await fetch(
          apiUrl("/match-products"),
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify(
              finalOcrCandidates.map(
                (candidate: OcrCandidate) => candidate.model_number
              )
            ),
          }
        );

        const matchData = await matchResponse.json();
        setMatchedProducts(matchData.results || []);
      }

      const similarFormData = new FormData();

      for (const image of images) {
        similarFormData.append("files", image.file);
      }

      const similarResponse = await fetch(
        apiUrl("/similar-search"),
        {
          method: "POST",
          body: similarFormData,
        }
      );

      const similarData = await similarResponse.json();
      setSimilarProducts(similarData.results || []);

      if (finalOcrCandidates.length > 0) {
        setModelNumber(finalOcrCandidates[0].model_number);
      }

      if (finalOcrCandidates.length > 0) {
        const bestModel = finalOcrCandidates[0].model_number;

        const suggestResponse = await fetch(
          apiUrl("/suggest-product-name"),
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify(bestModel),
          }
        );

        const suggestData = await suggestResponse.json();

        if (suggestData.suggested_product_name) {
          setProductName(suggestData.suggested_product_name);
        }

        if (suggestData.suggested_category) {
          setCategory(suggestData.suggested_category);
        }

        if (suggestData.suggested_tags) {
          setTags(suggestData.suggested_tags);
        }
      }

      const joinedText = finalOcrTexts.join(" ").toUpperCase();

      if (joinedText.includes("TOTO")) {
        setMaker("TOTO");
        setTags("水回り");
      } else if (joinedText.includes("LIXIL") || joinedText.includes("INAX")) {
        setMaker("LIXIL");
        setTags("水回り");
      } else if (joinedText.includes("PANASONIC")) {
        setMaker("Panasonic");
        setTags("電気");
      }

      const bestModel = finalOcrCandidates[0]?.model_number || "";

      if (bestModel.startsWith("TCF") || bestModel.startsWith("CS")) {
        setCategory("トイレ");
        setProductName("トイレ関連部材");
      } else if (bestModel.startsWith("TKS") || bestModel.startsWith("SF")) {
        setCategory("キッチン");
        setProductName("水栓");
      } else if (bestModel.startsWith("FY") || bestModel.startsWith("VD")) {
        setCategory("換気扇");
        setProductName("換気扇");
      }

      setMessage("AI解析が完了しました。");
    } catch (error) {
      console.error(error);
      setMessage("AI解析に失敗しました。");
    } finally {
      setLoading(false);
    }
  }

  async function handleBarcodeScan(code: string) {
    setLoading(true);
    setMessage("");
    resetAiResults();

    try {
      const data = await searchByBarcode(code);
      const parsed = data.parsed || parseScannedCode(code);
      const primary = parsed.primary || code.trim();

      if (!primary) {
        setMessage("コードを読み取れませんでした。");
        return;
      }

      setModelNumber(primary);
      setMemo((prev) =>
        prev.includes("QR/バーコード")
          ? prev
          : prev
            ? `${prev}\nQR/バーコード: ${code}`
            : `QR/バーコード: ${code}`
      );
      await matchSelectedModel(primary);

      if (data.results.length > 0) {
        const mapped: MatchedProduct[] = data.results.map((item) => ({
          ocr_candidate: item.matched_term || primary,
          score: item.score,
          product: {
            id: item.product.id as number,
            maker: (item.product.maker as string) || "",
            product_name: (item.product.product_name as string) || "",
            model_number: (item.product.model_number as string) || "",
            category: (item.product.category as string) || "",
            image_path: (item.product.image_path as string) || "",
            memo: (item.product.memo as string) || "",
            tags: (item.product.tags as string) || "",
          },
        }));
        setMatchedProducts(mapped);
        setMessage(
          `コード「${primary}」を読み取りました。登録済み商品が ${data.results.length} 件見つかりました。`
        );
      } else {
        setMessage(
          `コード「${primary}」を読み取りました。新規登録の内容を入力してください。`
        );
      }
    } catch (error) {
      console.error(error);
      setMessage("コードの読み取りに失敗しました。");
    } finally {
      setLoading(false);
    }
  }

  function applyAutocompleteSuggestion(
    suggestion: ProductAutocompleteSuggestion
  ) {
    if (suggestion.model_number) {
      setModelNumber(suggestion.model_number);
    }
    if (suggestion.maker) {
      setMaker(suggestion.maker);
    }
    if (suggestion.product_name) {
      setProductName(suggestion.product_name);
    }
    if (suggestion.category) {
      setCategory(suggestion.category);
    }
    if (suggestion.tags) {
      setTags(suggestion.tags);
    }
    if (suggestion.memo) {
      setMemo((prev) => (prev ? prev : suggestion.memo));
    }
    if (suggestion.official_url) {
      setOfficialUrl(suggestion.official_url);
    }

    if (suggestion.model_number) {
      void matchSelectedModel(suggestion.model_number);
    }
  }

  async function runAutocomplete(options?: { silent?: boolean }) {
    const trimmedModel = modelNumber.trim();
    const trimmedUrl = officialUrl.trim();

    if (!trimmedModel && !trimmedUrl) {
      if (!options?.silent) {
        setMessage("型番または商品ページURLを入力してください。");
      }
      return;
    }

    setAutocompleteLoading(true);
    if (!options?.silent) {
      setMessage("");
    }

    try {
      const suggestion = await fetchProductAutocomplete({
        modelNumber: trimmedModel,
        url: trimmedUrl,
      });

      setAutocompletePreview(suggestion);
      applyAutocompleteSuggestion(suggestion);

      if (!options?.silent) {
        const sourceLabels = suggestion.sources
          .map((source) => AUTOCOMPLETE_SOURCE_LABELS[source] || source)
          .join("・");

        const noteText =
          suggestion.notes.length > 0 ? `（${suggestion.notes[0]}）` : "";

        setMessage(
          `AI自動補完を反映しました。信頼度 ${Math.round(suggestion.confidence * 100)}%${sourceLabels ? ` / 根拠: ${sourceLabels}` : ""}${noteText}`
        );
      }
    } catch (error) {
      console.error(error);
      setAutocompletePreview(null);
      if (!options?.silent) {
        setMessage(
          error instanceof Error ? error.message : "AI自動補完に失敗しました。"
        );
      }
    } finally {
      setAutocompleteLoading(false);
    }
  }

  useEffect(() => {
    const trimmedModel = modelNumber.trim();
    const trimmedUrl = officialUrl.trim();

    if (trimmedModel.length < 3 && trimmedUrl.length < 12) {
      return;
    }

    const timer = window.setTimeout(() => {
      void runAutocomplete({ silent: true });
    }, 700);

    return () => window.clearTimeout(timer);
  }, [modelNumber, officialUrl]);

  async function matchSelectedModel(selectedModel: string) {
    const response = await fetch(apiUrl("/match-products"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify([selectedModel]),
    });

    const data = await response.json();
    setMatchedProducts(data.results || []);
  }

  async function registerProduct() {
    if (!modelNumber) {
      setMessage("型番は入力してください。");
      return;
    }

    setLoading(true);
    setMessage("");

    try {
      const productResponse = await fetch(apiUrl("/products"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          maker: maker || "未登録",
          product_name: productName || "未登録",
          model_number: modelNumber,
          category,
          memo,
          tags,
          official_url: officialUrl,
        }),
      });

      const productData = await productResponse.json() as {
        id: number;
        tags?: string;
        auto_tags_added?: string[];
      };
      const productId = productData.id;

      if (images.length > 0 && productId) {
        for (const image of images) {
          const imageFormData = new FormData();
          imageFormData.append("file", image.file);

          await fetch(apiUrl(`/products/${productId}/images`), {
            method: "POST",
            body: imageFormData,
          });
        }
      }

      clearAllImages();
      setMaker("");
      setProductName("未登録");
      setModelNumber("");
      setCategory("その他");
      setTags("");
      setMemo("");
      setOfficialUrl("");
      setAutocompletePreview(null);
      resetAiResults();
      saveFieldHistory("maker", maker);
      saveFieldHistory("product_name", productName);

      const autoTagNote =
        productData.auto_tags_added && productData.auto_tags_added.length > 0
          ? ` AIタグ: ${productData.auto_tags_added.join("、")}`
          : "";

      setMessage(`商品を登録しました。${autoTagNote}`);
    } catch (error) {
      console.error(error);
      setMessage("登録に失敗しました。");
    } finally {
      setLoading(false);
    }
  }

  const addImageButtonClass = darkMode
    ? "flex h-24 w-24 shrink-0 flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed border-slate-700 bg-slate-950 text-slate-400 hover:border-emerald-500 hover:text-emerald-400 disabled:opacity-50"
    : "flex h-24 w-24 shrink-0 flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed border-slate-300 bg-slate-50 text-slate-500 hover:border-emerald-500 hover:text-emerald-600 disabled:opacity-50";

  const resultCardClass = darkMode
    ? "rounded-xl border border-slate-800 bg-slate-950 p-4"
    : "rounded-xl border border-slate-200 bg-slate-50 p-4";

  const unifiedCandidates = mergeProductCandidates(
    matchedProducts,
    similarProducts
  );

  return (
    <div className="space-y-6">
      <LazyBarcodeScanner
        onScan={(code) => void handleBarcodeScan(code)}
        disabled={loading}
        hint="QR・バーコードから型番を読み取り、フォームへ自動入力します。登録済み商品があれば候補として表示します"
      />

      <div className={`${surfaceClass(darkMode)} p-5 md:p-6`}>
        <h2 className={sectionTitleClass}>
          <Images size={20} className="text-emerald-600" />
          商品画像
        </h2>
        <p
          className={
            darkMode
              ? "mt-2 text-sm text-slate-400"
              : "mt-2 text-sm text-slate-500"
          }
        >
          複数枚追加できます。型番ラベルの写真があるとAIの読み取り精度が上がります
        </p>

        <input
          ref={imageInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => {
            addImages(Array.from(e.target.files || []));
            e.target.value = "";
          }}
        />

        <div className="mt-4 flex flex-wrap items-start gap-3">
          <button
            type="button"
            onClick={() => imageInputRef.current?.click()}
            disabled={loading}
            title="画像を追加"
            aria-label="画像を追加"
            className={addImageButtonClass}
          >
            {loading ? (
              <Loader2 size={24} className="animate-spin" />
            ) : (
              <>
                <ImageIcon size={24} />
                <span className="text-xs font-medium">追加</span>
              </>
            )}
          </button>

          {images.map((image) => (
            <div
              key={image.id}
              className={
                darkMode
                  ? "w-28 shrink-0 rounded-2xl border border-slate-800 bg-slate-950 p-2"
                  : "w-28 shrink-0 rounded-2xl border border-slate-200 bg-white p-2 shadow-sm"
              }
            >
              <div className="relative">
                <img
                  src={image.previewUrl}
                  alt={image.file.name}
                  className="h-24 w-full rounded-xl object-cover"
                />
                <button
                  type="button"
                  onClick={() => removeImage(image.id)}
                  disabled={loading}
                  title="この写真を削除"
                  aria-label="この写真を削除"
                  className="absolute -right-2 -top-2 flex h-7 w-7 items-center justify-center rounded-full bg-red-500 text-white shadow hover:bg-red-600 disabled:opacity-50"
                >
                  <X size={16} />
                </button>
              </div>

              <select
                value={image.imageType}
                onChange={(e) => updateImageType(image.id, e.target.value)}
                className={
                  darkMode
                    ? "mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-white"
                    : "mt-2 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
                }
              >
                <option>全体写真</option>
                <option>型番ラベル</option>
                <option>施工例</option>
                <option>その他</option>
              </select>
            </div>
          ))}
        </div>

        {images.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <p
              className={
                darkMode ? "text-sm text-slate-400" : "text-sm text-slate-500"
              }
            >
              {images.length}枚の画像を選択中
            </p>
            {!loading && (
              <button
                type="button"
                onClick={clearAllImages}
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

        <button
          type="button"
          onClick={analyzeImage}
          disabled={loading || images.length === 0}
          className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 font-semibold text-white hover:bg-emerald-700 disabled:bg-slate-400 sm:w-auto"
        >
          <Sparkles size={18} />
          {loading ? "AI解析中..." : "AIで読み取る"}
        </button>
      </div>

      {(candidates.length > 0 ||
        unifiedCandidates.length > 0 ||
        texts.length > 0) && (
        <div className={`${surfaceClass(darkMode)} p-5 md:p-6`}>
          <h2 className={sectionTitleClass}>
            <Sparkles size={20} className="text-violet-600" />
            AI解析結果
          </h2>

          <div className="mt-4 space-y-4">
            {candidates.length > 0 && (
              <div className={resultCardClass}>
                <p className={labelClass}>型番候補</p>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {candidates.map((candidate, index) => (
                    <button
                      key={`${candidate.model_number}_${index}`}
                      type="button"
                      onClick={() => {
                        setModelNumber(candidate.model_number);
                        matchSelectedModel(candidate.model_number);
                      }}
                      className={
                        darkMode
                          ? "rounded-xl border border-slate-700 bg-slate-900 p-3 text-left hover:border-blue-500"
                          : "rounded-xl border border-slate-200 bg-white p-3 text-left hover:border-blue-400 hover:bg-blue-50"
                      }
                    >
                      <span className="font-bold">{candidate.model_number}</span>
                      <span
                        className={
                          darkMode
                            ? "ml-2 text-sm text-slate-400"
                            : "ml-2 text-sm text-slate-500"
                        }
                      >
                        スコア {candidate.score}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className={resultCardClass}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className={labelClass}>登録済み商品候補</p>
                {unifiedCandidates.length > 0 && (
                  <span
                    className={
                      darkMode
                        ? "rounded-full bg-slate-800 px-2.5 py-0.5 text-xs font-medium text-slate-300"
                        : "rounded-full bg-slate-200 px-2.5 py-0.5 text-xs font-medium text-slate-600"
                    }
                  >
                    {unifiedCandidates.length}件
                  </span>
                )}
              </div>
              <p
                className={
                  darkMode
                    ? "mt-1 text-xs text-slate-500"
                    : "mt-1 text-xs text-slate-500"
                }
              >
                型番一致と画像類似の結果をまとめて表示しています
              </p>

              {unifiedCandidates.length > 0 ? (
                <div className="mt-3 grid gap-3">
                  {unifiedCandidates.map((item) => (
                    <div
                      key={item.product.id}
                      className={
                        darkMode
                          ? "flex gap-4 rounded-xl border border-slate-800 bg-slate-900 p-4"
                          : "flex gap-4 rounded-xl border border-slate-200 bg-white p-4"
                      }
                    >
                      {item.product.image_path && (
                        <img
                          src={productImageUrl(
                            item.product.image_path.split(",")[0]
                          )}
                          alt={item.product.product_name}
                          className="h-20 w-20 shrink-0 rounded-xl object-cover"
                        />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap gap-2">
                          {item.sources.includes("ocr") &&
                          item.sources.includes("image") ? (
                            <span className="rounded-full bg-violet-100 px-2.5 py-0.5 text-xs font-semibold text-violet-700">
                              型番・画像ともに一致
                            </span>
                          ) : (
                            <>
                              {item.sources.includes("ocr") && (
                                <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-semibold text-blue-700">
                                  型番一致
                                </span>
                              )}
                              {item.sources.includes("image") && (
                                <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
                                  画像類似
                                </span>
                              )}
                            </>
                          )}
                        </div>

                        {item.ocrCandidate && (
                          <p className="mt-2 text-xs text-blue-600">
                            OCR候補: {item.ocrCandidate}
                          </p>
                        )}

                        <h3 className="mt-1 font-bold">
                          {item.product.product_name}
                        </h3>
                        <p className="text-sm">{item.product.model_number}</p>
                        <p
                          className={
                            darkMode
                              ? "text-xs text-slate-400"
                              : "text-xs text-slate-500"
                          }
                        >
                          {item.product.maker} / {item.product.category}
                        </p>

                        <div
                          className={
                            darkMode
                              ? "mt-2 flex flex-wrap gap-3 text-sm text-slate-300"
                              : "mt-2 flex flex-wrap gap-3 text-sm text-slate-600"
                          }
                        >
                          {item.matchScore !== undefined && (
                            <span className="font-semibold text-blue-600">
                              型番スコア {item.matchScore.toFixed(1)}
                            </span>
                          )}
                          {item.similarity !== undefined && (
                            <span className="font-semibold text-emerald-600">
                              画像類似度 {item.similarity.toFixed(2)}
                            </span>
                          )}
                        </div>

                        <button
                          type="button"
                          onClick={() => {
                            setModelNumber(item.product.model_number);
                            setMaker(item.product.maker);
                            setProductName(item.product.product_name);
                            setCategory(item.product.category);
                            setTags(item.product.tags);
                            setMemo(item.product.memo);
                          }}
                          className={
                            darkMode
                              ? "mt-3 text-sm font-medium text-blue-400 hover:text-blue-300"
                              : "mt-3 text-sm font-medium text-blue-600 hover:text-blue-700"
                          }
                        >
                          この商品情報をフォームに反映
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p
                  className={
                    darkMode
                      ? "mt-3 text-sm text-slate-400"
                      : "mt-3 text-sm text-slate-500"
                  }
                >
                  一致する登録済み商品はありません
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      <div className={`${surfaceClass(darkMode)} p-5 md:p-6`}>
        <h2 className={sectionTitleClass}>
          <ClipboardList size={20} className="text-blue-600" />
          商品情報
        </h2>

        <div
          className={
            darkMode
              ? "mt-5 rounded-xl border border-violet-900/60 bg-slate-950 p-4"
              : "mt-5 rounded-xl border border-violet-200 bg-violet-50/50 p-4"
          }
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p
                className={
                  darkMode
                    ? "flex items-center gap-2 text-sm font-semibold text-violet-300"
                    : "flex items-center gap-2 text-sm font-semibold text-violet-800"
                }
              >
                <Sparkles size={16} />
                AI自動補完
              </p>
              <p
                className={
                  darkMode
                    ? "mt-1 text-xs text-slate-400"
                    : "mt-1 text-xs text-slate-600"
                }
              >
                型番またはメーカー公式ページのURLを入力すると、商品名・メーカー・カテゴリなどを推測します
              </p>
            </div>
            <button
              type="button"
              onClick={() => void runAutocomplete()}
              disabled={loading || autocompleteLoading}
              className="inline-flex items-center gap-2 rounded-xl bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-700 disabled:bg-slate-400"
            >
              {autocompleteLoading ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Sparkles size={16} />
              )}
              {autocompleteLoading ? "補完中..." : "AIで自動補完"}
            </button>
          </div>

          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div>
              <label className={labelClass}>
                型番 <span className="text-red-500">*</span>
              </label>
              <input
                value={modelNumber}
                onChange={(e) => setModelNumber(e.target.value)}
                placeholder="例：TCF583HAR#NW1"
                disabled={loading || autocompleteLoading}
                className={`${inputClass} mt-1.5`}
              />
            </div>

            <div>
              <label className={labelClass}>商品ページURL</label>
              <input
                value={officialUrl}
                onChange={(e) => setOfficialUrl(e.target.value)}
                placeholder="https://www.toto.co.jp/..."
                disabled={loading || autocompleteLoading}
                className={`${inputClass} mt-1.5`}
              />
            </div>
          </div>

          {autocompletePreview && (
            <div
              className={
                darkMode
                  ? "mt-4 rounded-xl border border-slate-800 bg-slate-900 p-4 text-sm"
                  : "mt-4 rounded-xl border border-slate-200 bg-white p-4 text-sm"
              }
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={
                    darkMode
                      ? "font-semibold text-white"
                      : "font-semibold text-slate-900"
                  }
                >
                  補完プレビュー
                </span>
                <span className="rounded-full bg-violet-100 px-2.5 py-0.5 text-xs font-semibold text-violet-700">
                  信頼度 {Math.round(autocompletePreview.confidence * 100)}%
                </span>
                {autocompletePreview.sources.map((source) => (
                  <span
                    key={source}
                    className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-600"
                  >
                    {AUTOCOMPLETE_SOURCE_LABELS[source] || source}
                  </span>
                ))}
              </div>

              <dl className="mt-3 grid gap-2 sm:grid-cols-2">
                <div>
                  <dt className="text-xs text-slate-500">メーカー</dt>
                  <dd>{autocompletePreview.maker || "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">商品名</dt>
                  <dd>{autocompletePreview.product_name || "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">型番</dt>
                  <dd className="font-mono">
                    {autocompletePreview.model_number || "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">カテゴリ</dt>
                  <dd>{autocompletePreview.category || "—"}</dd>
                </div>
              </dl>

              {autocompletePreview.model_candidates.length > 1 && (
                <div className="mt-3">
                  <p className="text-xs text-slate-500">型番候補</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {autocompletePreview.model_candidates
                      .slice(0, 5)
                      .map((candidate) => (
                        <button
                          key={candidate.model_number}
                          type="button"
                          onClick={() => {
                            setModelNumber(candidate.model_number);
                            void runAutocomplete();
                          }}
                          className={
                            darkMode
                              ? "rounded-lg border border-slate-700 px-2.5 py-1 text-xs hover:border-violet-500"
                              : "rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs hover:border-violet-400"
                          }
                        >
                          {candidate.model_number}
                        </button>
                      ))}
                  </div>
                </div>
              )}

              {autocompletePreview.matched_product && (
                <p className="mt-3 text-xs text-blue-600">
                  登録済みの類似商品:{" "}
                  {autocompletePreview.matched_product.product_name}（
                  {autocompletePreview.matched_product.model_number}）
                </p>
              )}

              {autocompletePreview.notes.length > 0 && (
                <p className="mt-2 text-xs text-amber-600">
                  {autocompletePreview.notes.join(" ")}
                </p>
              )}
            </div>
          )}
        </div>

        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <FieldAutocompleteInput
            field="maker"
            label="メーカー"
            value={maker}
            onChange={setMaker}
            placeholder="例：TOTO"
            disabled={loading}
            labelClassName={labelClass}
            inputClassName={`${inputClass} mt-1.5`}
          />

          <FieldAutocompleteInput
            field="product_name"
            label="商品名"
            value={productName}
            onChange={setProductName}
            placeholder="商品名"
            disabled={loading}
            filterMaker={maker}
            labelClassName={labelClass}
            inputClassName={`${inputClass} mt-1.5`}
          />

          <div>
            <label className={labelClass}>カテゴリ</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className={`${inputClass} mt-1.5`}
            >
              <option>キッチン</option>
              <option>トイレ</option>
              <option>洗面台</option>
              <option>浴室</option>
              <option>建具</option>
              <option>床材</option>
              <option>壁材</option>
              <option>サッシ</option>
              <option>電気設備</option>
              <option>換気扇</option>
              <option>給排水部材</option>
              <option>工具</option>
              <option>その他</option>
            </select>
          </div>

          <div className="md:col-span-2">
            <label className={labelClass}>タグ</label>
            <input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="例：水回り, よく使う（空でも登録時にAIが自動付与）"
              className={`${inputClass} mt-1.5`}
            />
            <p
              className={
                darkMode
                  ? "mt-1.5 text-xs text-slate-500"
                  : "mt-1.5 text-xs text-slate-500"
              }
            >
              登録・更新時に、カテゴリ・メーカー・型番・商品名などからAIがタグを自動追加します
            </p>
          </div>

          <div className="md:col-span-2">
            <label className={labelClass}>メモ</label>
            <textarea
              value={memo}
              onChange={(e) => setMemo(e.target.value)}
              placeholder="現場メモや補足情報"
              rows={4}
              className={`${inputClass} mt-1.5`}
            />
          </div>
        </div>

        <button
          type="button"
          onClick={registerProduct}
          disabled={loading}
          className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-3.5 font-semibold text-white hover:bg-blue-700 disabled:bg-slate-400 sm:w-auto"
        >
          <PackagePlus size={18} />
          登録する
        </button>

        {message && (
          <p
            className={
              darkMode
                ? "mt-4 rounded-xl border border-slate-700 bg-slate-800 p-4 text-sm text-slate-200"
                : "mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700"
            }
          >
            {message}
          </p>
        )}
      </div>
    </div>
  );
}
