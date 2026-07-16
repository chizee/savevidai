export type Progress = { received: number; total: number | null };

export function buildFilename(
  handle: string,
  id: string,
  label: string,
  index: number,
  totalItems: number,
): string {
  const suffix = totalItems > 1 ? `_${index}` : "";
  return `${handle}_${id}${suffix}_${label}.mp4`;
}

export function proxyUrl(url: string, filename: string): string {
  return `/api/proxy?url=${encodeURIComponent(url)}&filename=${encodeURIComponent(filename)}`;
}

async function fetchBlob(url: string, onProgress: (p: Progress) => void): Promise<Blob> {
  const res = await fetch(url);
  if (!res.ok || !res.body) throw new Error(`fetch failed: ${res.status}`);
  const total = Number(res.headers.get("content-length")) || null;
  const reader = res.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    received += value.length;
    onProgress({ received, total });
  }
  return new Blob(chunks as BlobPart[], { type: "video/mp4" });
}

function saveBlob(blob: Blob, filename: string): void {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
}

/** Direct CDN blob download with progress; transparently falls back to the server proxy. */
export async function downloadVariant(
  url: string,
  filename: string,
  onProgress: (p: Progress) => void,
): Promise<void> {
  let blob: Blob;
  try {
    blob = await fetchBlob(url, onProgress);
  } catch {
    blob = await fetchBlob(proxyUrl(url, filename), onProgress);
  }
  saveBlob(blob, filename);
}
