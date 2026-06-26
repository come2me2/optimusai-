const { spawn, execSync } = require("child_process");
const path = require("path");

function resolvePython() {
  if (process.env.PYTHON) return process.env.PYTHON;
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

const port = process.env.PORT || "8000";
const host = process.env.HOST || "0.0.0.0";
const python = resolvePython();
const serverPy = path.join(__dirname, "server.py");

const child = spawn(python, [serverPy], {
  stdio: "inherit",
  env: {
    ...process.env,
    PORT: String(port),
    HOST: host,
    OPTIMUS_DATA_DIR: process.env.OPTIMUS_DATA_DIR || "/tmp/optimus-data",
  },
  cwd: __dirname,
});

const shutdown = (signal) => {
  if (!child.killed) child.kill(signal);
};

process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
child.on("exit", (code) => process.exit(code ?? 1));
