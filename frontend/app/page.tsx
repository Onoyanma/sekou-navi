"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Camera, ChevronRight, PackagePlus, ScanLine, Search } from "lucide-react";
import { AppShell, surfaceClass, useTheme } from "@/components/AppShell";
import { ProductCard } from "@/components/ProductCard";
import {
  checkApiHealth,
  fetchHomeSummary,
  productImageUrl,
  type Product,
} from "@/lib/products";

export default function HomePage() {
  return (
    <AppShell title="ホーム">
      <HomeContent />
    </AppShell>
  );
}

function HomeContent() {
  const { darkMode } = useTheme();
  const [productCount, setProductCount] = useState<number | null>(null);
  const [recentProducts, setRecentProducts] = useState<Product[]>([]);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(true);

  useEffect(() => {
    let cancelled = false;

    void Promise.all([fetchHomeSummary(6), checkApiHealth()])
      .then(([summary, healthy]) => {
        if (cancelled) return;
        setProductCount(summary.count);
        setRecentProducts(summary.recent);
        setApiOk(healthy);
      })
      .catch(() => {
        if (cancelled) return;
        setApiOk(false);
      })
      .finally(() => {
        if (!cancelled) setLoadingSummary(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const muted = darkMode ? "text-ink-400" : "text-ink-500";

  const tiles = [
    { href: "/scan", label: "コードを読み取る", note: "QR・バーコード", icon: ScanLine },
    { href: "/register", label: "商品を登録する", note: "型番・写真から", icon: PackagePlus },
  ];

  return (
    <div className="space-y-7">
      {/* いちばんよく使う操作：型番ラベルを撮って探す */}
      <section className="relative overflow-hidden rounded-[28px] bg-gradient-to-br from-brand-500 via-brand-600 to-brand-700 p-6 text-white shadow-[0_12px_32px_rgb(21_148_67/0.28)]">
        <div
          aria-hidden
          className="absolute -right-10 -top-12 h-44 w-44 rounded-full bg-white/10"
        />
        <div
          aria-hidden
          className="absolute -bottom-16 right-10 h-36 w-36 rounded-full bg-white/10"
        />
        <p className="relative text-sm font-medium text-white/85">
          型番ラベルを撮るだけ
        </p>
        <h2 className="relative mt-1 text-2xl font-bold leading-snug">
          写真から商品と
          <br />
          施工説明書を探す
        </h2>
        <div className="relative mt-6 flex flex-wrap gap-2.5">
          <Link
            href="/search?tab=image"
            className="inline-flex min-h-12 items-center gap-2 rounded-2xl bg-white px-5 text-[15px] font-bold text-brand-700 shadow-sm transition active:scale-[0.98]"
          >
            <Camera size={20} />
            写真で探す
          </Link>
          <Link
            href="/search"
            className="inline-flex min-h-12 items-center gap-2 rounded-2xl bg-white/20 px-5 text-[15px] font-semibold text-white backdrop-blur transition hover:bg-white/30 active:scale-[0.98]"
          >
            <Search size={20} />
            型番・キーワード
          </Link>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3">
        {tiles.map((tile) => {
          const Icon = tile.icon;

          return (
            <Link
              key={tile.href}
              href={tile.href}
              className={`${surfaceClass(darkMode)} flex flex-col gap-3 p-4 transition active:scale-[0.98]`}
            >
              <span
                className={`flex h-10 w-10 items-center justify-center rounded-full ${
                  darkMode ? "bg-brand-950 text-brand-300" : "bg-brand-50 text-brand-600"
                }`}
              >
                <Icon size={20} />
              </span>
              <span>
                <span className="block text-[15px] font-bold">{tile.label}</span>
                <span className={`mt-0.5 block text-xs ${muted}`}>{tile.note}</span>
              </span>
            </Link>
          );
        })}
      </section>

      <section className="space-y-3">
        <div className="flex items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold">最近の商品</h2>
            <p className={`mt-0.5 flex items-center gap-1.5 text-xs ${muted}`}>
              <span
                aria-hidden
                className={`h-1.5 w-1.5 rounded-full ${
                  apiOk === null
                    ? "bg-ink-300"
                    : apiOk
                      ? "bg-brand-500"
                      : "bg-red-500"
                }`}
              />
              {apiOk === false
                ? "サーバーに接続できません"
                : loadingSummary
                  ? "読み込み中"
                  : `登録 ${productCount ?? 0} 件`}
            </p>
          </div>
          <Link
            href="/search"
            className={`inline-flex min-h-10 items-center gap-0.5 text-sm font-semibold ${
              darkMode ? "text-brand-300" : "text-brand-700"
            }`}
          >
            すべて見る
            <ChevronRight size={16} />
          </Link>
        </div>

        {loadingSummary ? (
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
        ) : recentProducts.length > 0 ? (
          <div className="grid gap-3">
            {recentProducts.map((product) => (
              <ProductCard
                key={product.id}
                product={product}
                darkMode={darkMode}
                imageUrl={productImageUrl}
              />
            ))}
          </div>
        ) : (
          <div
            className={`${surfaceClass(darkMode)} px-6 py-12 text-center ${muted}`}
          >
            <p className="text-sm">まだ商品が登録されていません</p>
            <Link
              href="/register"
              className="mt-4 inline-flex min-h-12 items-center rounded-2xl bg-gradient-to-b from-brand-500 to-brand-700 px-6 text-[15px] font-semibold text-white"
            >
              最初の商品を登録する
            </Link>
          </div>
        )}
      </section>
    </div>
  );
}
