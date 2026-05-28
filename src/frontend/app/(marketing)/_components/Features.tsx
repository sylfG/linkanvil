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

const features = [
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

export default function Features() {
  return (
    <section className="py-20 md:py-28">
      <div className="max-w-6xl mx-auto px-5 md:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.5 }}
          className="text-center max-w-2xl mx-auto mb-14"
        >
          <div className="text-xs uppercase tracking-widest text-accent-light font-medium mb-3">
            Lo que obtienes
          </div>
          <h2 className="text-3xl md:text-4xl font-semibold leading-tight tracking-[-0.02em] text-slate-100">
            Diseñado para mentes que guardan demasiado.
          </h2>
        </motion.div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {features.map((f, i) => {
            const Icon = f.icon;
            return (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-50px" }}
                transition={{ duration: 0.4, delay: (i % 3) * 0.08 }}
                whileHover={{ y: -3 }}
                className="bg-card border border-border rounded-xl p-5 transition-colors hover:border-accent/30"
              >
                <div className="w-9 h-9 rounded-lg bg-surface border border-border flex items-center justify-center mb-3">
                  <Icon className="w-4 h-4 text-accent-light" />
                </div>
                <h3 className="font-medium text-slate-100 mb-1.5 text-sm">
                  {f.title}
                </h3>
                <p className="text-sm text-muted leading-relaxed">{f.desc}</p>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
