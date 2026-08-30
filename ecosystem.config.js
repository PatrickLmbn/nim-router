const path = require("path");
const fs = require("fs");

const isWin = process.platform === "win32";
const venvPython = isWin
  ? path.join(__dirname, ".venv", "Scripts", "python.exe")
  : path.join(__dirname, ".venv", "bin", "python");

const interpreter = fs.existsSync(venvPython) ? venvPython : (isWin ? "python" : "python3");


module.exports = {
  apps: [
    {
      name: "nim-router",
      script: "nim-router.py",
      interpreter: interpreter,
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};

