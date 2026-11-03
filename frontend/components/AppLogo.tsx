import { HardHat } from "lucide-react";

/** アプリのロゴ。緑のグラデーションの角丸に、白いヘルメット。 */
export function AppLogo({ size = 40 }: { size?: number }) {
  return (
    <span
      aria-hidden
      style={{ width: size, height: size, borderRadius: size * 0.28 }}
      className="inline-flex shrink-0 items-center justify-center bg-gradient-to-b from-brand-300 to-brand-600 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.35),0_4px_12px_rgb(21_148_67/0.3)]"
    >
      <HardHat size={size * 0.56} strokeWidth={2.2} />
    </span>
  );
}
