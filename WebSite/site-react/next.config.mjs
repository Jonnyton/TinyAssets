/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export — matches the current GH Pages deploy of the Svelte site.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  // The design system ships ESM dist; let Next transpile it.
  transpilePackages: ["@tiny/design-system"],
};

export default nextConfig;
