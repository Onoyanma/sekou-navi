/**
 * アップロード前に写真を縮小する。
 * 現場は電波が弱いことが多く、スマホの写真（数 MB）をそのまま送ると時間がかかる。
 * サーバー側の OCR も長辺 1600px に縮めて読むので、同じ大きさにしても精度は変わらない。
 */
const MAX_SIDE = 1600;
const SKIP_BELOW_BYTES = 800 * 1024;

export async function downscaleImage(
  file: File,
  maxSide: number = MAX_SIDE
): Promise<File> {
  try {
    // from-image: スマホの撮影向き（EXIF）を反映した状態で縮小する
    const bitmap = await createImageBitmap(file, {
      imageOrientation: "from-image",
    });
    const longest = Math.max(bitmap.width, bitmap.height);

    if (longest <= maxSide && file.size <= SKIP_BELOW_BYTES) {
      bitmap.close();
      return file;
    }

    const ratio = Math.min(1, maxSide / longest);
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * ratio);
    canvas.height = Math.round(bitmap.height * ratio);

    const context = canvas.getContext("2d");
    if (!context) {
      bitmap.close();
      return file;
    }

    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.9)
    );

    // 縮小して逆に大きくなる場合や、変換に失敗した場合は元の写真を使う
    if (!blob || blob.size >= file.size) return file;

    return new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", {
      type: "image/jpeg",
      lastModified: file.lastModified,
    });
  } catch {
    // 形式が読めないときなどは、そのままサーバーに任せる
    return file;
  }
}
