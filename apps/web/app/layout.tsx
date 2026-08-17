import type { Metadata } from "next";
import { Bodoni_Moda, Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// The one editorial display serif the whole system is built around — see
// docs/decisions/0003-frontend-visual-redesign.md. Variable weight so
// oversized headlines (RELAY at 200px+) can carry real bold weight, not
// just a scaled-up regular cut.
const displaySerif = Bodoni_Moda({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "Relay",
  description: "A shared context engine across GitHub, Slack, and Jira.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${displaySerif.variable} h-full antialiased`}
    >
      <body className="bg-paper text-ink flex min-h-full flex-col">{children}</body>
    </html>
  );
}
