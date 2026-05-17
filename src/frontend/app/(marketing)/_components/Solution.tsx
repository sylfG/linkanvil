"use client";
import { motion } from "framer-motion";
import { Brain, Archive, MessageSquare } from "lucide-react";

const pillars = [
  {
    icon: Brain,
    title: "Clasificación inteligente",
    desc: "Un LLM analiza cada URL y la etiqueta: evento con fecha, referencia descriptiva o evergreen. Tú decides qué hacer con el contenido pasado.",
  },
  {
    icon: Archive,
    title: "Archivo histórico opcional",
    desc: "Lo que ya no es accionable no se borra: se archiva. Sigue siendo recuperable en el chat con un toggle. Cero pérdida de información valiosa.",
  },
  {
    icon: MessageSquare,
    title: "Chat con tus fuentes",
    desc: "Pregunta con tus palabras. El chat recupera fragmentos relevantes de tu base de conocimiento, te responde, y cita las URLs exactas.",
  },
];

export default function Solution() {
  return (
    <section className="py-20 md:py-28">
      <div className="max-w-6xl mx-auto px-5 md:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.5 }}
          className="max-w-3xl"
        >
          <div className="text-xs uppercase tracking-widest text-accent-light font-medium mb-3">
            La solución
          </div>
          <h2 className="text-3xl md:text-4xl font-semibold leading-tight tracking-[-0.02em] text-slate-100 mb-4">
            LinkAnvil entiende lo que guardas y te lo devuelve cuando lo
            necesitas.
          </h2>
          <p className="text-muted text-base md:text-lg leading-relaxed">
            Tres pilares que convierten URLs sueltas en conocimiento útil.
          </p>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-5 mt-12">
          {pillars.map((p, i) => {
            const Icon = p.icon;
            return (
              <motion.div
                key={p.title}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-50px" }}
                transition={{ duration: 0.5, delay: i * 0.1 }}
                whileHover={{ y: -4 }}
                className="bg-card border border-border rounded-2xl p-6 transition-colors hover:border-accent/30"
              >
                <div className="w-10 h-10 rounded-lg bg-accent/15 border border-accent/30 flex items-center justify-center mb-4">
                  <Icon className="w-5 h-5 text-accent-light" />
                </div>
                <h3 className="font-semibold text-slate-100 mb-2">{p.title}</h3>
                <p className="text-sm text-muted leading-relaxed">{p.desc}</p>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
