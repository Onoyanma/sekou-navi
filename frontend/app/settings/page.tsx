"use client";

import { useEffect, useState, type ReactNode } from "react";
import { CheckCircle2, Moon, Trash2 } from "lucide-react";
import { AppShell, surfaceClass, useTheme } from "@/components/AppShell";
import { clearBarcodeRegisterDraft } from "@/lib/barcode";
import { API_BASE_URL } from "@/lib/api";

const SEARCH_HISTORY_KEY = "sekou_navi_search_history";
const MAKER_HISTORY_KEY = "sekou_navi_history_maker";
const PRODUCT_NAME_HISTORY_KEY = "sekou_navi_history_product_name";

export default function SettingsPage() {
  return (
    <AppShell title="設定">
      <SettingsContent />
    </AppShell>
  );
}

/** 項目を縦に並べた白い面（iOS の設定のような見た目）。 */
function Group({
  title,
  darkMode,
  children,
}: {
  title: string;
  darkMode: boolean;
  children: ReactNode;
}) {
  return (
    <section className="space-y-2">
      <h2
        className={`px-2 text-sm font-semibold ${
          darkMode ? "text-ink-400" : "text-ink-500"
        }`}
      >
        {title}
      </h2>
      <div
        className={`${surfaceClass(darkMode)} divide-y ${
          darkMode ? "divide-ink-800" : "divide-ink-100"
        }`}
      >
        {children}
      </div>
    </section>
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

  const muted = darkMode ? "text-ink-400" : "text-ink-500";

  const dataRows = [
    {
      title: "検索履歴",
      note: "検索画面の「最近の検索」を消します",
      onClear: () =>
        clearStorage([SEARCH_HISTORY_KEY], "検索履歴を削除しました"),
    },
    {
      title: "入力候補の履歴",
      note: "メーカー名・商品名の候補を消します",
      onClear: () =>
        clearStorage(
          [MAKER_HISTORY_KEY, PRODUCT_NAME_HISTORY_KEY],
          "入力候補の履歴を削除しました"
        ),
    },
    {
      title: "スキャン登録の下書き",
      note: "検索から登録画面へ引き継いだ内容を消します",
      onClear: () => {
        clearBarcodeRegisterDraft();
        setMessage("スキャン登録の下書きを削除しました");
      },
    },
  ];

  return (
    <div className="space-y-7">
      <Group title="表示" darkMode={darkMode}>
        <div className="flex items-center justify-between gap-4 p-4">
          <div className="flex items-center gap-3">
            <span
              className={`flex h-9 w-9 items-center justify-center rounded-full ${
                darkMode ? "bg-ink-800 text-ink-200" : "bg-ink-100 text-ink-600"
              }`}
            >
              <Moon size={18} />
            </span>
            <div>
              <p className="text-[15px] font-semibold">ダークモード</p>
              <p className={`text-xs ${muted}`}>暗い場所でも見やすくします</p>
            </div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={darkMode}
            aria-label="ダークモード"
            onClick={() => setDarkMode(!darkMode)}
            className={`relative h-8 w-14 shrink-0 rounded-full transition ${
              darkMode ? "bg-brand-500" : "bg-ink-300"
            }`}
          >
            <span
              className={`absolute left-1 top-1 h-6 w-6 rounded-full bg-white shadow transition-transform ${
                darkMode ? "translate-x-6" : ""
              }`}
            />
          </button>
        </div>
      </Group>

      <Group title="このブラウザに保存しているデータ" darkMode={darkMode}>
        {dataRows.map((row) => (
          <div
            key={row.title}
            className="flex items-center justify-between gap-4 p-4"
          >
            <div className="min-w-0">
              <p className="text-[15px] font-semibold">{row.title}</p>
              <p className={`text-xs ${muted}`}>{row.note}</p>
            </div>
            <button
              type="button"
              onClick={row.onClear}
              className={`inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-full px-4 text-sm font-semibold transition ${
                darkMode
                  ? "bg-red-950/60 text-red-300 hover:bg-red-950"
                  : "bg-red-50 text-red-600 hover:bg-red-100"
              }`}
            >
              <Trash2 size={15} />
              削除
            </button>
          </div>
        ))}
      </Group>

      <Group title="接続" darkMode={darkMode}>
        <div className="p-4">
          <p className="text-[15px] font-semibold">サーバーのアドレス</p>
          <p className={`mt-0.5 break-all font-mono text-xs ${muted}`}>
            {API_BASE_URL}
          </p>
        </div>
      </Group>

      {message && (
        <div
          role="status"
          className="pointer-events-none fixed inset-x-0 bottom-28 z-40 flex justify-center px-5 lg:bottom-10"
        >
          <p
            className={`flex items-center gap-2 rounded-full px-5 py-3 text-sm font-semibold shadow-float ${
              darkMode ? "bg-ink-100 text-ink-900" : "bg-ink-900 text-white"
            }`}
          >
            <CheckCircle2 size={16} className="text-brand-400" />
            {message}
          </p>
        </div>
      )}
    </div>
  );
}
