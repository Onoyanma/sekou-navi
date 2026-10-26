"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  Barcode,
  HardHat,
  Home,
  PackagePlus,
  Search,
  Settings,
} from "lucide-react";
import { isNavActive, NAV_ITEMS } from "@/lib/nav";

type ThemeContextValue = {
  darkMode: boolean;
  setDarkMode: (value: boolean) => void;
  toggleDarkMode: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

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
};

const NAV_ICONS = {
  "/": Home,
  "/search": Search,
  "/scan": Barcode,
  "/register": PackagePlus,
  "/settings": Settings,
} as const;

export function AppShell({ children, title, description }: AppShellProps) {
  const pathname = usePathname();
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    setDarkMode(localStorage.getItem("darkMode") === "true");
  }, []);

  function applyDarkMode(next: boolean) {
    setDarkMode(next);
    localStorage.setItem("darkMode", String(next));
  }

  function toggleDarkMode() {
    applyDarkMode(!darkMode);
  }

  const shellBg = darkMode
    ? "bg-slate-950 text-slate-100"
    : "bg-slate-50 text-slate-900";
  const sidebarBg = darkMode
    ? "bg-slate-900 border-slate-800"
    : "bg-white border-slate-200";

  return (
    <ThemeContext.Provider
      value={{ darkMode, setDarkMode: applyDarkMode, toggleDarkMode }}
    >
      <div className={`min-h-screen ${shellBg}`}>
        <div className="mx-auto flex min-h-screen max-w-7xl">
          <aside
            className={`hidden w-64 shrink-0 flex-col border-r lg:flex ${sidebarBg}`}
          >
            <div className="flex items-center gap-3 border-b px-5 py-5">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-white shadow-lg shadow-blue-600/30">
                <HardHat size={22} />
              </div>
              <div>
                <p className="text-lg font-bold leading-tight">施工ナビ</p>
                <p className="text-xs text-slate-500">現場向け商品DB</p>
              </div>
            </div>

            <nav className="flex flex-1 flex-col gap-1 p-3">
              {NAV_ITEMS.map((item) => {
                const active = isNavActive(pathname, item.href);
                const Icon = NAV_ICONS[item.href];

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={
                      active
                        ? "flex items-center gap-3 rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white shadow-md shadow-blue-600/25"
                        : darkMode
                          ? "flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium text-slate-300 hover:bg-slate-800"
                          : "flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium text-slate-600 hover:bg-slate-100"
                    }
                  >
                    <Icon size={18} />
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </aside>

          <div className="flex min-w-0 flex-1 flex-col">
            <header
              className={`sticky top-0 z-20 border-b px-4 py-4 backdrop-blur md:px-8 ${
                darkMode
                  ? "border-slate-800 bg-slate-950/80"
                  : "border-slate-200 bg-white/80"
              }`}
            >
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">
                  Sekou Navi
                </p>
                <h1 className="mt-1 text-2xl font-bold">{title}</h1>
                {description && (
                  <p
                    className={
                      darkMode
                        ? "mt-1 text-sm text-slate-400"
                        : "mt-1 text-sm text-slate-500"
                    }
                  >
                    {description}
                  </p>
                )}
              </div>
            </header>

            <main className="flex-1 px-4 py-6 md:px-8">{children}</main>

            <nav
              className={`fixed bottom-0 left-0 right-0 z-30 grid grid-cols-5 border-t lg:hidden ${sidebarBg}`}
            >
              {NAV_ITEMS.map((item) => {
                const active = isNavActive(pathname, item.href);
                const Icon = NAV_ICONS[item.href];

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={
                      active
                        ? "flex flex-col items-center gap-0.5 py-2.5 text-[10px] font-semibold text-blue-600"
                        : "flex flex-col items-center gap-0.5 py-2.5 text-[10px] font-medium text-slate-500"
                    }
                  >
                    <Icon size={20} />
                    {item.label}
                  </Link>
                );
              })}
            </nav>

            <div className="h-16 lg:hidden" />
          </div>
        </div>
      </div>
    </ThemeContext.Provider>
  );
}

export function surfaceClass(darkMode: boolean) {
  return darkMode
    ? "rounded-2xl border border-slate-800 bg-slate-900 shadow-sm"
    : "rounded-2xl border border-slate-200 bg-white shadow-sm";
}
