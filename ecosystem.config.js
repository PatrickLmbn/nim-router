module.exports = {
  apps: [
    {
      name: "nim-router",
      script: "nim-router.py",
      interpreter: "python3",
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};
