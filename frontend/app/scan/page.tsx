"use client";

import { useState } from "react";
import { Barcode, Loader2 } from "lucide-react";
import { AppShell, surfaceClass, useTheme } from "@/components/AppShell";
import { BarcodeQuickRegister } from "@/components/BarcodeQuickRegister";
import { LazyBarcodeScanner } from "@/components/LazyBarcodeScanner";
import { ProductCard } from "@/components/ProductCard";
import { parseScannedCode, searchByBarcode } from "@/lib/barcode";
import { productImageUrl, toProduct, type Product } from "@/lib/products";
import { apiUrl } from "@/lib/api";

type BarcodeSearchResult = {
  score: number;
  match_types: string[];
  matched_term: string;
  product: Product;
};

export default function ScanPage() {
  return (
    <AppShell
      title="スキャン"
      description="QR・バーコードから商品を探します"
    >
      <ScanContent />
    </AppShell>
  );
}

function ScanContent() {
  const { darkMode } = useTheme();
  const [barcodeLoading, setBarcodeLoading] = useState(false);
  const [barcodeResults, setBarcodeResults] = useState<BarcodeSearchResult[]>(
    []
  );
  const [lastScannedCode, setLastScannedCode] = useState("");
  const [barcodePrimary, setBarcodePrimary] = useState("");
  const [barcodeTerms, setBarcodeTerms] = useState<string[]>([]);
  const [registerNotice, setRegisterNotice] = useState("");

  async function handleBarcodeScan(
    code: string,
    options?: { keepNotice?: boolean }
  ) {
    setBarcodeLoading(true);
    setLastScannedCode(code);
    if (!options?.keepNotice) {
      setRegisterNotice("");
    }

    const parsed = parseScannedCode(code);
    setBarcodeTerms(parsed.terms);
    setBarcodePrimary(parsed.primary || code.trim());

    try {
      const data = await searchByBarcode(code);
      setBarcodeResults(
        (data.results || []).map((item) => ({
          score: item.score,
          match_types: item.match_types || [],
          matched_term: item.matched_term || "",
          product: toProduct(item.product),
        }))
      );
      setBarcodeTerms(data.parsed?.terms || parsed.terms);
      setBarcodePrimary(data.parsed?.primary || parsed.primary || code.trim());
    } catch (error) {
      console.error(error);
      setBarcodeResults([]);
    } finally {
      setBarcodeLoading(false);
    }
  }

  async function handleBarcodeRegistered(productId: number) {
    if (lastScannedCode) {
      await handleBarcodeScan(lastScannedCode, { keepNotice: true });
    } else {
      const response = await fetch(
        apiUrl(`/products/${productId}`)
      );
      const product = await response.json();
      setBarcodeResults([
        {
          score: 100,
          match_types: ["model_exact"],
          matched_term: product.model_number,
          product: toProduct(product),
        },
      ]);
    }

    setRegisterNotice("商品を登録しました。登録した商品を表示しています。");
  }

  function clearBarcodeSearch() {
    setBarcodeResults([]);
    setLastScannedCode("");
    setBarcodePrimary("");
    setBarcodeTerms([]);
    setRegisterNotice("");
  }

  const hasScan = lastScannedCode.length > 0;

  return (
    <div className="space-y-6">
      <LazyBarcodeScanner
        onScan={(code) => void handleBarcodeScan(code)}
        disabled={barcodeLoading}
        hint="型番のQR、JANコード、商品ページのURLなどを読み取ります。"
      />

      {hasScan && (
        <div className="flex flex-wrap items-center gap-3">
          <p
            className={
              darkMode ? "text-sm text-ink-400" : "text-sm text-ink-500"
            }
          >
            読み取り: <span className="font-mono">{lastScannedCode}</span>
            {barcodeLoading && "（検索中...）"}
          </p>
          {!barcodeLoading && (
            <button
              type="button"
              onClick={clearBarcodeSearch}
              className={
                darkMode
                  ? "text-sm font-medium text-red-400 hover:text-red-300"
                  : "text-sm font-medium text-red-600 hover:text-red-700"
              }
            >
              クリア
            </button>
          )}
        </div>
      )}

      {barcodeTerms.length > 0 && !barcodeLoading && (
        <div className="flex flex-wrap gap-2">
          {barcodeTerms.map((term) => (
            <span
              key={term}
              className="rounded-full bg-brand-100 px-3 py-1 text-xs font-semibold text-brand-700"
            >
              検索語: {term}
            </span>
          ))}
        </div>
      )}

      {registerNotice && (
        <p
          className={
            darkMode
              ? "rounded-2xl bg-brand-950/50 px-4 py-3 text-sm text-brand-300"
              : "rounded-2xl bg-brand-50 px-4 py-3 text-sm text-brand-800"
          }
        >
          {registerNotice}
        </p>
      )}

      {hasScan && (
        <section className="space-y-4">
          <h2
            className={`flex items-center gap-2 text-lg font-bold ${
              darkMode ? "text-white" : "text-ink-900"
            }`}
          >
            <Barcode size={20} className="text-brand-600" />
            コード一致の商品
            <span
              className={
                darkMode
                  ? "rounded-full bg-ink-800 px-2.5 py-0.5 text-sm font-medium text-ink-300"
                  : "rounded-full bg-ink-100 px-2.5 py-0.5 text-sm font-medium text-ink-600"
              }
            >
              {barcodeResults.length}件
            </span>
          </h2>

          {barcodeLoading ? (
            <div
              className={`${surfaceClass(darkMode)} flex items-center justify-center gap-2 p-10 text-sm`}
            >
              <Loader2 size={18} className="animate-spin" />
              コードを解析しています...
            </div>
          ) : barcodeResults.length > 0 ? (
            <div className="grid gap-4">
              {barcodeResults.map((item, index) => (
                <ProductCard
                  key={`${item.product.id}_${index}`}
                  product={item.product}
                  darkMode={darkMode}
                  imageUrl={productImageUrl}
                  combinedScore={item.score}
                  sources={item.match_types.map((type) =>
                    type === "model_exact"
                      ? "model"
                      : type === "contains"
                        ? "name"
                        : "model"
                  )}
                  ocrCandidate={item.matched_term}
                />
              ))}
            </div>
          ) : (
            <BarcodeQuickRegister
              modelNumber={barcodePrimary || lastScannedCode}
              scannedCode={lastScannedCode}
              terms={barcodeTerms}
              onRegistered={handleBarcodeRegistered}
            />
          )}
        </section>
      )}
    </div>
  );
}
