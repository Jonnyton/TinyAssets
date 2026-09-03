// Root layout — the shell. Imports the design system's full style layer first
// (tokens + base + vocabulary + component CSS), then site glue.
import "@tiny/design-system/styles.css";
import "./globals.css";

import type { Metadata } from "next";
import TopNav from "../components/TopNav";
import Footer from "../components/Footer";
import { SITE } from "../lib/site";

const TITLE = "TinyAssets — your own AI universe";
const DESCRIPTION =
  "A cloud agent of your own. It runs on the Claude or ChatGPT subscription you already pay for, connects to any platform, builds any automation from a few primitives, learns you as it goes, and keeps working after you close the tab.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE.origin),
  title: { default: TITLE, template: "%s — TinyAssets" },
  description: DESCRIPTION,
  manifest: "/site.webmanifest",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "16x16 32x32 48x48" },
      { url: "/icon.svg", type: "image/svg+xml" },
    ],
    apple: "/apple-touch-icon.png",
  },
  openGraph: {
    siteName: "TinyAssets",
    type: "website",
    title: TITLE,
    description: DESCRIPTION,
    images: ["/og-image.png"],
    url: SITE.origin + "/",
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
    images: ["/og-image.png"],
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${SITE.origin}/#org`,
      name: "TinyAssets",
      url: `${SITE.origin}/`,
      logo: `${SITE.origin}/logo-mark.png`,
      sameAs: [SITE.repo],
    },
    {
      "@type": "WebSite",
      "@id": `${SITE.origin}/#site`,
      url: `${SITE.origin}/`,
      name: "TinyAssets",
      description: DESCRIPTION,
      publisher: { "@id": `${SITE.origin}/#org` },
    },
    {
      "@type": "SoftwareApplication",
      "@id": `${SITE.origin}/#app`,
      name: "TinyAssets",
      applicationCategory: "ProductivityApplication",
      operatingSystem: "Web, Android, Windows, macOS, Linux",
      url: SITE.app,
      offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
      license: `${SITE.repo}/blob/main/LICENSE`,
    },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
        <a className="skip" href="#main">
          Skip to content
        </a>
        <TopNav />
        <main id="main">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
