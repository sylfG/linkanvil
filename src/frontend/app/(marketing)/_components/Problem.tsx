"use client";
import { motion } from "framer-motion";
import BookmarkGraveyard from "@/components/illustrations/BookmarkGraveyard";

export default function Problem() {
  return (
    <section id="problema" className="py-20 md:py-28 border-t border-border/50">
      <div className="max-w-6xl mx-auto px-5 md:px-8 grid lg:grid-cols-2 gap-10 lg:gap-16 items-center">
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.5 }}
        >
          <div className="text-xs uppercase tracking-widest text-accent-light font-medium mb-3">
            El problema
          </div>
          <h2 className="text-3xl md:text-4xl font-semibold leading-tight tracking-[-0.02em] text-slate-100 mb-5">
            Tu cerebro digital no es una biblioteca.{" "}
            <span className="text-muted">Es un cajón desastre.</span>
          </h2>
          <div className="space-y-4 text-muted text-base leading-relaxed">
            <p>
              Cada semana guardas decenas de URLs prometedoras: papers,
              tutoriales, hilos, anuncios de conferencias. Las archivas
              "para más tarde" — pero "más tarde" nunca llega. Cuando
              vuelves a necesitar ese dato concreto, no recuerdas dónde
              lo viste, ni qué palabras buscar.
            </p>
            <p>
              Las herramientas tradicionales tratan tus enlaces como
              archivos en una carpeta: estáticos, sin contexto, sin
              caducidad. <span className="text-slate-200">Lo que necesitas
              es un sistema que recuerde lo que tú olvidas.</span>
            </p>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.6, delay: 0.1 }}
        >
          <BookmarkGraveyard />
        </motion.div>
      </div>
    </section>
  );
}
