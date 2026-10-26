import { apiUrl } from "@/lib/api";
export { productImageUrl } from "@/lib/api";

export type Product = {
  id: number;
  maker: string;
  product_name: string;
  model_number: string;
  category: string;
  memo: string;
  tags: string;
  install_url: string;
  image_path: string;
};


export function toProduct(raw: Record<string, unknown>): Product {
  const imagePath =
    (raw.matched_image_path as string) ||
    (raw.image_path as string) ||
    (raw.product_image_path as string) ||
    "";

  return {
    id: raw.id as number,
    maker: (raw.maker as string) || "",
    product_name: (raw.product_name as string) || "",
    model_number: (raw.model_number as string) || "",
    category: (raw.category as string) || "",
    memo: (raw.memo as string) || "",
    tags: (raw.tags as string) || "",
    install_url: (raw.install_url as string) || "",
    image_path: imagePath,
  };
}

export type HomeSummary = {
  count: number;
  recent: Product[];
};

export async function fetchHomeSummary(limit = 6): Promise<HomeSummary> {
  const response = await fetch(
    apiUrl(`/products/summary?limit=${limit}`)
  );

  if (!response.ok) {
    throw new Error("商品サマリーの取得に失敗しました");
  }

  const data = (await response.json()) as {
    count: number;
    recent: Record<string, unknown>[];
  };

  return {
    count: data.count,
    recent: data.recent.map(toProduct),
  };
}

export async function checkApiHealth(): Promise<boolean> {
  try {
    const response = await fetch(apiUrl("/"), {
      method: "GET",
      cache: "no-store",
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function fetchProducts(): Promise<Product[]> {
  const response = await fetch(apiUrl("/products"));
  return response.json();
}
