// Run with `pnpm test` (Node 24 strips TypeScript types natively).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { checkFile, contentType, estimateCredits, parseGlossary } from "../src/lib/upload-rules.ts";

test("glossary parsing", () => {
  const { entries, invalid } = parseGlossary("师姐 = sư tỷ\n\n bad line \nA=B=C\n= x\n");
  assert.deepEqual(entries, [{ source: "师姐", target: "sư tỷ" }, { source: "A", target: "B=C" }]);
  assert.deepEqual(invalid, [3, 5]);
});

test("file checks and estimate", () => {
  assert.equal(checkFile("p1.PNG", 10, 1), null);
  assert.equal(checkFile("x.gif", 10, 1), "type");
  assert.equal(checkFile("x.cbz", 2 * 1024 * 1024, 1), "size");
  assert.equal(checkFile("x.jpg", 0, 1), "empty");
  assert.equal(contentType("ch.cbz"), "application/vnd.comicbook+zip");
  assert.deepEqual(estimateCredits(["a.jpg", "b.webp", "c.zip"], 2), { images: 2, credits: 4, hasArchives: true });
});

test("vi and en messages have the same keys", () => {
  const keys = (o, p = "") =>
    Object.entries(o).flatMap(([k, v]) => (v && typeof v === "object" ? keys(v, `${p}${k}.`) : [`${p}${k}`]));
  const load = (l) => keys(JSON.parse(readFileSync(new URL(`../messages/${l}.json`, import.meta.url), "utf8"))).sort();
  assert.deepEqual(load("vi"), load("en"));
});
