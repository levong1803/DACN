import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: "127.0.0.1",
    open: true,
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${process.env.VITE_API_PORT || "8001"}`,
        changeOrigin: true,
      },
    },
  },
});
