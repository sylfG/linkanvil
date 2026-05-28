"use client";
import { motion } from "framer-motion";
import { Link2, ShieldCheck, MessageSquare } from "lucide-react";
import PipelineConnector from "@/components/illustrations/PipelineConnector";

const steps = [
  {
    n: "01",
    icon: Link2,
    title: "Pega cualquier URL",
    desc: "Desde la web, la extensión o tu bot personal de Telegram. LinkAnvil scrappea el contenido, lo limpia y lo prepara para análisis.",
    mock: (
      <div className="space-y-2 text-xs">
        <div className="bg-surface border border-border rounded-lg px-3 py-2 font-mono text-muted truncate">
          https://aemetblog.es/2020/09/…
        </div>
        <div className="text-[10px] text-accent-light">
          ✓ Aceptado y encolado
        </div>
      </div>
    ),
  },
  {
    n: "02",
    icon: ShieldCheck,
    title: "La IA clasifica con tu policy",
    desc: "Un LLM extrae clase temporal y valor archivístico. Tu configuración decide: activo en KB, cuarentena para revisión, o archivo histórico.",
    mock: (
      <div className="space-y-1.5 text-xs">
        <div className="flex items-center justify-between bg-surface border border-border rounded-md px-2.5 py-1.5">
          <span className="text-muted">Evento + valor alto</span>
          <span className="text-accent-light font-medium">→ Archivo</span>
        </div>
        <div className="flex items-center justify-between bg-surface border border-border rounded-md px-2.5 py-1.5">
          <span className="text-muted">Referencia + valor medio</span>
          <span className="text-amber-300 font-medium">→ Cuarentena</span>
        </div>
        <div className="flex items-center justify-between bg-surface border border-border rounded-md px-2.5 py-1.5">
          <span className="text-muted">Evergreen</span>
          <span className="text-green-300 font-medium">→ Activo</span>
        </div>
      </div>
    ),
  },
  {
    n: "03",
    icon: MessageSquare,
    title: "Pregunta al chat",
    desc: "El chat recupera fragmentos relevantes de tu base vectorial y compone una respuesta citando las fuentes. Activa 'Archivo ON' para buscar también en el histórico.",
    mock: (
      <div className="space-y-2 text-xs">
        <div className="bg-accent/10 border border-accent/30 rounded-lg rounded-tr-sm px-3 py-1.5 text-slate-100">
          ¿Qué dice AEMET del 2020?
        </div>
        <div className="bg-surface border border-border rounded-lg rounded-tl-sm px-3 py-1.5 text-muted">
          Según tu archivo, fue el 2º verano…
        </div>
      </div>
    ),
  },
];

export default function HowItWorks() {
  return (
    <section
      id="como-funciona"
      className="py-20 md:py-28 border-t border-border/50"
    >
      <div className="max-w-6xl mx-auto px-5 md:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.5 }}
          className="text-center max-w-2xl mx-auto mb-14"
        >
          <div className="text-xs uppercase tracking-widest text-accent-light font-medium mb-3">
            Cómo funciona
          </div>
          <h2 className="text-3xl md:text-4xl font-semibold leading-tight tracking-[-0.02em] text-slate-100">
            Tres pasos. Cero curva de aprendizaje.
          </h2>
        </motion.div>

        <div className="relative grid md:grid-cols-3 gap-6">
          <PipelineConnector />
          {steps.map((s, i) => {
            const Icon = s.icon;
            return (
              <motion.div
                key={s.n}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-50px" }}
                transition={{ duration: 0.5, delay: i * 0.15 }}
                className="relative bg-card border border-border rounded-2xl p-6"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="w-10 h-10 rounded-lg bg-accent/15 border border-accent/30 flex items-center justify-center">
                    <Icon className="w-5 h-5 text-accent-light" />
                  </div>
                  <span className="font-mono text-xs text-muted">{s.n}</span>
                </div>
                <h3 className="font-semibold text-slate-100 mb-2">{s.title}</h3>
                <p className="text-sm text-muted leading-relaxed mb-4">
                  {s.desc}
                </p>
                <div className="bg-surface/40 border border-border/60 rounded-lg p-3">
                  {s.mock}
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
