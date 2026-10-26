import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import basicSsl from "@vitejs/plugin-basic-ssl";

// HTTPS=1 npm run dev serves over https (WebXR needs a secure origin).
export default defineConfig({
  plugins: [react(), tailwindcss(), ...(process.env.HTTPS === "1" ? [basicSsl()] : [])],
  server: {
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
