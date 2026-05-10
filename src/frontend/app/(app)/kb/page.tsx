"use client";
import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BookOpen,
  Search,
  RefreshCw,
  ExternalLink,
  Tag,
  X,
  ChevronDown,
  AlertTriangle,
  CalendarX,
  Trash2,
} from "lucide-react";
import { apiCall } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { useResourceStream } from "@/lib/resource_stream";

interface Resource {
  id: string;
  url: string;
  titulo?: string;
  resumen?: string;
  categoria?: string;
  tags?: string | string[] | null;
  estado: string;
  volatilidad: string;
  fecha_caducidad?: string;
  created_at: string;
}

// "todos" en backend ahora excluye cuarentena/expirado (esos tienen vista dedicada).
// Mantenemos el resto de filtros explícitos por si el usuario quiere un corte.
const ESTADO_OPTS = ["todos", "activo", "procesando", "cuarentena", "expirado"];

const ESTADO_COLORS: Record<string, string> = {
  activo: "bg-green-800/30 text-green-300 border-green-700/30",
  completado: "bg-blue-800/30 text-blue-300 border-blue-700/30",
  procesando: "bg-yellow-800/30 text-yellow-300 border-yellow-700/30",
  expirado: "bg-red-800/30 text-red-300 border-red-700/30",
  cuarentena: "bg-orange-800/30 text-orange-300 border-orange-700/30",
};

const ESTADO_EMOJI: Record<string, string> = {
  activo: "✅",
  completado: "✅",
  procesando: "⏳",
  expirado: "🗑️",
  cuarentena: "⚠️",
};

function parseTags(raw: string | string[] | null | undefined): string[] {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export default function KBPage() {
  const { token } = useAuthStore();
  const [resources, setResources] = useState<Resource[]>([]);
  const [filtered, setFiltered] = useState<Resource[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [estado, setEstado] = useState("todos");
  const [selected, setSelected] = useState<Resource | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<"quarantine" | "expire" | "delete" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiCall<Resource[]>(
        `/resources?estado=${estado}&limit=200`,
        {},
        token
      );
      setResources(data);
    } catch {}
    setLoading(false);
  }, [estado, token]);

  useEffect(() => { load(); }, [load]);

  // SSE: cualquier transición de recurso refresca la lista en vivo.
  useResourceStream(token, () => { load(); });

  async function runAction(action: "quarantine" | "expire" | "delete") {
    if (!selected) return;
    setBusy(true);
    setActionError(null);
    try {
      if (action === "delete") {
        await apiCall(`/resources/${selected.id}`, { method: "DELETE" }, token);
      } else {
        await apiCall(`/resources/${selected.id}/${action}`, { method: "POST" }, token);
      }
      setSelected(null);
      setConfirm(null);
      await load();
    } catch (e: any) {
      setActionError(e?.message ?? "Acción fallida");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    const q = search.toLowerCase();
    if (!q) {
      setFiltered(resources);
    } else {
      setFiltered(
        resources.filter(
          (r) =>
            (r.titulo || "").toLowerCase().includes(q) ||
            r.url.toLowerCase().includes(q) ||
            (r.resumen || "").toLowerCase().includes(q)
        )
      );
    }
  }, [resources, search]);

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 w-full">
      {/* Header */}
      <div className="mb-5">
        <h1 className="text-xl font-bold flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-accent-light" />
          Base de Conocimiento
        </h1>
        <p className="text-sm text-muted mt-1">{filtered.length} recurso(s)</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-5 items-center">
        <div className="relative flex-1 min-w-[160px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted pointer-events-none" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar..."
            className="w-full bg-card border border-border rounded-lg pl-8 pr-3 py-2 text-sm text-slate-100 placeholder-muted outline-none focus:border-accent-light transition-colors"
          />
        </div>

        <div className="relative">
          <select
            value={estado}
            onChange={(e) => setEstado(e.target.value)}
            className="appearance-none bg-card border border-border rounded-lg pl-3 pr-7 py-2 text-sm text-slate-200 outline-none cursor-pointer"
          >
            {ESTADO_OPTS.map((e) => (
              <option key={e} value={e}>
                {e === "todos" ? "Todos los estados" : e}
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted pointer-events-none" />
        </div>

        <button
          onClick={load}
          className="p-2 rounded-lg bg-card border border-border text-muted hover:text-slate-200 transition-colors"
          title="Actualizar"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-card border border-border rounded-xl p-4 animate-pulse">
              <div className="h-4 bg-border rounded w-3/4 mb-2" />
              <div className="h-3 bg-border rounded w-1/2 mb-3" />
              <div className="h-3 bg-border rounded w-full mb-1.5" />
              <div className="h-3 bg-border rounded w-5/6" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center opacity-40">
          <BookOpen className="w-10 h-10 mb-3" />
          <p className="font-medium">Sin recursos</p>
          <p className="text-sm text-muted mt-1">Añade URLs desde la pestaña Ingestar</p>
        </div>
      ) : (
        <motion.div
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
          initial="hidden"
          animate="visible"
          variants={{
            visible: { transition: { staggerChildren: 0.04 } },
            hidden: {},
          }}
        >
          {filtered.map((r) => {
            const tags = parseTags(r.tags);
            const colorClass = ESTADO_COLORS[r.estado] || "bg-slate-800/30 text-slate-300 border-slate-700/30";
            return (
              <motion.button
                key={r.id}
                variants={{
                  hidden: { opacity: 0, y: 16 },
                  visible: { opacity: 1, y: 0, transition: { duration: 0.25 } },
                }}
                onClick={() => setSelected(r)}
                className="bg-card border border-border rounded-xl p-4 text-left hover:border-accent/40 hover:bg-accent/5 transition-all group"
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <h3 className="text-sm font-medium text-slate-100 leading-snug line-clamp-2 flex-1">
                    {r.titulo || r.url}
                  </h3>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full border flex-shrink-0 ${colorClass}`}
                  >
                    {ESTADO_EMOJI[r.estado] || "❓"} {r.estado}
                  </span>
                </div>

                <p className="text-xs text-muted font-mono truncate mb-2 group-hover:text-accent-light transition-colors">
                  {r.url}
                </p>

                {r.resumen && (
                  <p className="text-xs text-slate-400 line-clamp-2 mb-2">{r.resumen}</p>
                )}

                {tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {tags.slice(0, 3).map((t) => (
                      <span
                        key={t}
                        className="text-xs bg-accent/10 text-accent-light px-1.5 py-0.5 rounded-md"
                      >
                        {t}
                      </span>
                    ))}
                    {tags.length > 3 && (
                      <span className="text-xs text-muted">+{tags.length - 3}</span>
                    )}
                  </div>
                )}
              </motion.button>
            );
          })}
        </motion.div>
      )}

      {/* Detail drawer */}
      <AnimatePresence>
        {selected && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/60"
              onClick={() => setSelected(null)}
            />
            <motion.div
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ type: "spring", damping: 28, stiffness: 280 }}
              className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-md bg-surface border-l border-border flex flex-col"
            >
              <div className="flex items-center justify-between px-5 py-4 border-b border-border">
                <h2 className="font-semibold text-slate-100 flex-1 truncate pr-4">
                  {selected.titulo || "Sin título"}
                </h2>
                <button
                  onClick={() => setSelected(null)}
                  className="p-1.5 rounded-lg hover:bg-white/5 transition-colors flex-shrink-0"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-5 space-y-4">
                <a
                  href={selected.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-sm text-accent-light hover:underline break-all"
                >
                  <ExternalLink className="w-3.5 h-3.5 flex-shrink-0" />
                  {selected.url}
                </a>

                <div className="flex flex-wrap gap-2">
                  {[
                    { label: "Estado", value: selected.estado },
                    { label: "Categoría", value: selected.categoria || "—" },
                    { label: "Volatilidad", value: selected.volatilidad },
                  ].map(({ label, value }) => (
                    <div key={label} className="bg-card border border-border rounded-lg px-3 py-2 flex-1 min-w-[100px]">
                      <p className="text-xs text-muted">{label}</p>
                      <p className="text-sm font-medium mt-0.5">{value}</p>
                    </div>
                  ))}
                </div>

                {selected.resumen && (
                  <div>
                    <p className="text-xs text-muted mb-1.5">Resumen</p>
                    <p className="text-sm text-slate-300 leading-relaxed">{selected.resumen}</p>
                  </div>
                )}

                {parseTags(selected.tags).length > 0 && (
                  <div>
                    <p className="text-xs text-muted mb-2 flex items-center gap-1">
                      <Tag className="w-3 h-3" /> Tags
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {parseTags(selected.tags).map((t) => (
                        <span
                          key={t}
                          className="text-xs bg-accent/10 text-accent-light border border-accent/20 px-2 py-0.5 rounded-md"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="text-xs text-muted space-y-1">
                  <p>Creado: {new Date(selected.created_at).toLocaleDateString("es-ES")}</p>
                  {selected.fecha_caducidad && (
                    <p>Caduca: {selected.fecha_caducidad}</p>
                  )}
                </div>

                {actionError && (
                  <div className="p-2.5 rounded-lg bg-red-900/20 border border-red-700/30 text-xs text-red-300">
                    {actionError}
                  </div>
                )}
              </div>

              {/* Drawer footer: acciones según estado */}
              <div className="border-t border-border p-4 space-y-2">
                {(selected.estado === "activo" || selected.estado === "procesando") && (
                  <button
                    disabled={busy}
                    onClick={() => setConfirm("quarantine")}
                    className="w-full flex items-center justify-center gap-2 text-xs font-medium px-3 py-2 rounded-lg bg-amber-900/20 text-amber-300 border border-amber-700/30 hover:bg-amber-900/40 transition-colors disabled:opacity-40"
                  >
                    <AlertTriangle className="w-3.5 h-3.5" />
                    Mandar a cuarentena
                  </button>
                )}
                {selected.estado !== "expirado" && (
                  <button
                    disabled={busy}
                    onClick={() => setConfirm("expire")}
                    className="w-full flex items-center justify-center gap-2 text-xs font-medium px-3 py-2 rounded-lg bg-red-900/20 text-red-300 border border-red-700/30 hover:bg-red-900/40 transition-colors disabled:opacity-40"
                  >
                    <CalendarX className="w-3.5 h-3.5" />
                    Marcar como expirado
                  </button>
                )}
                {(selected.estado === "cuarentena" || selected.estado === "expirado") && (
                  <button
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      setActionError(null);
                      try {
                        await apiCall(`/resources/${selected.id}/rescue`, { method: "POST" }, token);
                        setSelected(null);
                        await load();
                      } catch (e: any) {
                        setActionError(e?.message ?? "Rescate fallido");
                      } finally {
                        setBusy(false);
                      }
                    }}
                    className="w-full flex items-center justify-center gap-2 text-xs font-medium px-3 py-2 rounded-lg bg-green-900/20 text-green-300 border border-green-700/30 hover:bg-green-900/40 transition-colors disabled:opacity-40"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    Rescatar a activo
                  </button>
                )}
                <button
                  disabled={busy}
                  onClick={() => setConfirm("delete")}
                  className="w-full flex items-center justify-center gap-2 text-xs font-medium px-3 py-2 rounded-lg bg-red-950/30 text-red-200 border border-red-800/40 hover:bg-red-900/40 transition-colors disabled:opacity-40"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  Eliminar permanentemente
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Confirmación */}
      <AnimatePresence>
        {confirm && selected && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-[60] bg-black/70"
              onClick={() => !busy && setConfirm(null)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="fixed inset-0 z-[70] flex items-center justify-center p-4"
            >
              <div className="bg-surface border border-border rounded-2xl shadow-2xl max-w-sm w-full p-5">
                <h3 className="font-semibold text-sm mb-2">
                  {confirm === "delete"
                    ? "¿Eliminar definitivamente?"
                    : confirm === "expire"
                      ? "¿Marcar como expirado?"
                      : "¿Mandar a cuarentena?"}
                </h3>
                <p className="text-xs text-muted mb-4">
                  {confirm === "delete"
                    ? "Borra el recurso de tu base de conocimiento. Si nadie más lo tiene, se elimina globalmente y se purga de Qdrant. No se puede deshacer."
                    : confirm === "expire"
                      ? "Lo retira inmediatamente del RAG. Aún podrás rescatarlo desde la vista de Expirados."
                      : "Período de gracia configurable; durante ese tiempo seguirá visible en la vista de Cuarentena y podrás rescatarlo o expirarlo."}
                </p>
                <div className="flex gap-2 justify-end">
                  <button
                    disabled={busy}
                    onClick={() => setConfirm(null)}
                    className="px-3 py-1.5 text-xs rounded-lg bg-card border border-border text-muted hover:text-slate-200 transition-colors"
                  >
                    Cancelar
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => runAction(confirm)}
                    className={`px-3 py-1.5 text-xs font-medium rounded-lg text-white transition-colors ${
                      confirm === "delete"
                        ? "bg-red-700 hover:bg-red-600"
                        : confirm === "expire"
                          ? "bg-red-600 hover:bg-red-500"
                          : "bg-amber-700 hover:bg-amber-600"
                    }`}
                  >
                    {busy ? "Procesando..." : "Sí, continuar"}
                  </button>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
