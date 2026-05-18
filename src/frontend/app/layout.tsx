import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LinkAnvil — Segundo Cerebro",
  description: "Tu base de conocimiento personal impulsada por IA",
  // Next.js detecta automáticamente app/icon.png como favicon, pero
  // declaramos también la metadata explícita para que SEO y previews
  // (Open Graph, redes sociales) usen el mismo asset que la pestaña
  // del navegador. logo-dark.png es la variante para fondos oscuros.
  icons: {
    icon: [
      { url: "/icon.png", type: "image/png" },
      { url: "/logo-dark.png", type: "image/png", sizes: "586x586" },
    ],
    apple: "/icon.png",
  },
  openGraph: {
    images: ["/logo-dark.png"],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className="bg-bg text-slate-100 antialiased">{children}</body>
    </html>
  );
}
