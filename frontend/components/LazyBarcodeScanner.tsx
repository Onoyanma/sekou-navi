"use client";

import dynamic from "next/dynamic";
import { Loader2 } from "lucide-react";

export const LazyBarcodeScanner = dynamic(
  () =>
    import("./BarcodeScanner").then((mod) => ({
      default: mod.BarcodeScanner,
    })),
  {
    ssr: false,
    loading: () => (
      <div className="flex min-h-[12rem] items-center justify-center rounded-2xl border border-dashed border-ink-300 bg-ink-50 dark:border-ink-700 dark:bg-ink-900">
        <Loader2 className="animate-spin text-ink-400" size={24} />
      </div>
    ),
  }
);
