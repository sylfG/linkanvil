"use client";
import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ExternalLink,
  RefreshCw,
  Trash2,
  X,
  CalendarX,
  RotateCcw,
} from "lucide-react";
import { apiCall } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { useResourceStream, useResourceStreamDispatch } from "@/lib/resource_stream";
import { Pagination, PAGE_SIZE } from "@/components/Pagination";

interface ExpiredItem {
  id: string;
  url: string;
  titulo?: string;
  resumen?: string;
  categoria?: string;
  volatilidad?: string;
  fecha_caducidad?: string;
  quarantined_at?: string;
  quarantine_reason?: "caducidad" | "colision_semantica" | "manual";
  dias_desde_expiracion: number | null;
  updated_at: string;
}

export default function ExpiredPage() {
  const { token } = useAuthStore();
  const [items, setItems] = useState<ExpiredItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const dispatchEvent = useResourceStreamDispatch();

  const totalPages = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
  const pageItems = items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  useEffect(() => {
    if (page > totalPages) setPage(1);
  }, [page, totalPages]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiCall<{ items: ExpiredItem[]; count: number }>(
        "/resources/expired?limit=200",
        {},
        token,
      );
      setItems(data.items);
    } catch (e: any) {
      setError(e.message ?? "Error cargando recursos expirados");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const onVis = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [load]);

  // SSE: nuevos expirados aparecen sin refresh manual.
  useResourceStream(token, () => { load(); });

  function fireOptimistic(id: string, evento_tipo: "recurso.rescatado" | "recurso.eliminado") {
    const item = items.find((it) => it.id === id);
    dispatchEvent({
      evento_tipo,
      recurso_id: id,
      url: item?.url,
      titulo: item?.titulo,
      created_at: new Date().toISOString(),
      optimistic: true,
    });
  }

  async function remove(id: string) {
    setBusyId(id);
    setConfirm(null);
    try {
      await apiCall(`/resources/${id}`, { method: "DELETE" }, token);
      fireOptimistic(id, "recurso.eliminado");
      setItems((prev) => prev.filter((it) => it.id !== id));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function rescue(id: string) {
    setBusyId(id);
    try {
      await apiCall(`/resources/${id}/rescue`, { method: "POST" }, token);
      fireOptimistic(id, "recurso.rescatado");
      setItems((prev) => prev.filter((it) => it.id !== id));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 w-full">
      <div className="mb-5 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <CalendarX className="w-5 h-5 text-amber-400" />
            Archivo histórico
          </h1>
          <p className="text-sm text-muted mt-1">
            {items.length} recurso(s) fuera del KB activo. Consultables en chat
            con el toggle <span className="text-amber-300 font-medium">Archivo ON</span>.
            Puedes rescatarlos al KB activo o eliminarlos definitivamente.
          </p>
        </div>
        <button
          onClick={load}
          className="p-2 rounded-lg bg-card border border-border text-muted hover:text-slate-200 transition-colors"
          title="Actualizar"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-900/20 border border-red-700/30 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-card border border-border rounded-xl p-4 animate-pulse">
              <div className="h-4 bg-border rounded w-3/4 mb-2" />
              <div className="h-3 bg-border rounded w-1/2 mb-3" />
              <div className="h-3 bg-border rounded w-full" />
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center opacity-50">
          <CalendarX className="w-10 h-10 mb-3" />
          <p className="font-medium">Archivo histórico vacío</p>
          <p className="text-sm text-muted mt-1">
            Aún no hay recursos archivados. Los contenidos pasados con valor
            archivístico alto llegarán aquí automáticamente.
          </p>
        </div>
      ) : (
        <motion.ul
          className="grid grid-cols-1 lg:grid-cols-2 gap-3"
          initial="hidden"
          animate="visible"
          variants={{ visible: { transition: { staggerChildren: 0.03 } }, hidden: {} }}
        >
          {pageItems.map((it) => {
            const busy = busyId === it.id;
            return (
              <motion.li
                key={it.id}
                variants={{
                  hidden: { opacity: 0, y: 12 },
                  visible: { opacity: 1, y: 0, transition: { duration: 0.2 } },
                }}
                className="bg-card border border-border rounded-xl p-4 flex flex-col gap-3 opacity-90"
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="text-sm font-medium text-slate-100 leading-snug line-clamp-2 flex-1">
                    {it.titulo || it.url}
                  </h3>
                  <span className="text-xs px-2 py-0.5 rounded-full border flex items-center gap-1 flex-shrink-0 bg-amber-900/30 text-amber-300 border-amber-700/30">
                    <CalendarX className="w-3 h-3" />
                    Archivado
                  </span>
                </div>

                <a
                  href={it.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs font-mono text-muted hover:text-accent-light transition-colors truncate"
                >
                  <ExternalLink className="w-3 h-3 flex-shrink-0" />
                  <span className="truncate">{it.url}</span>
                </a>

                {it.resumen && (
                  <p className="text-xs text-slate-400 line-clamp-2">{it.resumen}</p>
                )}

                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted">
                    {it.dias_desde_expiracion === null
                      ? "Sin fecha de caducidad"
                      : it.dias_desde_expiracion === 0
                        ? "Expiró hoy"
                        : `Expiró hace ${it.dias_desde_expiracion} día(s)`}
                  </span>
                  {it.fecha_caducidad && (
                    <span className="text-muted">
                      {new Date(it.fecha_caducidad).toLocaleDateString("es-ES")}
                    </span>
                  )}
                </div>

                <div className="flex gap-2 pt-1 border-t border-border/60">
                  <button
                    disabled={busy}
                    onClick={() => rescue(it.id)}
                    className="flex-1 flex items-center justify-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-green-900/20 text-green-300 border border-green-700/30 hover:bg-green-900/40 transition-colors disabled:opacity-40"
                    title="Devolver a activo (recalcula caducidad por volatilidad)"
                  >
                    <RotateCcw className="w-3 h-3" />
                    Rescatar
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => setConfirm(it.id)}
                    className="flex-1 flex items-center justify-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-red-900/20 text-red-300 border border-red-700/30 hover:bg-red-900/40 transition-colors disabled:opacity-40"
                  >
                    <Trash2 className="w-3 h-3" />
                    Eliminar
                  </button>
                </div>
              </motion.li>
            );
          })}
        </motion.ul>
      )}

      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={items.length}
        onChange={setPage}
      />

      <AnimatePresence>
        {confirm && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/60"
              onClick={() => setConfirm(null)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="fixed inset-0 z-50 flex items-center justify-center p-4"
            >
              <div className="bg-surface border border-border rounded-2xl shadow-2xl max-w-sm w-full p-5">
                <div className="flex items-start gap-3 mb-4">
                  <div className="w-10 h-10 rounded-full bg-red-900/30 flex items-center justify-center flex-shrink-0">
                    <Trash2 className="w-5 h-5 text-red-400" />
                  </div>
                  <div className="flex-1">
                    <h3 className="font-semibold text-sm">¿Eliminar definitivamente?</h3>
                    <p className="text-xs text-muted mt-1">
                      Borra el recurso de tu base de conocimiento. Si nadie más lo tiene,
                      se elimina globalmente y de Qdrant. No se puede deshacer.
                    </p>
                  </div>
                  <button
                    onClick={() => setConfirm(null)}
                    className="p-1 rounded-lg hover:bg-white/5 transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => setConfirm(null)}
                    className="px-3 py-1.5 text-xs rounded-lg bg-card border border-border text-muted hover:text-slate-200 transition-colors"
                  >
                    Cancelar
                  </button>
                  <button
                    onClick={() => remove(confirm)}
                    className="px-3 py-1.5 text-xs font-medium rounded-lg bg-red-700 hover:bg-red-600 text-white transition-colors"
                  >
                    Sí, eliminar
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
