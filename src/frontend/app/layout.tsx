import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LinkAnvil — Segundo Cerebro",
  description: "Tu base de conocimiento personal impulsada por IA",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className="bg-bg text-slate-100 antialiased">{children}</body>
    </html>
  );
}
