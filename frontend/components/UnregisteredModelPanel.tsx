import Link from "next/link";
import { ExternalLink, PackagePlus } from "lucide-react";
import { surfaceClass } from "@/components/AppShell";
import { buildManualSearchLinks } from "@/lib/manualLinks";

type UnregisteredModelPanelProps = {
  darkMode: boolean;
  modelNumber: string;
  maker: string;
};

/** 登録済み商品に自信を持って当てはまらないときに、次の行動（登録・説明書の検索）を示す。 */
export function UnregisteredModelPanel({
  darkMode,
  modelNumber,
  maker,
}: UnregisteredModelPanelProps) {
  const links = buildManualSearchLinks(maker, modelNumber);
  const registerHref = `/register?model_number=${encodeURIComponent(modelNumber)}`;

  const secondaryButton = darkMode
    ? "inline-flex items-center gap-2 rounded-xl border border-slate-700 px-4 py-3 text-sm font-semibold text-slate-200 hover:bg-slate-800"
    : "inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50";

  return (
    <section className={`${surfaceClass(darkMode)} space-y-4 p-5`}>
      <div>
        <h2
          className={
            darkMode
              ? "text-base font-bold text-white"
              : "text-base font-bold text-slate-900"
          }
        >
          登録されていない商品かもしれません
        </h2>
        <p
          className={
            darkMode
              ? "mt-1 text-sm text-slate-400"
              : "mt-1 text-sm text-slate-600"
          }
        >
          読み取った型番:{" "}
          <span className="font-mono font-semibold">{modelNumber}</span>
          {maker && `（${maker}）`}
          。読み間違いがないか、実物のラベルと見比べてください。
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Link
          href={registerHref}
          className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700"
        >
          <PackagePlus size={18} />
          この型番で登録する
        </Link>
        {links.map((link) => (
          <a
            key={link.label}
            href={link.url}
            target="_blank"
            rel="noreferrer noopener"
            className={secondaryButton}
          >
            <ExternalLink size={16} />
            {link.label}
          </a>
        ))}
      </div>
    </section>
  );
}
