"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuthStore } from "@/lib/auth";
import Logo from "@/components/Logo";

// Nav translúcido fijo. Solo se vuelve opaco al hacer scroll > 16px,
// efecto similar al de Linear/Vercel. La detección del token decide si
// mostrar "Iniciar sesión" o "Abrir tu cerebro" — un único CTA en el
// nav (eliminamos la duplicidad "Iniciar sesión" + "Probar demo": apuntan
// al mismo /login, así que basta con un botón).
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
          <Logo size={32} className="rounded-md" priority />
          <span className="font-semibold text-sm text-slate-100">LinkAnvil</span>
        </Link>

        <div className="hidden md:flex items-center gap-6 text-sm text-muted">
          <a href="#problema" className="hover:text-slate-200 transition-colors">
            El problema
          </a>
          <a href="#como-funciona" className="hover:text-slate-200 transition-colors">
            Cómo funciona
          </a>
          <a href="#ejemplos" className="hover:text-slate-200 transition-colors">
            Ejemplos
          </a>
          <a href="#auditoria" className="hover:text-slate-200 transition-colors">
            Auditoría nocturna
          </a>
          <a href="#faq" className="hover:text-slate-200 transition-colors">
            FAQ
          </a>
        </div>

        <div className="flex items-center gap-2">
          {token ? (
            <Link
              href="/chat"
              className="text-sm bg-accent hover:bg-accent-hover text-white px-4 py-2 rounded-lg transition-colors"
            >
              Abrir tu cerebro
            </Link>
          ) : (
            <>
              {/* Login: link discreto a la izquierda. Demo: CTA principal. */}
              <Link
                href="/login"
                className="hidden sm:inline-block text-sm text-muted hover:text-slate-200 px-3 py-2 transition-colors"
              >
                Iniciar sesión
              </Link>
              <Link
                href="/?demo=1#hero"
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
