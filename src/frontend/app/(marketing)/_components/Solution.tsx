"use client";
import { motion } from "framer-motion";
import {
  Clock,
  Archive,
  Lock,
  Bot,
  SlidersHorizontal,
  Zap,
} from "lucide-react";

// Sección "La solución". 6 pilares = la propuesta de valor canónica.
// Reemplaza la versión anterior de 3 pilares y absorbe el contenido
// de la antigua sección Features (que queda como archivo histórico
// en _components/Features.tsx sin importarse desde page.tsx).
const pillars = [
  {
    icon: Clock,
    title: "Clasificación temporal",
    desc: "Evento, referencia o evergreen. El LLM detecta la naturaleza temporal del contenido al ingestar.",
  },
  {
    icon: Archive,
    title: "Archivo histórico opt-in",
    desc: "Lo pasado con valor alto no se borra: se archiva. Sigue indexado para búsqueda semántica.",
  },
  {
    icon: Lock,
    title: "Tu cerebro es solo tuyo",
    desc: "Arquitectura multi-tenant con aislamiento estricto. Los datos de cada usuario son invisibles para el resto.",
  },
  {
    icon: Bot,
    title: "Bot de Telegram personal",
    desc: "Conecta tu propio bot y envía URLs desde el móvil. Llegan a tu KB en segundos.",
  },
  {
    icon: SlidersHorizontal,
    title: "Policy configurable",
    desc: "Una matriz de 6 celdas decide qué hacer con cada combinación clase × valor archivístico. 3 presets o ajuste fino.",
  },
  {
    icon: Zap,
    title: "RAG opt-in",
    desc: "El chat funciona con búsqueda contextual o sin ella. Tú decides cuándo el modelo debe consultar tu base.",
  },
];

export default function Solution() {
  return (
    <section className="py-20 md:py-28 border-t border-border/50">
      <div className="max-w-6xl mx-auto px-5 md:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.5 }}
          className="max-w-2xl mb-12"
        >
          <div className="text-xs uppercase tracking-widest text-accent-light font-medium mb-3">
            La solución
          </div>
          <h2 className="text-3xl md:text-4xl font-semibold leading-tight tracking-[-0.02em] text-slate-100 mb-3">
            Seis pilares que convierten URLs sueltas en conocimiento útil.
          </h2>
          <p className="text-base text-muted leading-relaxed">
            Cada uno resuelve un punto concreto del flujo: cómo entra
            el contenido, cómo se conserva, quién puede verlo y cómo
            se consulta.
          </p>
        </motion.div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {pillars.map((p, i) => {
            const Icon = p.icon;
            return (
              <motion.article
                key={p.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-50px" }}
                transition={{ duration: 0.4, delay: (i % 3) * 0.08 }}
                whileHover={{ y: -3 }}
                className="bg-card border border-border rounded-2xl p-6 transition-colors hover:border-accent/30"
              >
                <div className="w-10 h-10 rounded-lg bg-accent/15 border border-accent/20 flex items-center justify-center mb-4">
                  <Icon className="w-5 h-5 text-accent-light" />
                </div>
                <h3 className="text-base font-semibold text-slate-100 mb-2 tracking-[-0.01em]">
                  {p.title}
                </h3>
                <p className="text-sm text-muted leading-relaxed">{p.desc}</p>
              </motion.article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
