import Link from "next/link";
import { ExternalLink, PackagePlus } from "lucide-react";
import { surfaceClass } from "@/components/AppShell";
import { primaryButton, secondaryButton } from "@/components/ui";
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

  return (
    <section className={`${surfaceClass(darkMode)} space-y-4 p-5`}>
      <div>
        <h2 className="text-lg font-bold">登録されていない商品かもしれません</h2>
        <p
          className={`mt-1.5 text-sm leading-relaxed ${
            darkMode ? "text-ink-400" : "text-ink-600"
          }`}
        >
          読み取った型番：
          <span className="font-mono font-semibold">{modelNumber}</span>
          {maker && `（${maker}）`}
          <br />
          読み間違いがないか、実物のラベルと見比べてください。
        </p>
      </div>

      <div className="grid gap-2.5 sm:flex sm:flex-wrap">
        <Link href={registerHref} className={primaryButton}>
          <PackagePlus size={18} />
          この型番で登録する
        </Link>
        {links.map((link) => (
          <a
            key={link.label}
            href={link.url}
            target="_blank"
            rel="noreferrer noopener"
            className={secondaryButton(darkMode)}
          >
            <ExternalLink size={16} />
            {link.label}
          </a>
        ))}
      </div>
    </section>
  );
}
