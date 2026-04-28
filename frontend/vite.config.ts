import { defineConfig, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = "http://localhost:8000";

function apiProxy(): ProxyOptions {
  return {
    target: apiTarget,
    changeOrigin: true,
    configure(proxy) {
      proxy.on("error", (_error, request, response) => {
        if (!response) {
          return;
        }

        if (!response.headersSent) {
          response.writeHead(502, { "Content-Type": "text/plain" });
        }

        response.end(`Roundup API proxy could not reach ${apiTarget} for ${request.url ?? "this request"}.`);
      });
    }
  };
}

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": apiProxy(),
      "/debug": apiProxy(),
      "/metrics": apiProxy(),
      "/health": apiProxy()
    }
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts"
  }
});
