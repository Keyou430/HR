import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("exports portal bootstrap contracts", async () => {
  const source = await readFile(new URL("../src/types/index.ts", import.meta.url), "utf8");

  for (const name of [
    "EmbedUrls",
    "PortalCatalogItem",
    "PortalCatalog",
    "PortalBootstrapResponse",
  ]) {
    assert.equal(source.includes(`export interface ${name}`), true, `${name} is missing`);
  }
});
