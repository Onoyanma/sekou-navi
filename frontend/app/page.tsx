"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Barcode,
  ChevronRight,
  Package,
  PackagePlus,
  Search,
  Wifi,
} from "lucide-react";
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
    <AppShell
      title="ホーム"
      description="施工ナビのメニューと登録商品の概要です"
    >
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

    void Promise.all([
      fetchHomeSummary(6),
      checkApiHealth(),
    ])
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

  const quickActions = [
    {
      href: "/search",
      label: "検索",
      description: "キーワード・画像で商品を探す",
      icon: Search,
      color: "bg-blue-600 text-white",
    },
    {
      href: "/scan",
      label: "スキャン",
      description: "QR・バーコードを読み取る",
      icon: Barcode,
      color: "bg-violet-600 text-white",
    },
    {
      href: "/register",
      label: "登録",
      description: "新しい商品を追加する",
      icon: PackagePlus,
      color: "bg-emerald-600 text-white",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className={`${surfaceClass(darkMode)} p-5`}>
          <div className="flex items-center justify-between">
            <div>
              <p
                className={
                  darkMode ? "text-sm text-slate-400" : "text-sm text-slate-500"
                }
              >
                登録商品
              </p>
              <p className="mt-2 text-3xl font-bold">
                {loadingSummary ? "—" : productCount ?? 0}
              </p>
            </div>
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-100 text-blue-600">
              <Package size={22} />
            </div>
          </div>
        </div>

        <div className={`${surfaceClass(darkMode)} p-5`}>
          <div className="flex items-center justify-between">
            <div>
              <p
                className={
                  darkMode ? "text-sm text-slate-400" : "text-sm text-slate-500"
                }
              >
                API
              </p>
              <p className="mt-2 text-3xl font-bold">
                {apiOk === null ? "—" : apiOk ? "接続中" : "未接続"}
              </p>
            </div>
            <div
              className={`flex h-12 w-12 items-center justify-center rounded-xl ${
                apiOk === null
                  ? "bg-slate-100 text-slate-400"
                  : apiOk
                    ? "bg-emerald-100 text-emerald-600"
                    : "bg-red-100 text-red-600"
              }`}
            >
              <Wifi size={22} />
            </div>
          </div>
        </div>
      </div>

      <section className="space-y-3">
        <h2
          className={
            darkMode
              ? "text-lg font-bold text-white"
              : "text-lg font-bold text-slate-900"
          }
        >
          クイックアクセス
        </h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {quickActions.map((action) => {
            const Icon = action.icon;

            return (
              <Link
                key={action.href}
                href={action.href}
                className={`${surfaceClass(darkMode)} group flex items-center gap-4 p-4 transition hover:border-blue-500/50`}
              >
                <div
                  className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${action.color}`}
                >
                  <Icon size={20} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">{action.label}</p>
                  <p
                    className={
                      darkMode
                        ? "mt-0.5 text-xs text-slate-400"
                        : "mt-0.5 text-xs text-slate-500"
                    }
                  >
                    {action.description}
                  </p>
                </div>
                <ChevronRight
                  size={18}
                  className={
                    darkMode
                      ? "text-slate-600 group-hover:text-slate-400"
                      : "text-slate-300 group-hover:text-slate-500"
                  }
                />
              </Link>
            );
          })}
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h2
            className={
              darkMode
                ? "text-lg font-bold text-white"
                : "text-lg font-bold text-slate-900"
            }
          >
            最近登録した商品
          </h2>
          <Link
            href="/search"
            className={
              darkMode
                ? "text-sm font-medium text-blue-400 hover:text-blue-300"
                : "text-sm font-medium text-blue-600 hover:text-blue-700"
            }
          >
            すべて見る
          </Link>
        </div>

        {loadingSummary ? (
          <div className="grid gap-4">
            {Array.from({ length: 3 }).map((_, index) => (
              <div
                key={index}
                className={`${surfaceClass(darkMode)} h-32 animate-pulse bg-slate-100/50 dark:bg-slate-800/50`}
              />
            ))}
          </div>
        ) : recentProducts.length > 0 ? (
          <div className="grid gap-4">
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
            className={`${surfaceClass(darkMode)} p-10 text-center text-sm ${
              darkMode ? "text-slate-400" : "text-slate-500"
            }`}
          >
            まだ商品が登録されていません。
            <Link
              href="/register"
              className="ml-1 font-semibold text-blue-600 hover:underline"
            >
              登録する
            </Link>
          </div>
        )}
      </section>
    </div>
  );
}
