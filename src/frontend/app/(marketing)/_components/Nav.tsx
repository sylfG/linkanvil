"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Brain } from "lucide-react";
import { useAuthStore } from "@/lib/auth";

// Nav translúcido fijo. Solo se vuelve opaco al hacer scroll > 16px,
// efecto similar al de Linear/Vercel. La detección del token decide si
// mostrar "Iniciar sesión" o "Abrir tu cerebro".
export default function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 16);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <nav
      className={`fixed top-0 inset-x-0 z-50 h-16 flex items-center transition-all duration-300 ${
        scrolled
          ? "bg-bg/80 backdrop-blur-md border-b border-border"
          : "bg-transparent"
      }`}
    >
      <div className="max-w-6xl mx-auto w-full px-5 md:px-8 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 group">
          <div className="w-8 h-8 rounded-lg bg-accent/20 flex items-center justify-center group-hover:bg-accent/30 transition-colors">
            <Brain className="w-4 h-4 text-accent-light" />
          </div>
          <span className="font-semibold text-sm text-slate-100">LinkAnvil</span>
        </Link>

        <div className="hidden md:flex items-center gap-6 text-sm text-muted">
          <a href="#problema" className="hover:text-slate-200 transition-colors">
            El problema
          </a>
          <a href="#como-funciona" className="hover:text-slate-200 transition-colors">
            Cómo funciona
          </a>
          <a href="#casos" className="hover:text-slate-200 transition-colors">
            Casos
          </a>
          <a href="#faq" className="hover:text-slate-200 transition-colors">
            FAQ
          </a>
        </div>

        <div className="flex items-center gap-3">
          {token ? (
            <Link
              href="/chat"
              className="text-sm bg-accent hover:bg-accent-hover text-white px-4 py-2 rounded-lg transition-colors"
            >
              Abrir tu cerebro
            </Link>
          ) : (
            <>
              <Link
                href="/login"
                className="text-sm text-slate-300 hover:text-slate-100 transition-colors hidden sm:inline-block"
              >
                Iniciar sesión
              </Link>
              <Link
                href="/login"
                className="text-sm bg-accent hover:bg-accent-hover text-white px-4 py-2 rounded-lg transition-colors"
              >
                Probar demo
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
