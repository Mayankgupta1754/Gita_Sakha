import type { Metadata } from "next";
import { Cormorant_Garamond, Noto_Serif_Devanagari, Outfit } from "next/font/google";
import "./globals.css";

const display = Cormorant_Garamond({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-display",
});

const sans = Outfit({
  subsets: ["latin"],
  variable: "--font-sans",
});

const devanagari = Noto_Serif_Devanagari({
  subsets: ["devanagari"],
  weight: ["500", "600"],
  variable: "--font-deva",
});

export const metadata: Metadata = {
  title: "Gita Sakha — Talk with Lord Krishna",
  description: "Talk with Lord Krishna. Guidance drawn from the Bhagavad Gita.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${display.variable} ${sans.variable} ${devanagari.variable}`}>{children}</body>
    </html>
  );
}
