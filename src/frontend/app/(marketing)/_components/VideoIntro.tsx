"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import { Play } from "lucide-react";

// Vídeo de presentación general — embebido inline en la landing.
// Patrón "facade": al render inicial solo se monta un poster con un
// botón de play (sin red a YouTube → no impacta LCP ni cookies).
// Tras el primer click se monta el <iframe> de youtube-nocookie.com
// y el navegador empieza a reproducir.
const VIDEO_ID = "MVeKcTZOXS8";
const VIDEO_EMBED = `https://www.youtube-nocookie.com/embed/${VIDEO_ID}?autoplay=1&rel=0&modestbranding=1`;
const VIDEO_WATCH = `https://youtu.be/${VIDEO_ID}`;
const VIDEO_POSTER = `https://img.youtube.com/vi/${VIDEO_ID}/maxresdefault.jpg`;

export default function VideoIntro() {
  const [loaded, setLoaded] = useState(false);

  return (
    <section
      id="video"
      className="py-20 md:py-28 border-t border-border/50"
    >
      <div className="max-w-5xl mx-auto px-5 md:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.5 }}
          className="text-center mb-10"
        >
          <div className="text-xs uppercase tracking-widest text-accent-light font-medium mb-3">
            Video de presentación
          </div>
          <h2 className="text-3xl md:text-4xl font-semibold leading-tight tracking-[-0.02em] text-slate-100 mb-4">
            Mira LinkAnvil en acción.
          </h2>
          <p className="text-muted text-base md:text-lg max-w-2xl mx-auto leading-relaxed">
            Un recorrido por la arquitectura, el flujo de ingesta
            asíncrona y la demo pública del chat RAG.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true, margin: "-50px" }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="relative aspect-video w-full rounded-2xl overflow-hidden border border-border bg-black shadow-2xl shadow-accent/10"
        >
          {loaded ? (
            <iframe
              src={VIDEO_EMBED}
              title="LinkAnvil — vídeo de presentación"
              className="absolute inset-0 w-full h-full"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              referrerPolicy="strict-origin-when-cross-origin"
              allowFullScreen
            />
          ) : (
            <button
              type="button"
              onClick={() => setLoaded(true)}
              aria-label="Reproducir vídeo de presentación"
              className="group absolute inset-0 w-full h-full cursor-pointer"
            >
              {/* Poster de YouTube. img.youtube.com/vi/<id>/maxresdefault.jpg
                  es público y no fija cookies de tracking. */}
              <img
                src={VIDEO_POSTER}
                alt="Vista previa del vídeo de presentación de LinkAnvil"
                className="absolute inset-0 w-full h-full object-cover"
                loading="lazy"
                decoding="async"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/10 to-black/30 transition-colors group-hover:from-black/70" />
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="flex items-center justify-center w-20 h-20 md:w-24 md:h-24 rounded-full bg-accent text-white shadow-2xl shadow-accent/40 transition-transform group-hover:scale-110">
                  <Play className="w-9 h-9 md:w-11 md:h-11 fill-current ml-1" />
                </div>
              </div>
            </button>
          )}
          <noscript>
            <div className="absolute inset-0 flex items-center justify-center px-6 text-center bg-black/80">
              <p className="text-sm text-muted">
                Necesitas JavaScript para ver el vídeo.{" "}
                <a
                  href={VIDEO_WATCH}
                  className="text-accent-light hover:underline"
                >
                  Ábrelo en YouTube
                </a>
                .
              </p>
            </div>
          </noscript>
        </motion.div>

        <p className="text-center text-xs text-muted mt-5">
          ¿Prefieres verlo en YouTube?{" "}
          <a
            href={VIDEO_WATCH}
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent-light hover:underline"
          >
            youtu.be/{VIDEO_ID}
          </a>
        </p>
      </div>
    </section>
  );
}
