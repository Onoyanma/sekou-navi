"use client";

import { useEffect, useState } from "react";
import { Moon, Sun, Trash2 } from "lucide-react";
import { AppShell, surfaceClass, useTheme } from "@/components/AppShell";
import { clearBarcodeRegisterDraft } from "@/lib/barcode";
import { API_BASE_URL } from "@/lib/api";

const SEARCH_HISTORY_KEY = "sekou_navi_search_history";
const MAKER_HISTORY_KEY = "sekou_navi_history_maker";
const PRODUCT_NAME_HISTORY_KEY = "sekou_navi_history_product_name";

export default function SettingsPage() {
  return (
    <AppShell title="設定" description="表示やデータの管理を行います">
      <SettingsContent />
    </AppShell>
  );
}

function SettingsContent() {
  const { darkMode, setDarkMode } = useTheme();
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(() => setMessage(""), 3000);
    return () => window.clearTimeout(timer);
  }, [message]);

  function clearStorage(keys: string[], notice: string) {
    for (const key of keys) {
      localStorage.removeItem(key);
    }
    setMessage(notice);
  }

  const rowClass = darkMode
    ? "flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-950 p-4"
    : "flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4";

  return (
    <div className="space-y-6">
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

      <section className={`${surfaceClass(darkMode)} space-y-4 p-5 md:p-6`}>
        <h2
          className={
            darkMode
              ? "text-lg font-bold text-white"
              : "text-lg font-bold text-slate-900"
          }
        >
          表示
        </h2>

        <div className={rowClass}>
          <div>
            <p className="font-semibold">ダークモード</p>
            <p
              className={
                darkMode
                  ? "mt-1 text-sm text-slate-400"
                  : "mt-1 text-sm text-slate-500"
              }
            >
              画面の明るさを切り替えます
            </p>
          </div>
          <button
            type="button"
            onClick={() => setDarkMode(!darkMode)}
            className={
              darkMode
                ? "inline-flex items-center gap-2 rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-amber-300 hover:bg-slate-800"
                : "inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-white"
            }
          >
            {darkMode ? <Sun size={16} /> : <Moon size={16} />}
            {darkMode ? "ライトに切替" : "ダークに切替"}
          </button>
        </div>
      </section>

      <section className={`${surfaceClass(darkMode)} space-y-4 p-5 md:p-6`}>
        <h2
          className={
            darkMode
              ? "text-lg font-bold text-white"
              : "text-lg font-bold text-slate-900"
          }
        >
          データ
        </h2>

        <div className={rowClass}>
          <div>
            <p className="font-semibold">検索履歴</p>
            <p
              className={
                darkMode
                  ? "mt-1 text-sm text-slate-400"
                  : "mt-1 text-sm text-slate-500"
              }
            >
              検索画面の「最近の検索」を削除します
            </p>
          </div>
          <button
            type="button"
            onClick={() =>
              clearStorage([SEARCH_HISTORY_KEY], "検索履歴を削除しました。")
            }
            className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700"
          >
            <Trash2 size={16} />
            削除
          </button>
        </div>

        <div className={rowClass}>
          <div>
            <p className="font-semibold">入力候補の履歴</p>
            <p
              className={
                darkMode
                  ? "mt-1 text-sm text-slate-400"
                  : "mt-1 text-sm text-slate-500"
              }
            >
              メーカー・商品名のオートコンプリート履歴を削除します
            </p>
          </div>
          <button
            type="button"
            onClick={() =>
              clearStorage(
                [MAKER_HISTORY_KEY, PRODUCT_NAME_HISTORY_KEY],
                "入力候補の履歴を削除しました。"
              )
            }
            className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700"
          >
            <Trash2 size={16} />
            削除
          </button>
        </div>

        <div className={rowClass}>
          <div>
            <p className="font-semibold">スキャン登録の下書き</p>
            <p
              className={
                darkMode
                  ? "mt-1 text-sm text-slate-400"
                  : "mt-1 text-sm text-slate-500"
              }
            >
              検索から登録画面へ引き継いだコード情報を削除します
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              clearBarcodeRegisterDraft();
              setMessage("スキャン登録の下書きを削除しました。");
            }}
            className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700"
          >
            <Trash2 size={16} />
            削除
          </button>
        </div>
      </section>

      <section className={`${surfaceClass(darkMode)} space-y-3 p-5 md:p-6`}>
        <h2
          className={
            darkMode
              ? "text-lg font-bold text-white"
              : "text-lg font-bold text-slate-900"
          }
        >
          API
        </h2>
        <p
          className={
            darkMode ? "text-sm text-slate-400" : "text-sm text-slate-500"
          }
        >
          バックエンド: {API_BASE_URL}
        </p>
      </section>
    </div>
  );
}
