export const NAV_ITEMS = [
  { href: "/", label: "ホーム" },
  { href: "/search", label: "検索" },
  { href: "/scan", label: "スキャン" },
  { href: "/register", label: "登録" },
  { href: "/settings", label: "設定" },
] as const;

export function isNavActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }

  return pathname === href || pathname.startsWith(`${href}/`);
}
