#!/usr/bin/env node
const { execSync } = require("child_process");
const { mkdirSync, cpSync, existsSync } = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const out = path.join(root, "onreza-output");

function resolvePython() {
  for (const bin of ["python3", "python"]) {
    try {
      execSync(`${bin} --version`, { stdio: "ignore" });
      return bin;
    } catch {
      /* try next */
    }
  }
  return "python3";
}

function pipInstall(cwd, python) {
  const attempts = [
    `${python} -m pip install .`,
    "python3 -m pip install .",
    "python -m pip install .",
    "pip3 install .",
  ];
  for (const cmd of attempts) {
    try {
      console.log(">", cmd);
      execSync(cmd, { cwd, stdio: "inherit" });
      return;
    } catch {
      console.log("!", cmd, "failed, trying next...");
    }
  }
  throw new Error("Could not run pip install — python3/pip not found on build image");
}

const python = resolvePython();
pipInstall(root, python);

mkdirSync(out, { recursive: true });

for (const item of ["static", "server.py", "server.cjs", "pyproject.toml", "requirements.txt"]) {
  const src = path.join(root, item);
  if (!existsSync(src)) continue;
  const dest = path.join(out, item);
  cpSync(src, dest, { recursive: true });
}

console.log("> build output:", out);
