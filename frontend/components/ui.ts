/**
 * 画面全体で使い回すクラス名。ボタン・入力欄・面の見た目をここにそろえる。
 * 色は globals.css の brand（緑）と ink（灰色）を使う。
 */

const buttonBase =
  "inline-flex min-h-12 items-center justify-center gap-2 rounded-2xl px-5 text-[15px] font-semibold transition active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50";

/** 主役のボタン（1 画面に 1 つが目安）。 */
export const primaryButton = `${buttonBase} bg-gradient-to-b from-brand-500 to-brand-700 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.25),0_6px_16px_rgb(21_148_67/0.28)] hover:from-brand-600 hover:to-brand-800`;

/** 白地のボタン。 */
export function secondaryButton(darkMode: boolean) {
  return `${buttonBase} ${
    darkMode
      ? "bg-ink-800 text-ink-100 hover:bg-ink-700"
      : "bg-white text-ink-800 shadow-card hover:bg-ink-50"
  }`;
}

/** 薄い緑のボタン（補助的な操作）。 */
export function tonalButton(darkMode: boolean) {
  return `${buttonBase} ${
    darkMode
      ? "bg-brand-950 text-brand-300 hover:bg-brand-900"
      : "bg-brand-50 text-brand-700 hover:bg-brand-100"
  }`;
}

/** 削除など、取り消しにくい操作のボタン。 */
export const dangerButton = `${buttonBase} bg-red-600 text-white hover:bg-red-700`;

/** 文字だけのボタン。 */
export function textButton(darkMode: boolean) {
  return `inline-flex min-h-10 items-center gap-1 rounded-lg px-2 text-sm font-semibold transition ${
    darkMode ? "text-brand-300 hover:text-brand-200" : "text-brand-700 hover:text-brand-800"
  }`;
}

/** 入力欄。背景を薄く色づけして、枠線は目立たせない。 */
export function fieldClass(darkMode: boolean) {
  return `w-full min-h-12 rounded-2xl border-0 px-4 py-3 outline-none ring-1 transition placeholder:text-ink-400 focus:ring-2 focus:ring-brand-500 ${
    darkMode
      ? "bg-ink-900 text-white ring-ink-800"
      : "bg-white text-ink-900 ring-ink-200"
  }`;
}

/** 小さなラベル（チップ）。 */
export function chip(darkMode: boolean) {
  return `inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
    darkMode ? "bg-ink-800 text-ink-200" : "bg-ink-100 text-ink-700"
  }`;
}
