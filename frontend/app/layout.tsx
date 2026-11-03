import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "施工ナビ",
  description: "施工商品の検索・登録支援アプリ",
};

export const viewport: Viewport = {
  themeColor: "#1fb155",
  // ノッチのある端末で、画面の端まで背景を広げる
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
