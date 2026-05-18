"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowRight, Loader2, Sparkles } from "lucide-react";
import { useAuthStore } from "@/lib/auth";
import { startDemoSession } from "@/lib/demo";

export default function CTABanner() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDemoClick() {
    setError(null);
    setLoading(true);
    try {
      await startDemoSession();
      router.push("/demo");
    } catch (err: any) {
      setError(err?.message ?? "No se pudo iniciar la sesión demo.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="py-20 md:py-24">
      <div className="max-w-5xl mx-auto px-5 md:px-8">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-50px" }}
          transition={{ duration: 0.5 }}
          className="relative overflow-hidden rounded-3xl border border-accent/30 p-10 md:p-14 text-center"
          style={{
            background:
              "linear-gradient(135deg, rgba(124, 58, 237, 0.18) 0%, rgba(124, 58, 237, 0.05) 60%, transparent 100%)",
          }}
        >
          {/* Decorative blobs */}
          <div
            aria-hidden
            className="absolute -top-20 -right-20 w-72 h-72 rounded-full pointer-events-none"
            style={{
              background:
                "radial-gradient(circle, rgba(139, 92, 246, 0.25), transparent 70%)",
            }}
          />
          <div
            aria-hidden
            className="absolute -bottom-20 -left-20 w-72 h-72 rounded-full pointer-events-none"
            style={{
              background:
                "radial-gradient(circle, rgba(124, 58, 237, 0.2), transparent 70%)",
            }}
          />

          <h2 className="relative text-2xl md:text-4xl font-semibold tracking-[-0.02em] text-slate-100 mb-4">
            Pruébalo con datos de ejemplo
            <br className="hidden sm:block" />
            <span className="text-accent-light"> en 30 segundos.</span>
          </h2>
          <p className="relative text-muted text-base md:text-lg mb-8 max-w-xl mx-auto">
            Cuenta demo lista para usar. Sin tarjeta, sin formularios largos.
          </p>
          {token ? (
            <Link
              href="/chat"
              className="relative inline-flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover text-white font-medium px-6 py-3.5 rounded-lg transition-colors text-base group"
            >
              Abrir tu cerebro
              <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
            </Link>
          ) : (
            <button
              onClick={handleDemoClick}
              disabled={loading}
              className="relative inline-flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-60 disabled:cursor-not-allowed text-white font-medium px-6 py-3.5 rounded-lg transition-colors text-base group"
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Sparkles className="w-4 h-4" />
              )}
              {loading ? "Preparando demo..." : "Acceder al demo"}
            </button>
          )}
          {error && (
            <p className="relative text-xs text-red-300 mt-3" role="alert">
              {error}
            </p>
          )}
        </motion.div>
      </div>
    </section>
  );
}
