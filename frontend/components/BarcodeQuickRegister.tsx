"use client";

import Link from "next/link";
import { useState } from "react";
import { Loader2, PackagePlus } from "lucide-react";
import { surfaceClass, useTheme } from "@/components/AppShell";
import { FieldAutocompleteInput } from "@/components/FieldAutocompleteInput";
import { saveFieldHistory } from "@/lib/fieldSuggestions";
import {
  buildRegisterUrl,
  registerProduct,
  saveBarcodeRegisterDraft,
  type BarcodeRegisterDraft,
} from "@/lib/barcode";
import { fieldClass, primaryButton } from "@/components/ui";

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

type BarcodeQuickRegisterProps = {
  modelNumber: string;
  scannedCode: string;
  terms?: string[];
  onRegistered: (productId: number) => void;
};

export function BarcodeQuickRegister({
  modelNumber,
  scannedCode,
  terms = [],
  onRegistered,
}: BarcodeQuickRegisterProps) {
  const { darkMode } = useTheme();
  const [maker, setMaker] = useState("");
  const [productName, setProductName] = useState("未登録");
  const [model, setModel] = useState(modelNumber);
  const [category, setCategory] = useState("その他");
  const [memo] = useState("");
  const [tags, setTags] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const inputClass = `${fieldClass(darkMode)} mt-1.5`;

  const labelClass = darkMode
    ? "text-sm font-semibold text-ink-300"
    : "text-sm font-semibold text-ink-600";

  async function handleSubmit() {
    if (!model.trim()) {
      setError("型番を入力してください。");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const data = await registerProduct({
        maker,
        product_name: productName,
        model_number: model.trim(),
        category,
        memo: memo || `QR/バーコード登録: ${scannedCode}`,
        tags,
      });
      saveFieldHistory("maker", maker);
      saveFieldHistory("product_name", productName);
      onRegistered(data.id);
    } catch (submitError) {
      console.error(submitError);
      setError("登録に失敗しました。もう一度お試しください。");
    } finally {
      setLoading(false);
    }
  }

  function openFullRegister() {
    const draft: BarcodeRegisterDraft = {
      modelNumber: model.trim() || modelNumber,
      scannedCode,
      terms,
    };
    saveBarcodeRegisterDraft(draft);
  }

  const fullRegisterHref = buildRegisterUrl({
    modelNumber: model.trim() || modelNumber,
    scannedCode,
    terms,
  });

  return (
    <div className={`${surfaceClass(darkMode)} space-y-5 p-5 md:p-6`}>
      <div>
        <p
          className={
            darkMode
              ? "text-base font-bold text-white"
              : "text-base font-bold text-ink-900"
          }
        >
          未登録の商品です
        </p>
        <p
          className={
            darkMode
              ? "mt-2 text-sm text-ink-400"
              : "mt-2 text-sm text-ink-500"
          }
        >
          読み取ったコードに一致する商品がありません。ここからそのまま登録できます。
        </p>
        <p
          className={
            darkMode
              ? "mt-2 font-mono text-sm text-brand-300"
              : "mt-2 font-mono text-sm text-brand-700"
          }
        >
          {scannedCode}
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <label className={labelClass}>型番 *</label>
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className={inputClass}
          />
        </div>
        <FieldAutocompleteInput
          field="maker"
          label="メーカー"
          value={maker}
          onChange={setMaker}
          placeholder="例：TOTO"
          disabled={loading}
          labelClassName={labelClass}
          inputClassName={inputClass}
        />
        <FieldAutocompleteInput
          field="product_name"
          label="商品名"
          value={productName}
          onChange={setProductName}
          disabled={loading}
          filterMaker={maker}
          labelClassName={labelClass}
          inputClassName={inputClass}
        />
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
          <label className={labelClass}>タグ（任意）</label>
          <input
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="例：水回り"
            className={inputClass}
          />
        </div>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={loading}
          className={`${primaryButton}`}
        >
          {loading ? (
            <Loader2 size={18} className="animate-spin" />
          ) : (
            <PackagePlus size={18} />
          )}
          この内容で登録する
        </button>
        <Link
          href={fullRegisterHref}
          onClick={openFullRegister}
          className={
            darkMode
              ? "inline-flex items-center rounded-xl border border-ink-700 px-5 py-3 text-sm font-semibold text-ink-200 hover:bg-ink-800"
              : "inline-flex items-center rounded-xl border border-ink-200 px-5 py-3 text-sm font-semibold text-ink-700 hover:bg-ink-50"
          }
        >
          詳細を入力して登録
        </Link>
      </div>
    </div>
  );
}
