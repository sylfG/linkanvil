"use client";
import { motion } from "framer-motion";
import { Send, Zap, Archive, Bot, User as UserIcon } from "lucide-react";

// Device frame estilizado mostrando el chat con RAG en acción. Es un
// mock (no screenshot real) — eso garantiza que la landing se vea
// perfecta sin assets binarios. Cuando exista un screenshot PNG real
// puedes sustituir este componente por <Image src="/screenshots/chat-rag.png"/>.
export default function ChatPreviewFrame() {
  return (
    <div className="relative">
      {/* Glow detrás del frame */}
      <div
        aria-hidden
        className="absolute -inset-8 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 60% 60% at 50% 50%, rgba(139, 92, 246, 0.25), transparent 70%)",
        }}
      />

      {/* Device frame */}
      <div className="relative bg-card border border-border rounded-2xl overflow-hidden shadow-2xl">
        {/* Title bar tipo macOS */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-surface/50">
          <div className="flex gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
            <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/60" />
            <div className="w-2.5 h-2.5 rounded-full bg-green-500/60" />
          </div>
          <div className="flex-1 text-center text-[11px] text-muted font-mono">
            linkanvil.app / chat
          </div>
        </div>

        {/* Toolbar del chat */}
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-surface/30">
          <span className="text-xs text-muted">cerebro-lite</span>
          <span className="flex items-center gap-1 text-xs bg-accent/20 border border-accent/40 text-accent-light px-2 py-0.5 rounded-md">
            <Zap className="w-2.5 h-2.5" />
            RAG ON
          </span>
          <span className="flex items-center gap-1 text-xs bg-amber-500/10 border border-amber-400/30 text-amber-300 px-2 py-0.5 rounded-md">
            <Archive className="w-2.5 h-2.5" />
            Archivo ON
          </span>
        </div>

        {/* Mensajes */}
        <div className="p-5 space-y-4 min-h-[280px]">
          <motion.div
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.4 }}
            className="flex gap-2 justify-end"
          >
            <div className="bg-accent/15 border border-accent/30 rounded-2xl rounded-tr-sm px-4 py-2.5 max-w-[80%]">
              <p className="text-sm text-slate-100">
                ¿Cómo fue el verano de 2020 según AEMET?
              </p>
            </div>
            <div className="w-7 h-7 rounded-full bg-surface border border-border flex items-center justify-center flex-shrink-0">
              <UserIcon className="w-3.5 h-3.5 text-muted" />
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.8 }}
            className="flex gap-2"
          >
            <div className="w-7 h-7 rounded-full bg-accent/20 border border-accent/40 flex items-center justify-center flex-shrink-0">
              <Bot className="w-3.5 h-3.5 text-accent-light" />
            </div>
            <div className="bg-surface border border-border rounded-2xl rounded-tl-sm px-4 py-2.5 max-w-[80%]">
              <p className="text-sm text-slate-200 leading-relaxed">
                Según el <span className="text-accent-light">informe de
                AEMET</span> que tienes archivado, el verano de 2020 fue
                el segundo más cálido desde 1965, con una anomalía de{" "}
                <span className="text-accent-light">+0.9°C</span>.
              </p>
              <div className="mt-2 pt-2 border-t border-border/50 flex items-center gap-2">
                <span className="text-[10px] text-muted">Fuente:</span>
                <span className="text-[10px] text-accent-light font-mono">
                  aemetblog.es/2020/09/18
                </span>
              </div>
            </div>
          </motion.div>
        </div>

        {/* Input bar */}
        <div className="px-4 py-3 border-t border-border bg-surface/30">
          <div className="flex items-center gap-2 bg-card border border-border rounded-lg px-3 py-2">
            <span className="text-xs text-muted flex-1">
              Pregunta sobre tus recursos…
            </span>
            <Send className="w-3.5 h-3.5 text-accent-light" />
          </div>
        </div>
      </div>
    </div>
  );
}
