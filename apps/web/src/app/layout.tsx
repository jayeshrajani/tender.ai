import "./globals.css";
import "@fontsource-variable/bricolage-grotesque";

import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata, Viewport } from "next";

import { Providers } from "./providers";

export const metadata: Metadata = {
  title: { default: "TenderOS", template: "%s · TenderOS" },
  description: "Tender intelligence for Madhya Pradesh construction contractors.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f6fa" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0d14" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // next-themes sets the theme class before hydration.
    <html lang="en-IN" className={`${GeistSans.variable} ${GeistMono.variable}`} suppressHydrationWarning>
      <body className="min-h-dvh font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
