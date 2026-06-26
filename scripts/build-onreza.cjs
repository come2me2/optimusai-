#!/usr/bin/env node
const { execSync } = require("child_process");
const { mkdirSync, cpSync, existsSync } = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const out = path.join(root, "onreza-output");

console.log("> pip install .");
execSync("pip install .", { cwd: root, stdio: "inherit" });

mkdirSync(out, { recursive: true });

for (const item of ["static", "server.py", "server.cjs", "pyproject.toml", "requirements.txt"]) {
  const src = path.join(root, item);
  if (!existsSync(src)) continue;
  const dest = path.join(out, item);
  cpSync(src, dest, { recursive: true });
}

console.log("> build output:", out);
