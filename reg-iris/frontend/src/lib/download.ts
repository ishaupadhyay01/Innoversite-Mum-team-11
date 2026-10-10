import { withAuth } from "@/api/client";

/** Downloads through fetch so the bearer token (if any) is sent; works for streamed CSV. */
export async function downloadFile(url: string, filename: string): Promise<void> {
  const resp = await fetch(url, { headers: withAuth() });
  if (!resp.ok) throw new Error(`Download failed (${resp.status})`);
  const blob = await resp.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
