"use client";
import { motion } from "framer-motion";
import { Moon, Clock, ShieldCheck, Brain, ArrowRight } from "lucide-react";

// Sección que explica cómo el cron nocturno + el LLM mantienen la KB
// "viva" sin intervención del usuario. Encaja entre Features (qué hace)
// y UseCases (quién lo usa), porque resuelve una pregunta clave: "vale,
// ¿y qué pasa con lo que guardé hace 6 meses?".
const STEPS = [
  {
    icon: Clock,
    title: "03:00 UTC — el cron despierta",
    body: "Mientras duermes, LinkAnvil escanea tu KB en busca de URLs que hayan llegado a su fecha de caducidad o cuyo `fecha_evento` ya pasó.",
  },
  {
    icon: Brain,
    title: "El LLM re-evalúa cada candidato",
    body: "Vuelve a clasificar `temporal_class` y `valor_archivistico`. Si el contenido sigue siendo útil, lo deja activo; si no, lo propone para archivo histórico o cuarentena.",
  },
  {
    icon: ShieldCheck,
    title: "Tu policy decide el destino",
    body: "Según tu preset (Estricto / Equilibrado / Permisivo) el recurso pasa a `cuarentena` (espera tu visto bueno) o directo a archivo. Nada se borra nunca sin que tú lo apruebes.",
  },
];

export default function NightlyAudit() {
  return (
    <section
      id="auditoria"
      className="relative py-20 md:py-28 border-t border-border/50 overflow-hidden"
    >
      {/* Glow nocturno tenue al fondo — referencia visual al "mientras
          duermes". No-op en prefers-reduced-motion porque es estático. */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-32 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-accent/10 rounded-full blur-3xl opacity-40" />
      </div>

      <div className="relative max-w-6xl mx-auto px-5 md:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.5 }}
          className="max-w-2xl mb-12"
        >
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-accent/30 bg-accent/10 text-accent-light text-xs font-medium mb-4">
            <Moon className="w-3 h-3" />
            Auditoría nocturna
          </div>
          <h2 className="text-3xl md:text-4xl font-semibold leading-tight tracking-[-0.02em] text-slate-100 mb-4">
            Tu cerebro no envejece.{" "}
            <span className="text-accent-light">Cada noche se revisa solo.</span>
          </h2>
          <p className="text-base md:text-lg text-muted leading-relaxed">
            Una IA pasa por tus enlaces guardados todas las noches y
            comprueba si siguen siendo relevantes. Detecta artículos que
            envejecen mal, eventos que ya pasaron y referencias que se
            quedaron obsoletas — y propone qué hacer con cada uno según
            las reglas que tú definas.
          </p>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-5">
          {STEPS.map((step, i) => {
            const Icon = step.icon;
            return (
              <motion.article
                key={step.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-80px" }}
                transition={{ duration: 0.45, delay: i * 0.08 }}
                whileHover={{ y: -4 }}
                className="relative bg-card border border-border rounded-2xl p-6 group"
              >
                <div className="absolute top-4 right-5 text-[11px] font-mono text-muted/60">
                  0{i + 1}
                </div>
                <div className="w-10 h-10 rounded-lg bg-accent/15 border border-accent/20 flex items-center justify-center mb-4">
                  <Icon className="w-5 h-5 text-accent-light" />
                </div>
                <h3 className="text-base font-semibold text-slate-100 mb-2 tracking-[-0.01em]">
                  {step.title}
                </h3>
                <p className="text-sm text-muted leading-relaxed">{step.body}</p>
              </motion.article>
            );
          })}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.4, delay: 0.2 }}
          className="mt-8 flex flex-col sm:flex-row items-start sm:items-center gap-3 sm:gap-5 text-xs text-muted bg-bg/40 border border-border/60 rounded-xl px-5 py-4"
        >
          <span className="inline-flex items-center gap-2 text-slate-300 font-medium">
            <ArrowRight className="w-3.5 h-3.5 text-accent-light" />
            Resultado:
          </span>
          <span>
            La próxima vez que abras el chat, tu KB ya está limpia. No
            cita nada caducado, no recomienda papers refutados, no te
            sugiere ofertas que vencieron.
          </span>
        </motion.div>
      </div>
    </section>
  );
}
