// Pure helpers for the new-translation form. No imports so `node --test` can load this file directly.

export const ACCEPT = ".png,.jpg,.jpeg,.webp,.zip,.cbz";
const IMAGE = ["png", "jpg", "jpeg", "webp"];
// Content type is derived from the extension (browsers report "" for .cbz and vary for .zip).
const CONTENT_TYPES: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
  zip: "application/zip",
  cbz: "application/vnd.comicbook+zip",
};

export function extension(name: string): string {
  const i = name.lastIndexOf(".");
  return i < 0 ? "" : name.slice(i + 1).toLowerCase();
}

export const isImage = (name: string) => IMAGE.includes(extension(name));
export const contentType = (name: string) => CONTENT_TYPES[extension(name)] ?? "application/octet-stream";

export type FileProblem = "type" | "size" | "empty" | null;

/** maxMb applies per file (docs/API.md: "Size limits come from /pricing.limits"). */
export function checkFile(name: string, size: number, maxMb: number): FileProblem {
  if (!(extension(name) in CONTENT_TYPES)) return "type";
  if (size <= 0) return "empty";
  if (size > maxMb * 1024 * 1024) return "size";
  return null;
}

export interface GlossaryEntry {
  source: string;
  target: string;
}

/** One `source = target` per line; blank lines ignored; returns 1-based numbers of malformed lines. */
export function parseGlossary(text: string): { entries: GlossaryEntry[]; invalid: number[] } {
  const entries: GlossaryEntry[] = [];
  const invalid: number[] = [];
  text.split(/\r?\n/).forEach((raw, i) => {
    const line = raw.trim();
    if (!line) return;
    const eq = line.indexOf("=");
    const source = eq < 0 ? "" : line.slice(0, eq).trim();
    const target = eq < 0 ? "" : line.slice(eq + 1).trim();
    if (source && target) entries.push({ source, target });
    else invalid.push(i + 1);
  });
  return { entries, invalid };
}

/** Credits for the image files; archives are only counted after extraction on the server. */
export function estimateCredits(names: string[], perPage: number) {
  const images = names.filter(isImage).length;
  return { images, credits: images * perPage, hasArchives: names.length > images };
}

/** Pricing blocks for one page: max(1, ceil(w·h / (mp·10⁶))) — docs/API.md "Page price". */
export function pageBlocks(width: number, height: number, megapixels: number): number {
  if (!(width > 0 && height > 0 && megapixels > 0)) return 1;
  return Math.max(1, Math.ceil((width * height) / (megapixels * 1e6)));
}

/** Credits for one page = rate × blocks. */
export const pageCredits = (width: number, height: number, rate: number, megapixels: number) =>
  rate * pageBlocks(width, height, megapixels);

/** Referral codes are short and URL-safe (API accepts ≤ 16 chars); anything else is dropped. */
export const cleanRef = (v: string | null | undefined) => (v && /^[A-Za-z0-9_-]{1,16}$/.test(v) ? v : undefined);
