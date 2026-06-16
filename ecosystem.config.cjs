/** PM2 config for production. Run from project root: pm2 start ecosystem.config.cjs */
module.exports = {
  apps: [
    {
      name: "agentserver",
      cwd: "/var/www/html/a-agent-base",
      script: "venv/bin/python",
      args: "-m uvicorn app.main:app --host 0.0.0.0 --port 5000",
      interpreter: "none",
      autorestart: true,
      max_restarts: 10,
      env: {
        PORT: "5000",
      },
    },
  ],
};
