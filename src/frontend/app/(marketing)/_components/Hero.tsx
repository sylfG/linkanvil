"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, useScroll, useTransform, AnimatePresence } from "framer-motion";
import { ArrowRight, Sparkles, Play, X, Loader2 } from "lucide-react";
import { useAuthStore } from "@/lib/auth";
import { startDemoSession } from "@/lib/demo";
import HeroPattern from "@/components/illustrations/HeroPattern";
import ChatPreviewFrame from "@/components/illustrations/ChatPreviewFrame";

// Embed del vídeo de presentación en YouTube. Usamos youtube-nocookie
// (privacy-enhanced) para no fijar cookies de tracking hasta que el
// usuario pulse play. autoplay=1 al cargar el modal porque el usuario
// ya hizo click explícito en el botón "Ver demo".
const DEMO_VIDEO_ID = "MVeKcTZOXS8";
const DEMO_VIDEO_EMBED = `https://www.youtube-nocookie.com/embed/${DEMO_VIDEO_ID}?autoplay=1&rel=0&modestbranding=1`;
const DEMO_VIDEO_WATCH = `https://youtu.be/${DEMO_VIDEO_ID}`;

export default function Hero() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const ref = useRef<HTMLDivElement>(null);
  const [videoOpen, setVideoOpen] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);

  async function handleDemoClick() {
    setDemoError(null);
    setDemoLoading(true);
    try {
      await startDemoSession();
      router.push("/demo");
    } catch (err: any) {
      setDemoError(err?.message ?? "No se pudo iniciar la sesión demo.");
    } finally {
      setDemoLoading(false);
    }
  }

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
            {/* Slice 6 — CTA primaria: arranca una sesión demo
                efímera (TTL 15min) llamando a POST /auth/demo-start
                directamente. Sin password, sin formulario, sin
                credenciales visibles. Redirige a /demo al terminar. */}
            {token ? (
              <Link
                href="/chat"
                className="group inline-flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover text-white font-medium px-5 py-3 rounded-lg transition-colors"
              >
                Abrir tu cerebro
                <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
              </Link>
            ) : (
              <button
                onClick={handleDemoClick}
                disabled={demoLoading}
                className="group inline-flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-60 disabled:cursor-not-allowed text-white font-medium px-5 py-3 rounded-lg transition-colors"
              >
                {demoLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Sparkles className="w-4 h-4" />
                )}
                {demoLoading ? "Preparando demo..." : "Probar el demo gratis"}
              </button>
            )}
            <button
              onClick={() => setVideoOpen(true)}
              className="group inline-flex items-center justify-center gap-2 bg-card hover:bg-surface border border-border text-slate-200 font-medium px-5 py-3 rounded-lg transition-colors"
            >
              <Play className="w-4 h-4" />
              Ver cómo funciona
            </button>
          </div>

          {demoError && (
            <p className="text-xs text-red-300 mt-3" role="alert">
              {demoError}
            </p>
          )}

          <p className="text-xs text-muted mt-5">
            Sin tarjeta. Demo público con 15 min de sesión y datos sembrados.
            {" "}
            <Link href="/login" className="text-accent-light/80 hover:underline">
              ¿Ya tienes cuenta?
            </Link>
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

      {/* Modal de vídeo: iframe de YouTube cargado bajo demanda (sólo
          cuando el usuario pulsa Play). Cerrable con ESC, click en
          el backdrop o en la X. */}
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
          <iframe
            src={DEMO_VIDEO_EMBED}
            title="LinkAnvil — vídeo de presentación"
            className="absolute inset-0 w-full h-full"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            referrerPolicy="strict-origin-when-cross-origin"
            allowFullScreen
          />
          <noscript>
            <div className="absolute inset-0 flex items-center justify-center px-6 text-center bg-black/80">
              <p className="text-sm text-muted">
                Necesitas JavaScript para ver el vídeo embebido.{" "}
                <a
                  href={DEMO_VIDEO_WATCH}
                  className="text-accent-light hover:underline"
                >
                  Ábrelo en YouTube
                </a>
                .
              </p>
            </div>
          </noscript>
        </div>
        <div className="px-5 py-3 border-t border-border bg-bg/40 text-xs text-muted flex items-center justify-between gap-4">
          <span>
            ¿Sin sonido? Activa los altavoces.
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
