import { readdir, stat } from "node:fs/promises";
import { resolve } from "node:path";

const assetsDirectory = resolve(process.cwd(), "dist/assets");
const maximumJavaScriptBytes = 500 * 1024;

const files = await readdir(assetsDirectory);
const javascriptFiles = files.filter((file) => file.endsWith(".js"));

if (javascriptFiles.length === 0) {
  throw new Error(`No JavaScript assets found in ${assetsDirectory}; run the production build first.`);
}

const oversized = [];
for (const file of javascriptFiles) {
  const asset = await stat(resolve(assetsDirectory, file));
  if (asset.size > maximumJavaScriptBytes) {
    oversized.push(`${file}=${asset.size}`);
  }
}

if (oversized.length > 0) {
  throw new Error(
    `Release JavaScript chunk budget exceeded (${maximumJavaScriptBytes} bytes): ${oversized.join(", ")}`,
  );
}

process.stdout.write(
  JSON.stringify({
    status: "pass",
    javascript_chunk_count: javascriptFiles.length,
    maximum_javascript_chunk_bytes: maximumJavaScriptBytes,
  }) + "\n",
);
