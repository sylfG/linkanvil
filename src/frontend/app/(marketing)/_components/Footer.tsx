import Link from "next/link";
import { Brain, Github } from "lucide-react";

export default function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-border/50 py-12 md:py-16 bg-surface/30">
      <div className="max-w-6xl mx-auto px-5 md:px-8">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-10">
          {/* Brand */}
          <div className="col-span-2 md:col-span-1">
            <Link href="/" className="flex items-center gap-2 mb-3">
              <div className="w-8 h-8 rounded-lg bg-accent/20 flex items-center justify-center">
                <Brain className="w-4 h-4 text-accent-light" />
              </div>
              <span className="font-semibold text-sm text-slate-100">
                LinkAnvil
              </span>
            </Link>
            <p className="text-xs text-muted leading-relaxed max-w-[220px]">
              Tu segundo cerebro autónomo. Auto-hospedado, privado y
              transparente.
            </p>
          </div>

          {/* Producto */}
          <div>
            <h3 className="text-xs font-semibold text-slate-100 uppercase tracking-wider mb-3">
              Producto
            </h3>
            <ul className="space-y-2 text-sm">
              <li>
                <Link
                  href="/login"
                  className="text-muted hover:text-slate-200 transition-colors"
                >
                  Iniciar sesión
                </Link>
              </li>
              <li>
                <Link
                  href="/register"
                  className="text-muted hover:text-slate-200 transition-colors"
                >
                  Crear cuenta
                </Link>
              </li>
              <li>
                <Link
                  href="/login"
                  className="text-muted hover:text-slate-200 transition-colors"
                >
                  Iniciar sesión
                </Link>
              </li>
            </ul>
          </div>

          {/* Recursos */}
          <div>
            <h3 className="text-xs font-semibold text-slate-100 uppercase tracking-wider mb-3">
              Recursos
            </h3>
            <ul className="space-y-2 text-sm">
              <li>
                <a
                  href="https://github.com/sylfG/linkanvil"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-muted hover:text-slate-200 transition-colors inline-flex items-center gap-1.5"
                >
                  <Github className="w-3.5 h-3.5" />
                  Código fuente
                </a>
              </li>
              <li>
                <a
                  href="#como-funciona"
                  className="text-muted hover:text-slate-200 transition-colors"
                >
                  Cómo funciona
                </a>
              </li>
              <li>
                <a
                  href="#faq"
                  className="text-muted hover:text-slate-200 transition-colors"
                >
                  Preguntas frecuentes
                </a>
              </li>
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h3 className="text-xs font-semibold text-slate-100 uppercase tracking-wider mb-3">
              Legal
            </h3>
            <ul className="space-y-2 text-sm">
              <li>
                <span className="text-muted">Self-hosted</span>
              </li>
              <li>
                <span className="text-muted">Datos en tu infra</span>
              </li>
              <li>
                <span className="text-muted">Open source</span>
              </li>
            </ul>
          </div>
        </div>

        <div className="pt-8 border-t border-border/30 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-muted">
          <p>© {year} LinkAnvil. Made for minds that save too much.</p>
          <p className="font-mono">v0.1</p>
        </div>
      </div>
    </footer>
  );
}
