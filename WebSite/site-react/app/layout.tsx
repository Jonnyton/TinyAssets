// Root layout — the shell. Imports the design system's full style layer first
// (tokens + base + vocabulary + component CSS), then site glue.
import "@tiny/design-system/styles.css";
import "./globals.css";

import type { Metadata } from "next";
import TopNav from "../components/TopNav";
import Footer from "../components/Footer";
import TinyBot from "../components/TinyBot";

export const metadata: Metadata = {
  metadataBase: new URL("https://tinyassets.io"),
  title: "TinyAssets — meet Tiny, the engine that turns chat into finished work",
  description:
    "TinyAssets is the open-source platform you connect to your chatbot over MCP. Tiny is the acting intelligence inside it: name a goal and he runs real multi-step work, with evidence-gated outcomes and workflows users can author, publish, copy, and remix.",
  openGraph: {
    siteName: "TinyAssets",
    type: "website",
    title: "TinyAssets — meet Tiny, the engine that turns chat into finished work",
    description:
      "Connect your chatbot to one URL. Name a goal. Tiny runs the real, multi-step work — and shows you live, verifiable evidence instead of marketing claims.",
    images: ["/og-image.png"],
    url: "https://tinyassets.io/",
  },
  twitter: {
    card: "summary_large_image",
    title: "TinyAssets — the engine that shows its work",
    description:
      "Live, verifiable state on every page: the same MCP endpoint you paste into your chatbot renders this site's numbers.",
    images: ["/og-image.png"],
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": "https://tinyassets.io/#org",
      name: "TinyAssets",
      alternateName: "Tiny",
      url: "https://tinyassets.io/",
      logo: "https://tinyassets.io/logo-mark.png",
      sameAs: ["https://github.com/Jonnyton/TinyAssets"],
    },
    {
      "@type": "WebSite",
      "@id": "https://tinyassets.io/#site",
      url: "https://tinyassets.io/",
      name: "TinyAssets",
      alternateName: "Tiny",
      description:
        "TinyAssets is the open-source platform behind Tiny, the personified intelligence users meet through MCP.",
      publisher: { "@id": "https://tinyassets.io/#org" },
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
        <TopNav />
        <main>{children}</main>
        <Footer />
        <TinyBot />
      </body>
    </html>
  );
}
