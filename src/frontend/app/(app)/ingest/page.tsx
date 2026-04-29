"use client";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Link2, Plus, CheckCircle2, Loader2, AlertCircle, Trash2 } from "lucide-react";
import { apiCall, sseUrl } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { useSSE, type IngestEvent } from "@/lib/sse";

export default function IngestPage() {
  const { token } = useAuthStore();
  const [urlsInput, setUrlsInput] = useState("");
  const [source, setSource] = useState("web");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState<{ url: string; status: string; icon: string }[]>([]);
  const [error, setError] = useState("");

  const sseFeedUrl = token ? sseUrl(token) : null;
  const { events, clear } = useSSE(sseFeedUrl, (ev) => {
    if (ev.url) {
      setSubmitted((prev) => prev.filter((s) => s.url !== ev.url));
    }
  });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const urls = urlsInput
      .split("\n")
      .map((u) => u.trim())
      .filter(Boolean);
    if (!urls.length) return;

    setLoading(true);
    setError("");
    const results: typeof submitted = [];

    for (const url of urls) {
      try {
        const resp = await apiCall<any>(
          "/ingest",
          { method: "POST", body: JSON.stringify({ url, source }) },
          token
        );
        const isDup = resp.is_duplicate;
        results.push({
          url,
          status: isDup ? "Duplicado — ya en la base" : "Encolada ✓",
          icon: isDup ? "⏭️" : "📥",
        });
      } catch (err: any) {
        results.push({ url, status: `Error: ${err.message}`, icon: "❌" });
      }
    }
    setSubmitted((prev) => [...results, ...prev]);
    setUrlsInput("");
    setLoading(false);
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 max-w-3xl mx-auto w-full">
      <div className="mb-6">
        <h1 className="text-xl font-bold flex items-center gap-2">
          <Link2 className="w-5 h-5 text-accent-light" />
          Ingestar URLs
        </h1>
        <p className="text-sm text-muted mt-1">
          Añade URLs a tu base de conocimiento. Aparecerán aquí cuando terminen de procesarse.
        </p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="bg-card border border-border rounded-2xl p-5 mb-6">
        <div className="flex gap-3 flex-wrap mb-4">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs text-muted mb-1.5">Fuente</label>
            <input
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-slate-100 outline-none focus:border-accent-light transition-colors"
              placeholder="web"
            />
          </div>
        </div>

        <label className="block text-xs text-muted mb-1.5">URLs (una por línea)</label>
        <textarea
          value={urlsInput}
          onChange={(e) => setUrlsInput(e.target.value)}
          rows={4}
          placeholder={"https://ejemplo.com/articulo\nhttps://otro.com/doc"}
          className="w-full bg-surface border border-border rounded-lg px-3 py-2.5 text-sm text-slate-100 placeholder-muted outline-none focus:border-accent-light transition-colors font-mono resize-y"
        />

        {error && (
          <p className="text-red-400 text-sm mt-2 flex items-center gap-1">
            <AlertCircle className="w-3.5 h-3.5" />
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading || !urlsInput.trim()}
          className="mt-4 flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Plus className="w-4 h-4" />
          )}
          {loading ? "Enviando..." : "Ingestar URLs"}
        </button>
      </form>

      {/* Reactive feed — completed via SSE */}
      {events.length > 0 && (
        <div className="mb-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-slate-300 flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-green-400" />
              Completadas ({events.length})
            </h2>
            <button
              onClick={clear}
              className="text-xs text-muted hover:text-slate-300 flex items-center gap-1 transition-colors"
            >
              <Trash2 className="w-3 h-3" />
              Limpiar
            </button>
          </div>
          <div className="space-y-2">
            <AnimatePresence>
              {events.map((ev, i) => (
                <motion.div
                  key={`${ev.recurso_id}-${i}`}
                  initial={{ opacity: 0, y: -8, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  className="bg-green-900/15 border border-green-700/30 rounded-xl p-3.5 flex items-start gap-3"
                >
                  <CheckCircle2 className="w-4 h-4 text-green-400 flex-shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-200 truncate">
                      {ev.titulo || ev.url}
                    </p>
                    <p className="text-xs text-muted truncate mt-0.5">{ev.url}</p>
                  </div>
                  <span className="ml-auto text-xs bg-green-800/30 text-green-300 px-2 py-0.5 rounded-full flex-shrink-0">
                    vectorizado
                  </span>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* Submitted (queued) */}
      {submitted.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-1.5">
            <Loader2 className="w-4 h-4 text-muted animate-spin" />
            Encoladas ({submitted.length})
          </h2>
          <div className="space-y-2">
            {submitted.map((item, i) => (
              <div
                key={i}
                className="bg-card border border-border rounded-xl p-3.5 flex items-center gap-3"
              >
                <span className="text-base flex-shrink-0">{item.icon}</span>
                <div className="min-w-0">
                  <p className="text-xs font-mono text-muted truncate">{item.url}</p>
                  <p className="text-xs text-slate-400 mt-0.5">{item.status}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
