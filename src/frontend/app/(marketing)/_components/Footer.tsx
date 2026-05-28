import Link from "next/link";
import { Brain, Github, Lock, Server, Heart } from "lucide-react";

// Enlaces externos a la documentacion publicada en GitHub Pages.
// Solo apuntamos a paginas con valor para el visitante de la landing
// (que aun no es usuario). Los anchors internos a las secciones de la
// propia landing (#como-funciona, #faq, etc.) viven en el Nav y NO se
// duplican aqui.
const DOCS_BASE = "https://sylfg.github.io/linkanvil";
const REPO = "https://github.com/sylfG/linkanvil";

const DOCS_LINKS = [
  { label: "Resumen del proyecto", href: `${DOCS_BASE}/0-resumen` },
  { label: "Arquitectura", href: `${DOCS_BASE}/4-arquitectura` },
  { label: "Ciclo de vida", href: `${DOCS_BASE}/7-lifecycle` },
  { label: "Guía de seguridad", href: `${DOCS_BASE}/11-Seguridad` },
  {
    label: "Extracción de requisitos",
    href: `${DOCS_BASE}/Extractor_de_Requisitos/`,
  },
];

const REPO_LINKS = [
  { label: "Código fuente", href: REPO, icon: Github },
  { label: "Reportar un bug", href: `${REPO}/issues/new` },
  { label: "Releases", href: `${REPO}/releases` },
];

// Atributos descriptivos del producto. Antes eran <span> en una columna
// "Legal" sin enlaces — la inflaba sin aportar. Ahora viven como pills
// al lado del copyright donde de verdad cumplen su funcion: dar contexto
// rapido del producto sin pretender ser navegables.
const PRODUCT_TRAITS = [
  { label: "Self-hosted", icon: Server },
  { label: "Open source", icon: Heart },
  { label: "Tu infra, tus datos", icon: Lock },
];

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

          {/* Producto: solo lo que NO esta en el navbar.
              "Iniciar sesion" ya esta en el nav -> no duplicado aqui. */}
          <div>
            <h3 className="text-xs font-semibold text-slate-100 uppercase tracking-wider mb-3">
              Producto
            </h3>
            <ul className="space-y-2 text-sm">
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
                  href="/#hero"
                  className="text-muted hover:text-slate-200 transition-colors"
                >
                  Probar el demo
                </Link>
              </li>
            </ul>
          </div>

          {/* Documentacion: enlaces a VitePress publicado en GitHub
              Pages. Las secciones internas de la landing (#como-funciona,
              #faq) viven en el Nav, no se duplican. */}
          <div>
            <h3 className="text-xs font-semibold text-slate-100 uppercase tracking-wider mb-3">
              Documentación
            </h3>
            <ul className="space-y-2 text-sm">
              {DOCS_LINKS.map((l) => (
                <li key={l.href}>
                  <a
                    href={l.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-muted hover:text-slate-200 transition-colors"
                  >
                    {l.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          {/* Repositorio: GitHub y atajos de community.
              Sustituye a la antigua columna "Recursos" cuyos anchors
              ya viven en el Nav. */}
          <div>
            <h3 className="text-xs font-semibold text-slate-100 uppercase tracking-wider mb-3">
              Repositorio
            </h3>
            <ul className="space-y-2 text-sm">
              {REPO_LINKS.map((l) => {
                const Icon = l.icon;
                return (
                  <li key={l.href}>
                    <a
                      href={l.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-muted hover:text-slate-200 transition-colors inline-flex items-center gap-1.5"
                    >
                      {Icon && <Icon className="w-3.5 h-3.5" />}
                      {l.label}
                    </a>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>

        {/* Pills descriptivos + copyright */}
        <div className="pt-8 border-t border-border/30 flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            {PRODUCT_TRAITS.map((t) => {
              const Icon = t.icon;
              return (
                <span
                  key={t.label}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-card border border-border text-[11px] text-muted"
                >
                  <Icon className="w-3 h-3 text-accent-light" />
                  {t.label}
                </span>
              );
            })}
          </div>
          <div className="flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-muted">
            <p>© {year} LinkAnvil. Made for minds that save too much.</p>
            <p className="font-mono">v0.1</p>
          </div>
        </div>
      </div>
    </footer>
  );
}
