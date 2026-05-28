"use client";
import { motion } from "framer-motion";
import { ChefHat, Github, Newspaper, FlaskConical, ArrowUpRight } from "lucide-react";

// Ejemplos reales de URLs que un usuario puede pegar en LinkAnvil. Cada
// card muestra el origen, lo que el LLM extraería (temporal_class +
// valor_archivistico) y la decisión final del sistema. El objetivo:
// hacer tangible la clasificación que en la sección anterior se explica
// en abstracto.
type Example = {
  icon: typeof ChefHat;
  domain: string;
  url: string;
  title: string;
  temporal_class: "evergreen" | "referencia" | "evento";
  valor: "alto" | "medio" | "nulo";
  decision: string;
  decisionColor: string;
  rationale: string;
};

const EXAMPLES: Example[] = [
  {
    icon: ChefHat,
    domain: "lecturas.com",
    url: "https://www.lecturas.com/recetas/nutricion/menu-semanal-saludable-cocina-facil-ensaladas-pollo-tortillas-postres-para-disfrutar-sin-remordimientos_21973",
    title: "Menú semanal saludable — cocina fácil",
    temporal_class: "evergreen",
    valor: "medio",
    decision: "Activo permanente",
    decisionColor: "bg-emerald-700/30 text-emerald-300 border-emerald-600/40",
    rationale:
      "Las recetas no caducan. El chat te las recuerda cuando preguntas '¿qué cenamos hoy?' meses después.",
  },
  {
    icon: Github,
    domain: "github.com",
    url: "https://github.com/sylfG/linkanvil",
    title: "sylfG/linkanvil — repositorio público",
    temporal_class: "referencia",
    valor: "alto",
    decision: "Activo + auto-refresh",
    decisionColor: "bg-blue-700/30 text-blue-300 border-blue-600/40",
    rationale:
      "Los repos cambian. El cron nocturno re-vectoriza el README cuando detecta nuevos commits relevantes.",
  },
  {
    icon: FlaskConical,
    domain: "arxiv.org",
    url: "https://arxiv.org/abs/2310.06825",
    title: "Paper de arXiv — Mistral 7B",
    temporal_class: "referencia",
    valor: "alto",
    decision: "Activo (refutable)",
    decisionColor: "bg-purple-700/30 text-purple-300 border-purple-600/40",
    rationale:
      "Si un paper posterior refuta a éste, el colisionador semántico lo manda a cuarentena automáticamente.",
  },
  {
    icon: Newspaper,
    domain: "diaridegirona.cat",
    url: "https://www.diaridegirona.cat/girona/2024/03/18/expojove...",
    title: "Crónica ExpoJove 2024 — feria pasada",
    temporal_class: "referencia",
    valor: "medio",
    decision: "Cuarentena (evento pasado)",
    decisionColor: "bg-amber-700/30 text-amber-300 border-amber-600/40",
    rationale:
      "Fecha del path → evento ya celebrado. Te lo pone en cuarentena para que decidas si rescatarlo o archivarlo.",
  },
];

const CLASS_LABEL: Record<Example["temporal_class"], string> = {
  evergreen: "evergreen",
  referencia: "referencia",
  evento: "evento",
};

export default function RealExamples() {
  return (
    <section
      id="ejemplos"
      className="py-20 md:py-28 border-t border-border/50"
    >
      <div className="max-w-6xl mx-auto px-5 md:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.5 }}
          className="max-w-2xl mb-10"
        >
          <div className="text-xs uppercase tracking-widest text-accent-light font-medium mb-3">
            Ejemplos reales
          </div>
          <h2 className="text-3xl md:text-4xl font-semibold leading-tight tracking-[-0.02em] text-slate-100 mb-3">
            URLs cualquiera, decisiones que tienen sentido.
          </h2>
          <p className="text-base text-muted leading-relaxed">
            Estos son enlaces que el sistema procesa hoy mismo. Cada uno
            entra por el mismo pipeline: el LLM lee la página, clasifica
            su naturaleza temporal y aplica la política que tú
            configuraste.
          </p>
        </motion.div>

        <div className="grid md:grid-cols-2 gap-4">
          {EXAMPLES.map((ex, i) => {
            const Icon = ex.icon;
            return (
              <motion.a
                key={ex.url}
                href={ex.url}
                target="_blank"
                rel="noopener noreferrer"
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ duration: 0.4, delay: i * 0.06 }}
                whileHover={{ y: -3 }}
                className="block bg-card border border-border rounded-2xl p-5 hover:border-accent/40 transition-colors group"
              >
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-lg bg-surface border border-border flex items-center justify-center flex-shrink-0">
                    <Icon className="w-5 h-5 text-accent-light" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 text-[11px] text-muted mb-1">
                      <span className="truncate">{ex.domain}</span>
                      <ArrowUpRight className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                    <h3 className="text-sm font-semibold text-slate-100 mb-3 tracking-[-0.005em] line-clamp-2">
                      {ex.title}
                    </h3>

                    {/* Chips de clasificación */}
                    <div className="flex flex-wrap items-center gap-1.5 mb-3">
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-bg/50 border border-border/60 text-slate-300">
                        temporal_class={CLASS_LABEL[ex.temporal_class]}
                      </span>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-bg/50 border border-border/60 text-slate-300">
                        valor={ex.valor}
                      </span>
                    </div>

                    {/* Decisión final */}
                    <div
                      className={`inline-flex items-center gap-1.5 text-[11px] font-medium px-2 py-1 rounded-md border ${ex.decisionColor} mb-2`}
                    >
                      {ex.decision}
                    </div>

                    <p className="text-xs text-muted leading-relaxed">
                      {ex.rationale}
                    </p>
                  </div>
                </div>
              </motion.a>
            );
          })}
        </div>
      </div>
    </section>
  );
}
