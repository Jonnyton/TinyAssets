import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    port: 5173,
    strictPort: false,
    hmr: {
      // Show syntax/runtime errors as a browser overlay so Jonathan sees
      // failures without checking the terminal.
      overlay: true
    },
    watch: {
      // chokidar defaults work on Windows + the FUSE-mount writes Cowork
      // does. Polling is the slow fallback if HMR ever mysteriously stops.
      // Leave commented unless we see actual stalls.
      // usePolling: true,
      // interval: 300
    },
    // Proxy /mcp-live → tinyassets.io/mcp in dev so the browser can
    // talk to the MCP without CORS. In prod, /wiki and /graph live on
    // tinyassets.io directly so /mcp-live → /mcp via worker config.
    proxy: {
      '/mcp-live': {
        target: 'https://tinyassets.io',
        changeOrigin: true,
        secure: true,
        rewrite: (path) => path.replace(/^\/mcp-live/, '/mcp')
      }
    }
  }
});
