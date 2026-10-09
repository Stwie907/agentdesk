import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/user-memories": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/agents": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/executions": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/memories": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/conversations": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
  },
});
