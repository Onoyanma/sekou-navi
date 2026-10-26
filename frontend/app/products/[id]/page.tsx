"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ClipboardList,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  Images,
  Loader2,
  Pencil,
  Save,
  Trash2,
  X,
} from "lucide-react";
import { AppShell, surfaceClass, useTheme } from "@/components/AppShell";
import { FieldAutocompleteInput } from "@/components/FieldAutocompleteInput";
import { saveFieldHistory } from "@/lib/fieldSuggestions";

type Product = {
  id: number;
  maker: string;
  product_name: string;
  model_number: string;
  category: string;
  image_path: string;
  manual_url: string;
  install_url: string;
  official_url: string;
  memo: string;
  tags: string;
  created_at: string;
};

type ProductImage = {
  id: number;
  product_id: number;
  image_path: string;
  image_type: string;
  created_at: string;
};

type PendingImage = {
  id: string;
  file: File;
  previewUrl: string;
};

const CATEGORIES = [
  "キッチン",
  "トイレ",
  "洗面台",
  "浴室",
  "建具",
  "床材",
  "壁材",
  "サッシ",
  "電気設備",
  "換気扇",
  "給排水部材",
  "工具",
  "その他",
];

function productImageUrl(imagePath: string): string {
  const normalized = imagePath.startsWith("/")
    ? imagePath.slice(1)
    : imagePath;

  return `http://127.0.0.1:8000/${encodeURI(normalized)}`;
}

export default function ProductDetailPage() {
  return (
    <AppShell
      title="商品詳細"
      description="商品情報の確認・編集ができます"
    >
      <ProductDetailContent />
    </AppShell>
  );
}

function ProductDetailContent() {
  const { darkMode } = useTheme();
  const router = useRouter();
  const params = useParams();
  const productId = Number(params.id);
  const imageInputRef = useRef<HTMLInputElement>(null);

  const [product, setProduct] = useState<Product | null>(null);
  const [images, setImages] = useState<ProductImage[]>([]);
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [message, setMessage] = useState("");

  const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);
  const [deletedImageIds, setDeletedImageIds] = useState<number[]>([]);

  const [maker, setMaker] = useState("");
  const [productName, setProductName] = useState("");
  const [modelNumber, setModelNumber] = useState("");
  const [category, setCategory] = useState("その他");
  const [tags, setTags] = useState("");
  const [memo, setMemo] = useState("");
  const [manualUrl, setManualUrl] = useState("");
  const [installUrl, setInstallUrl] = useState("");
  const [officialUrl, setOfficialUrl] = useState("");

  const inputClass = darkMode
    ? "mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-white outline-none focus:border-blue-500"
    : "mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 outline-none focus:border-blue-500";

  const labelClass = darkMode
    ? "text-sm font-semibold text-slate-300"
    : "text-sm font-semibold text-slate-600";

  const sectionTitleClass = darkMode
    ? "flex items-center gap-2 text-lg font-bold text-white"
    : "flex items-center gap-2 text-lg font-bold text-slate-900";

  const dividerClass = darkMode
    ? "border-t border-slate-800"
    : "border-t border-slate-200";

  const loadProduct = useCallback(async () => {
    const response = await fetch(
      `http://127.0.0.1:8000/products/${productId}`
    );
    const data = await response.json();
    setProduct(data);
    setMaker(data.maker || "");
    setProductName(data.product_name || "");
    setModelNumber(data.model_number || "");
    setCategory(data.category || "その他");
    setTags(data.tags || "");
    setMemo(data.memo || "");
    setManualUrl(data.manual_url || "");
    setInstallUrl(data.install_url || "");
    setOfficialUrl(data.official_url || "");
  }, [productId]);

  const loadImages = useCallback(async () => {
    const response = await fetch(
      `http://127.0.0.1:8000/products/${productId}/images`
    );

    if (!response.ok) {
      return;
    }

    const data = await response.json();
    setImages(data);
  }, [productId]);

  useEffect(() => {
    async function init() {
      setLoading(true);

      try {
        await Promise.all([loadProduct(), loadImages()]);
      } finally {
        setLoading(false);
      }
    }

    if (productId) {
      init();
    }
  }, [productId, loadProduct, loadImages]);

  const legacyImages: ProductImage[] =
    product?.image_path && images.length === 0
      ? product.image_path.split(",").map((path, index) => ({
          id: -index - 1,
          product_id: productId,
          image_path: path.trim(),
          image_type: "その他",
          created_at: "",
        }))
      : [];

  const displayImages = images.length > 0 ? images : legacyImages;
  const visibleImages = displayImages.filter(
    (image) => !deletedImageIds.includes(image.id)
  );

  function revokePendingPreviews(items: PendingImage[]) {
    for (const image of items) {
      URL.revokeObjectURL(image.previewUrl);
    }
  }

  function resetImageEdits() {
    revokePendingPreviews(pendingImages);
    setPendingImages([]);
    setDeletedImageIds([]);
    if (imageInputRef.current) {
      imageInputRef.current.value = "";
    }
  }

  function addPendingImages(files: FileList | File[]) {
    const fileList = Array.from(files);
    if (fileList.length === 0) return;

    const newImages: PendingImage[] = fileList.map((file) => ({
      id: `${file.name}_${file.lastModified}_${Math.random()}`,
      file,
      previewUrl: URL.createObjectURL(file),
    }));

    setPendingImages((prev) => [...prev, ...newImages]);
  }

  function removePendingImage(id: string) {
    const removed = pendingImages.find((image) => image.id === id);
    if (removed) {
      URL.revokeObjectURL(removed.previewUrl);
    }
    setPendingImages((prev) => prev.filter((image) => image.id !== id));
  }

  function markImageForDeletion(imageId: number) {
    if (imageId < 0) {
      setMessage("この画像は個別削除できません。新しい画像を追加してください。");
      return;
    }
    setDeletedImageIds((prev) =>
      prev.includes(imageId) ? prev : [...prev, imageId]
    );
  }

  async function saveProduct() {
    if (!modelNumber.trim()) {
      setMessage("型番を入力してください。");
      return;
    }

    setSaving(true);
    setMessage("");

    try {
      const response = await fetch(
        `http://127.0.0.1:8000/products/${productId}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            maker: maker || "未登録",
            product_name: productName || "未登録",
            model_number: modelNumber,
            category,
            memo,
            tags,
            manual_url: manualUrl,
            install_url: installUrl,
            official_url: officialUrl,
          }),
        }
      );

      if (!response.ok) {
        setMessage("保存に失敗しました。");
        return;
      }

      for (const imageId of deletedImageIds) {
        await fetch(
          `http://127.0.0.1:8000/products/${productId}/images/${imageId}`,
          { method: "DELETE" }
        );
      }

      for (const image of pendingImages) {
        const formData = new FormData();
        formData.append("file", image.file);

        await fetch(`http://127.0.0.1:8000/products/${productId}/images`, {
          method: "POST",
          body: formData,
        });
      }

      resetImageEdits();
      await Promise.all([loadProduct(), loadImages()]);
      saveFieldHistory("maker", maker);
      saveFieldHistory("product_name", productName);
      setIsEditing(false);
      setMessage("商品情報を保存しました。");
    } catch (error) {
      console.error(error);
      setMessage("保存に失敗しました。");
    } finally {
      setSaving(false);
    }
  }

  function cancelEdit() {
    if (!product) return;

    setMaker(product.maker || "");
    setProductName(product.product_name || "");
    setModelNumber(product.model_number || "");
    setCategory(product.category || "その他");
    setTags(product.tags || "");
    setMemo(product.memo || "");
    setManualUrl(product.manual_url || "");
    setInstallUrl(product.install_url || "");
    setOfficialUrl(product.official_url || "");
    resetImageEdits();
    setIsEditing(false);
    setMessage("");
  }

  function startEditing() {
    resetImageEdits();
    setIsEditing(true);
    setMessage("");
  }

  async function deleteProduct() {
    if (!product) return;

    const confirmed = confirm(
      `「${product.product_name}」（${product.model_number}）を削除しますか？\nこの操作は取り消せません。`
    );

    if (!confirmed) return;

    setDeleting(true);
    setMessage("");

    try {
      const response = await fetch(
        `http://127.0.0.1:8000/products/${productId}`,
        { method: "DELETE" }
      );

      if (!response.ok) {
        setMessage("商品の削除に失敗しました。");
        return;
      }

      router.push("/");
    } catch (error) {
      console.error(error);
      setMessage("商品の削除に失敗しました。");
    } finally {
      setDeleting(false);
    }
  }

  const addImageButtonClass = darkMode
    ? "flex h-28 w-28 shrink-0 flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed border-slate-700 bg-slate-950 text-slate-400 hover:border-emerald-500 hover:text-emerald-400 disabled:opacity-50"
    : "flex h-28 w-28 shrink-0 flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed border-slate-300 bg-slate-50 text-slate-500 hover:border-emerald-500 hover:text-emerald-600 disabled:opacity-50";

  const imageThumbClass = darkMode
    ? "w-28 shrink-0 rounded-2xl border border-slate-800 bg-slate-950 p-2"
    : "w-28 shrink-0 rounded-2xl border border-slate-200 bg-white p-2 shadow-sm";

  if (loading || !product) {
    return (
      <div
        className={`${surfaceClass(darkMode)} flex items-center justify-center gap-2 p-12 text-sm`}
      >
        <Loader2 size={18} className="animate-spin" />
        読み込み中...
      </div>
    );
  }

  const hasAnyImages = visibleImages.length > 0 || pendingImages.length > 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {!isEditing ? (
            <button
              type="button"
              onClick={startEditing}
              className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700"
            >
              <Pencil size={16} />
              編集する
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={saveProduct}
                disabled={saving}
                className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {saving ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Save size={16} />
                )}
                保存する
              </button>
              <button
                type="button"
                onClick={cancelEdit}
                disabled={saving}
                className={
                  darkMode
                    ? "inline-flex items-center gap-2 rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 hover:bg-slate-800"
                    : "inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                }
              >
                <X size={16} />
                キャンセル
              </button>
            </>
          )}
        </div>
      </div>

      {message && (
        <p
          className={
            darkMode
              ? "rounded-xl border border-slate-700 bg-slate-800 px-4 py-3 text-sm text-slate-200"
              : "rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700"
          }
        >
          {message}
        </p>
      )}

      <div className={`${surfaceClass(darkMode)} p-5 md:p-8`}>
        {!isEditing ? (
          <div className="grid gap-8 lg:grid-cols-[minmax(0,300px)_1fr]">
            <section>
              <h2 className={sectionTitleClass}>
                <Images size={20} className="text-emerald-600" />
                商品画像
              </h2>

              {displayImages.length > 0 ? (
                <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {displayImages.map((image) => (
                    <div key={image.id} className="overflow-hidden">
                      <img
                        src={productImageUrl(image.image_path)}
                        alt={product.product_name}
                        className="aspect-square w-full rounded-2xl border object-cover shadow-sm"
                      />
                      {image.image_type && image.image_type !== "その他" && (
                        <p
                          className={
                            darkMode
                              ? "mt-1.5 truncate text-center text-xs text-slate-500"
                              : "mt-1.5 truncate text-center text-xs text-slate-500"
                          }
                        >
                          {image.image_type}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div
                  className={
                    darkMode
                      ? "mt-4 flex aspect-square max-w-[300px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-700 bg-slate-950 text-slate-500"
                      : "mt-4 flex aspect-square max-w-[300px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-slate-50 text-slate-400"
                  }
                >
                  <ImageIcon size={32} className="opacity-50" />
                  <p className="mt-2 text-sm">画像が登録されていません</p>
                </div>
              )}
            </section>

            <section>
              <div className="flex flex-wrap gap-2">
                <span
                  className={
                    darkMode
                      ? "rounded-full bg-slate-800 px-3 py-1 text-sm text-slate-200"
                      : "rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700"
                  }
                >
                  {product.maker}
                </span>
                <span className="rounded-full bg-blue-100 px-3 py-1 text-sm font-medium text-blue-700">
                  {product.category}
                </span>
              </div>

              <h2
                className={
                  darkMode
                    ? "mt-4 text-2xl font-bold text-white md:text-3xl"
                    : "mt-4 text-2xl font-bold text-slate-900 md:text-3xl"
                }
              >
                {product.product_name}
              </h2>

              <p
                className={
                  darkMode
                    ? "mt-2 font-mono text-lg text-slate-300"
                    : "mt-2 font-mono text-lg text-slate-600"
                }
              >
                {product.model_number}
              </p>

              {product.memo && (
                <p
                  className={
                    darkMode
                      ? "mt-6 rounded-xl bg-slate-800 p-4 text-slate-300"
                      : "mt-6 rounded-xl bg-slate-50 p-4 text-slate-700"
                  }
                >
                  {product.memo}
                </p>
              )}

              {product.tags && (
                <p
                  className={
                    darkMode
                      ? "mt-4 text-sm text-slate-400"
                      : "mt-4 text-sm text-slate-500"
                  }
                >
                  {product.tags}
                </p>
              )}

              <div className="mt-8 flex flex-wrap gap-3">
                {product.manual_url && (
                  <a
                    href={product.manual_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-700"
                  >
                    <FileText size={16} />
                    取扱説明書
                  </a>
                )}

                {product.install_url && (
                  <a
                    href={product.install_url}
                    target="_blank"
                    rel="noreferrer"
                    className={
                      darkMode
                        ? "inline-flex items-center gap-2 rounded-xl border border-slate-700 px-5 py-3 text-sm font-semibold text-slate-200 hover:bg-slate-800"
                        : "inline-flex items-center gap-2 rounded-xl border border-slate-200 px-5 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                    }
                  >
                    <ExternalLink size={16} />
                    施工説明書
                  </a>
                )}

                {product.official_url && (
                  <a
                    href={product.official_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-semibold text-white hover:bg-emerald-700"
                  >
                    <ExternalLink size={16} />
                    公式ページ
                  </a>
                )}
              </div>
            </section>
          </div>
        ) : (
          <div className="space-y-8">
            <section>
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
                写真を追加・削除できます。変更は「保存する」で反映されます
              </p>

              <input
                ref={imageInputRef}
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={(e) => {
                  if (e.target.files) {
                    addPendingImages(e.target.files);
                  }
                  e.target.value = "";
                }}
              />

              <div className="mt-4 flex flex-wrap items-start gap-3">
                <button
                  type="button"
                  onClick={() => imageInputRef.current?.click()}
                  disabled={saving}
                  title="画像を追加"
                  aria-label="画像を追加"
                  className={addImageButtonClass}
                >
                  <ImageIcon size={24} />
                  <span className="text-xs font-medium">追加</span>
                </button>

                {visibleImages.map((image) => (
                  <div key={image.id} className={imageThumbClass}>
                    <div className="relative">
                      <img
                        src={productImageUrl(image.image_path)}
                        alt={product.product_name}
                        className="h-28 w-full rounded-xl object-cover"
                      />
                      {image.id > 0 && (
                        <button
                          type="button"
                          onClick={() => markImageForDeletion(image.id)}
                          disabled={saving}
                          title="画像を削除"
                          aria-label="画像を削除"
                          className="absolute -right-2 -top-2 flex h-7 w-7 items-center justify-center rounded-full bg-red-500 text-white shadow hover:bg-red-600 disabled:opacity-50"
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                    {image.image_type && image.image_type !== "その他" && (
                      <p className="mt-2 truncate text-center text-xs text-slate-500">
                        {image.image_type}
                      </p>
                    )}
                  </div>
                ))}

                {pendingImages.map((image) => (
                  <div key={image.id} className={imageThumbClass}>
                    <div className="relative">
                      <img
                        src={image.previewUrl}
                        alt={image.file.name}
                        className="h-28 w-full rounded-xl object-cover"
                      />
                      <span className="absolute bottom-1 left-1 rounded-md bg-emerald-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                        新規
                      </span>
                      <button
                        type="button"
                        onClick={() => removePendingImage(image.id)}
                        disabled={saving}
                        title="追加を取り消す"
                        aria-label="追加を取り消す"
                        className="absolute -right-2 -top-2 flex h-7 w-7 items-center justify-center rounded-full bg-red-500 text-white shadow hover:bg-red-600 disabled:opacity-50"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {!hasAnyImages && (
                <p
                  className={
                    darkMode
                      ? "mt-3 text-sm text-slate-400"
                      : "mt-3 text-sm text-slate-500"
                  }
                >
                  「追加」から写真を選んでください
                </p>
              )}

              {(pendingImages.length > 0 || deletedImageIds.length > 0) && (
                <p
                  className={
                    darkMode
                      ? "mt-3 text-sm text-emerald-400"
                      : "mt-3 text-sm text-emerald-600"
                  }
                >
                  {pendingImages.length > 0 &&
                    `追加予定 ${pendingImages.length}枚`}
                  {pendingImages.length > 0 && deletedImageIds.length > 0 && " / "}
                  {deletedImageIds.length > 0 &&
                    `削除予定 ${deletedImageIds.length}枚`}
                </p>
              )}
            </section>

            <div className={dividerClass} />

            <section>
              <h2 className={sectionTitleClass}>
                <ClipboardList size={20} className="text-blue-600" />
                商品情報
              </h2>

              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <FieldAutocompleteInput
                  field="maker"
                  label="メーカー"
                  value={maker}
                  onChange={setMaker}
                  disabled={saving}
                  labelClassName={labelClass}
                  inputClassName={inputClass}
                />

                <FieldAutocompleteInput
                  field="product_name"
                  label="商品名"
                  value={productName}
                  onChange={setProductName}
                  disabled={saving}
                  filterMaker={maker}
                  labelClassName={labelClass}
                  inputClassName={inputClass}
                />

                <div>
                  <label className={labelClass}>
                    型番 <span className="text-red-500">*</span>
                  </label>
                  <input
                    value={modelNumber}
                    onChange={(e) => setModelNumber(e.target.value)}
                    className={inputClass}
                  />
                </div>

                <div>
                  <label className={labelClass}>カテゴリ</label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className={inputClass}
                  >
                    {CATEGORIES.map((item) => (
                      <option key={item}>{item}</option>
                    ))}
                  </select>
                </div>

                <div className="md:col-span-2">
                  <label className={labelClass}>タグ</label>
                  <input
                    value={tags}
                    onChange={(e) => setTags(e.target.value)}
                    className={inputClass}
                  />
                </div>

                <div className="md:col-span-2">
                  <label className={labelClass}>メモ</label>
                  <textarea
                    value={memo}
                    onChange={(e) => setMemo(e.target.value)}
                    rows={4}
                    className={inputClass}
                  />
                </div>

                <div className="md:col-span-2">
                  <label className={labelClass}>取扱説明書URL</label>
                  <input
                    value={manualUrl}
                    onChange={(e) => setManualUrl(e.target.value)}
                    placeholder="https://"
                    className={inputClass}
                  />
                </div>

                <div className="md:col-span-2">
                  <label className={labelClass}>施工説明書URL</label>
                  <input
                    value={installUrl}
                    onChange={(e) => setInstallUrl(e.target.value)}
                    placeholder="https://"
                    className={inputClass}
                  />
                </div>

                <div className="md:col-span-2">
                  <label className={labelClass}>公式ページURL</label>
                  <input
                    value={officialUrl}
                    onChange={(e) => setOfficialUrl(e.target.value)}
                    placeholder="https://"
                    className={inputClass}
                  />
                </div>
              </div>
            </section>

            <div className={dividerClass} />

            <section>
              <h2
                className={
                  darkMode
                    ? "text-base font-bold text-red-400"
                    : "text-base font-bold text-red-600"
                }
              >
                登録削除
              </h2>
              <p
                className={
                  darkMode
                    ? "mt-2 text-sm text-slate-400"
                    : "mt-2 text-sm text-slate-500"
                }
              >
                商品と登録画像をすべて削除します
              </p>
              <button
                type="button"
                onClick={deleteProduct}
                disabled={saving || deleting}
                className="mt-4 inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
              >
                {deleting ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Trash2 size={16} />
                )}
                この商品を削除する
              </button>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
