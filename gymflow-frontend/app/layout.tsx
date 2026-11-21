import type { Metadata, Viewport } from "next";
import { Inter, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });
const display = Plus_Jakarta_Sans({ subsets: ["latin"], weight: ["600", "700", "800"], variable: "--font-display" });

const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME || "GymFlow";

export const metadata: Metadata = {
  title: `${APP_NAME} – Gym software that pays for itself`,
  description: "Collect every fee on time, renew more members and turn more enquiries into joins – all over WhatsApp.",
  applicationName: APP_NAME,
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = { themeColor: "#D9480F", width: "device-width", initialScale: 1 };

// Applies a saved dark/light choice before paint so the page never flashes the wrong theme.
const THEME_SCRIPT = `try{var t=localStorage.getItem("gf-theme");if(t==="dark"||t==="light")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${display.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
