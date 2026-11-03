"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useContext,
  useEffect,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import {
  ChevronLeft,
  Home,
  PackagePlus,
  ScanLine,
  Search,
  Settings,
} from "lucide-react";
import { AppLogo } from "@/components/AppLogo";
import { isNavActive, NAV_ITEMS } from "@/lib/nav";

type ThemeContextValue = {
  darkMode: boolean;
  setDarkMode: (value: boolean) => void;
  toggleDarkMode: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

const DARK_MODE_KEY = "darkMode";
const DARK_MODE_EVENT = "sekou-navi:dark-mode";
let memoryDarkMode = false;

// ダークモード設定は localStorage に保存し、タブ間・コンポーネント間で同期する
function subscribeDarkMode(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(DARK_MODE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(DARK_MODE_EVENT, onChange);
  };
}

function readDarkMode(): boolean {
  try {
    return localStorage.getItem(DARK_MODE_KEY) === "true";
  } catch {
    return memoryDarkMode;
  }
}

function writeDarkMode(value: boolean) {
  memoryDarkMode = value;
  try {
    localStorage.setItem(DARK_MODE_KEY, String(value));
  } catch {
    // 保存できない環境（プライベートブラウズ等）でも画面上は切り替える
  }
  window.dispatchEvent(new Event(DARK_MODE_EVENT));
}

export function useTheme() {
  const context = useContext(ThemeContext);

  if (!context) {
    throw new Error("useTheme must be used within AppShell");
  }

  return context;
}

type AppShellProps = {
  children: ReactNode;
  title: string;
  description?: string;
  /** true にすると、タイトルの上に「戻る」を出す（詳細画面など） */
  back?: boolean;
};

const NAV_ICONS = {
  "/": Home,
  "/search": Search,
  "/scan": ScanLine,
  "/register": PackagePlus,
  "/settings": Settings,
} as const;

export function AppShell({
  children,
  title,
  description,
  back,
}: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const darkMode = useSyncExternalStore(
    subscribeDarkMode,
    readDarkMode,
    () => false
  );

  function applyDarkMode(next: boolean) {
    writeDarkMode(next);
  }

  function toggleDarkMode() {
    applyDarkMode(!darkMode);
  }

  // 画面の端（スクロールの行き過ぎ部分など）も、テーマの色にそろえる
  useEffect(() => {
    document.documentElement.style.colorScheme = darkMode ? "dark" : "light";
    document.body.style.background = darkMode ? "#0d1511" : "";
  }, [darkMode]);

  const muted = darkMode ? "text-ink-400" : "text-ink-500";

  return (
    <ThemeContext.Provider
      value={{ darkMode, setDarkMode: applyDarkMode, toggleDarkMode }}
    >
      <div
        className={`min-h-dvh ${
          darkMode ? "bg-ink-950 text-ink-50" : "bg-ink-50 text-ink-900"
        }`}
      >
        <div className="mx-auto flex min-h-dvh max-w-6xl">
          {/* パソコン・タブレット：左のサイドバー */}
          <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col px-4 py-7 lg:flex">
            <Link href="/" className="flex items-center gap-3 px-2">
              <AppLogo size={40} />
              <span className="text-lg font-bold tracking-tight">施工ナビ</span>
            </Link>

            <nav className="mt-8 flex flex-col gap-1">
              {NAV_ITEMS.map((item) => {
                const active = isNavActive(pathname, item.href);
                const Icon = NAV_ICONS[item.href];

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`flex min-h-11 items-center gap-3 rounded-xl px-3 text-[15px] transition ${
                      active
                        ? darkMode
                          ? "bg-brand-950 font-semibold text-brand-300"
                          : "bg-brand-50 font-semibold text-brand-700"
                        : darkMode
                          ? "font-medium text-ink-300 hover:bg-ink-900"
                          : "font-medium text-ink-600 hover:bg-ink-100"
                    }`}
                  >
                    <Icon size={20} strokeWidth={active ? 2.4 : 2} />
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </aside>

          <div className="flex min-w-0 flex-1 flex-col">
            <header className="px-5 pb-3 pt-[max(1.5rem,env(safe-area-inset-top))] md:px-8 md:pt-9">
              {back ? (
                <button
                  type="button"
                  onClick={() => router.back()}
                  className={`-ml-2 mb-2 inline-flex min-h-11 items-center gap-0.5 rounded-xl px-2 text-[15px] font-semibold ${
                    darkMode ? "text-brand-300" : "text-brand-700"
                  }`}
                >
                  <ChevronLeft size={20} />
                  戻る
                </button>
              ) : (
                <div className="mb-3 flex items-center gap-2 lg:hidden">
                  <AppLogo size={28} />
                  <span className="text-sm font-bold tracking-tight">施工ナビ</span>
                </div>
              )}
              <h1 className="text-[28px] font-bold leading-tight tracking-tight md:text-3xl">
                {title}
              </h1>
              {description && (
                <p className={`mt-1.5 text-[15px] leading-relaxed ${muted}`}>
                  {description}
                </p>
              )}
            </header>

            <main className="w-full max-w-3xl flex-1 px-5 pb-32 pt-2 md:px-8 lg:pb-12">
              {children}
            </main>
          </div>
        </div>

        {/* スマホ：画面下のタブバー。真ん中のスキャンだけ目立たせる */}
        <nav
          aria-label="メインメニュー"
          className={`fixed inset-x-3 bottom-[max(0.75rem,env(safe-area-inset-bottom))] z-30 grid grid-cols-5 items-end rounded-[28px] px-1 pb-1.5 pt-1.5 shadow-float backdrop-blur-xl lg:hidden ${
            darkMode ? "bg-ink-900/90" : "bg-white/90"
          }`}
        >
          {NAV_ITEMS.map((item) => {
            const active = isNavActive(pathname, item.href);
            const Icon = NAV_ICONS[item.href];
            const isScan = item.href === "/scan";

            if (isScan) {
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className="flex flex-col items-center gap-1 pb-0.5"
                >
                  <span
                    className={`-mt-7 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-b from-brand-400 to-brand-600 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.3),0_8px_20px_rgb(21_148_67/0.4)] ring-4 transition active:scale-95 ${
                      darkMode ? "ring-ink-950" : "ring-ink-50"
                    }`}
                  >
                    <Icon size={26} strokeWidth={2.2} />
                  </span>
                  <span
                    className={`text-[11px] font-semibold ${
                      active ? "text-brand-600" : muted
                    }`}
                  >
                    {item.label}
                  </span>
                </Link>
              );
            }

            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-14 flex-col items-center justify-center gap-0.5 rounded-2xl text-[11px] transition ${
                  active ? "font-semibold text-brand-600" : `font-medium ${muted}`
                }`}
              >
                <Icon size={22} strokeWidth={active ? 2.4 : 2} />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </ThemeContext.Provider>
  );
}

/** 白い面（カード）。枠線ではなく、うっすらした影で浮かせる。 */
export function surfaceClass(darkMode: boolean) {
  return darkMode
    ? "rounded-3xl bg-ink-900 shadow-none ring-1 ring-ink-800"
    : "rounded-3xl bg-white shadow-card";
}
