#!/usr/bin/env node
const { execSync } = require("child_process");
const { mkdirSync, cpSync, writeFileSync } = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const out = path.join(root, "onreza-output");

mkdirSync(out, { recursive: true });

for (const item of ["lib", "static", "server.cjs"]) {
  const src = path.join(root, item);
  const dest = path.join(out, item);
  cpSync(src, dest, { recursive: true });
}

writeFileSync(
  path.join(out, "package.json"),
  JSON.stringify(
    {
      name: "optimus-ai",
      private: true,
      type: "commonjs",
      scripts: { start: "node server.cjs" },
      dependencies: { express: "^4.21.2" },
      engines: { node: ">=22" },
    },
    null,
    2
  )
);

console.log("> npm install --omit=dev (onreza-output)");
execSync("npm install --omit=dev", { cwd: out, stdio: "inherit" });
console.log("> build output:", out);
