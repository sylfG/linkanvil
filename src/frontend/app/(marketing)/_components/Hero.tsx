"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { motion, useScroll, useTransform, AnimatePresence } from "framer-motion";
import { ArrowRight, Sparkles, Play, X } from "lucide-react";
import { useAuthStore } from "@/lib/auth";
import HeroPattern from "@/components/illustrations/HeroPattern";
import ChatPreviewFrame from "@/components/illustrations/ChatPreviewFrame";

// El vídeo de demostración. Cuando exista el asset definitivo, sustituir
// esta URL por /demo.mp4 (o un embed de YouTube/Vimeo). De momento
// dejamos el slot vacío para que el modal renderice "vídeo próximamente".
const DEMO_VIDEO_SRC = "/demo.mp4";

export default function Hero() {
  const token = useAuthStore((s) => s.token);
  const ref = useRef<HTMLDivElement>(null);
  const [videoOpen, setVideoOpen] = useState(false);

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
            {/* CTA primaria: abre el vídeo de demostración. Lo prominente
                ahora es ENTENDER la propuesta antes de probarla. */}
            <button
              onClick={() => setVideoOpen(true)}
              className="group inline-flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover text-white font-medium px-5 py-3 rounded-lg transition-colors"
            >
              <Play className="w-4 h-4" />
              Ver cómo funciona
            </button>
            {/* CTA secundaria: login (o /chat si ya hay sesión). */}
            <Link
              href={token ? "/chat" : "/login"}
              className="group inline-flex items-center justify-center gap-2 bg-card hover:bg-surface border border-border text-slate-200 font-medium px-5 py-3 rounded-lg transition-colors"
            >
              {token ? "Abrir tu cerebro" : "Iniciar sesión"}
              <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
            </Link>
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

      {/* Modal de vídeo. Si /demo.mp4 no existe todavía, el <video>
          mostrará el "poster" + mensaje "vídeo próximamente". Cerrable
          con ESC, click en el backdrop o en la X. */}
      <AnimatePresence>
        {videoOpen && <VideoModal onClose={() => setVideoOpen(false)} />}
      </AnimatePresence>
    </section>
  );
}

function VideoModal({ onClose }: { onClose: () => void }) {
  // ESC cierra el modal — accesibilidad básica.
  if (typeof window !== "undefined") {
    document.onkeydown = (e) => {
      if (e.key === "Escape") onClose();
    };
  }

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[60] bg-black/80 backdrop-blur-sm"
        onClick={onClose}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ duration: 0.2 }}
        className="fixed inset-4 md:inset-x-auto md:left-1/2 md:top-1/2 md:-translate-x-1/2 md:-translate-y-1/2 md:w-[min(96vw,1100px)] md:max-h-[88vh] z-[61] bg-card border border-border rounded-2xl overflow-hidden flex flex-col"
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2 text-sm text-slate-200">
            <Play className="w-4 h-4 text-accent-light" />
            Demostración de LinkAnvil
          </div>
          <button
            onClick={onClose}
            aria-label="Cerrar vídeo"
            className="p-1.5 rounded-lg hover:bg-white/10 text-muted hover:text-slate-200 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="relative bg-black aspect-video w-full">
          <video
            src={DEMO_VIDEO_SRC}
            controls
            playsInline
            preload="metadata"
            className="absolute inset-0 w-full h-full object-contain"
          >
            {/* Si el navegador no puede reproducirlo o el archivo no
                existe todavía, se muestra el fallback de abajo. */}
          </video>
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-center px-6">
            <noscript>
              <p className="text-sm text-muted">
                Necesitas JavaScript activado para ver el vídeo.
              </p>
            </noscript>
          </div>
        </div>
        <div className="px-5 py-3 border-t border-border bg-bg/40 text-xs text-muted flex items-center justify-between gap-4">
          <span>
            ¿Sin sonido? Activa los altavoces. Duración aproximada: 90s.
          </span>
          <Link
            href="/login"
            className="text-accent-light hover:underline whitespace-nowrap"
          >
            Iniciar sesión →
          </Link>
        </div>
      </motion.div>
    </>
  );
}
