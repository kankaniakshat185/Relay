import type { Metadata } from "next";
import { Bodoni_Moda, Geist, Geist_Mono } from "next/font/google";
import Script from "next/script";
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
      {/* Runs before hydration so a stored theme choice applies before
       * first paint — without this, a page load would briefly show the
       * system-matched theme (from globals.css's `prefers-color-scheme`
       * block) and then flash to the user's stored override. */}
      <Script id="theme-init" strategy="beforeInteractive">
        {`(function(){try{var t=localStorage.getItem("relay-theme");if(t==="light"||t==="dark"){document.documentElement.dataset.theme=t;}}catch(e){}})();`}
      </Script>
    </html>
  );
}
