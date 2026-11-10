#!/usr/bin/env node

/**
 * Groma Node.js CLI Runner
 * Forwards CLI calls to Groma's Python engine while keeping zero config for JavaScript/TypeScript developers.
 */

const { spawn, spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const packageRoot = path.resolve(__dirname, "..");
const args = process.argv.slice(2);

// Function to find an available python executable
function findPython() {
  // 1. Check local virtualenv inside the package if it exists
  const localVenvPython = path.join(packageRoot, ".venv", "bin", "python");
  if (fs.existsSync(localVenvPython)) {
    return localVenvPython;
  }

  // 2. Check system python3
  const checkPython3 = spawnSync("python3", ["--version"], { stdio: "ignore" });
  if (checkPython3.status === 0) {
    return "python3";
  }

  // 3. Check system python
  const checkPython = spawnSync("python", ["--version"], { stdio: "ignore" });
  if (checkPython.status === 0) {
    return "python";
  }

  return null;
}

const pythonBin = findPython();

if (!pythonBin) {
  console.error(
    "\x1b[31mError: Python 3 was not found on your system.\x1b[0m\n" +
      "Groma's analysis engine requires Python 3.10+ to be installed.\n" +
      "Please install Python from https://www.python.org/ or via your package manager."
  );
  process.exit(1);
}

// Ensure package root is in PYTHONPATH so python can locate the 'groma' module
const env = {
  ...process.env,
  PYTHONPATH: process.env.PYTHONPATH
    ? `${packageRoot}${path.delimiter}${process.env.PYTHONPATH}`
    : packageRoot,
};

// Spawn the python process running groma
const child = spawn(pythonBin, ["-m", "groma", ...args], {
  env,
  stdio: "inherit",
});

child.on("error", (err) => {
  console.error(`\x1b[31mFailed to start Groma:\x1b[0m ${err.message}`);
  process.exit(1);
});

child.on("close", (code) => {
  process.exit(code ?? 0);
});

