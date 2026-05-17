"use client";
import Link from "next/link";
import { useRef } from "react";
import { motion, useScroll, useTransform } from "framer-motion";
import { ArrowRight, Sparkles, Play } from "lucide-react";
import { useAuthStore } from "@/lib/auth";
import HeroPattern from "@/components/illustrations/HeroPattern";
import ChatPreviewFrame from "@/components/illustrations/ChatPreviewFrame";

export default function Hero() {
  const token = useAuthStore((s) => s.token);
  const ref = useRef<HTMLDivElement>(null);

  // Parallax suave: el screenshot del chat se mueve a 0.7x velocidad del
  // scroll y opacidad cae conforme entra la siguiente sección.
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });
  const previewY = useTransform(scrollYProgress, [0, 1], [0, -120]);
  const previewOpacity = useTransform(scrollYProgress, [0, 0.8], [1, 0.3]);

  return (
    <section
      ref={ref}
      className="relative pt-24 md:pt-32 pb-20 md:pb-28 overflow-hidden"
    >
      <HeroPattern />

      <div className="relative max-w-6xl mx-auto px-5 md:px-8 grid lg:grid-cols-[1.1fr_1fr] gap-10 lg:gap-16 items-center">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        >
          {/* Eyebrow */}
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-accent/30 bg-accent/10 text-accent-light text-xs font-medium mb-5">
            <Sparkles className="w-3 h-3" />
            Tu segundo cerebro, sin el caos
          </div>

          {/* H1 con negative letter-spacing al estilo Linear */}
          <h1 className="text-4xl sm:text-5xl md:text-6xl font-semibold leading-[1.05] tracking-[-0.025em] text-slate-100 mb-6">
            Guardas para después.{" "}
            <span className="text-accent-light">Y después nunca llega.</span>
          </h1>

          <p className="text-lg text-muted leading-relaxed max-w-xl mb-8">
            LinkAnvil convierte tus URLs guardadas, artículos, papers y
            tutoriales en una base de conocimiento navegable por
            significado. Pregúntale con tus palabras — te responde con
            tus fuentes.
          </p>

          <div className="flex flex-col sm:flex-row gap-3">
            <Link
              href={token ? "/chat" : "/login"}
              className="group inline-flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover text-white font-medium px-5 py-3 rounded-lg transition-colors"
            >
              {token ? "Abrir tu cerebro" : "Probar demo gratis"}
              <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
            </Link>
            <a
              href="#como-funciona"
              className="inline-flex items-center justify-center gap-2 bg-card hover:bg-surface border border-border text-slate-200 font-medium px-5 py-3 rounded-lg transition-colors"
            >
              <Play className="w-4 h-4" />
              Ver cómo funciona
            </a>
          </div>

          <p className="text-xs text-muted mt-5">
            Sin tarjeta. Credenciales demo visibles en la página de login.
          </p>
        </motion.div>

        {/* Preview del chat con parallax */}
        <motion.div
          style={{ y: previewY, opacity: previewOpacity }}
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.6, delay: 0.1, ease: "easeOut" }}
          className="relative"
        >
          <ChatPreviewFrame />
        </motion.div>
      </div>
    </section>
  );
}
