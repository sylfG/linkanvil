"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { Bell, AlertTriangle, CalendarX, RotateCcw, CheckCheck } from "lucide-react";
import { apiCall } from "@/lib/api";

interface NotificationItem {
  id: string;
  evento_tipo: string;
  recurso_id?: string;
  titulo?: string;
  url?: string;
  motivo?: string;
  leido: boolean;
  created_at: string;
}

const REASON_LABEL: Record<string, string> = {
  caducidad: "ha caducado",
  colision_semantica: "fue reemplazado",
  manual: "marcado manualmente",
  gracia_agotada: "expiró tras la gracia",
};

function eventMeta(ev: string) {
  if (ev === "recurso.cuarentena")
    return { Icon: AlertTriangle, cls: "text-amber-300", label: "Cuarentena", href: "/quarantine" };
  if (ev === "recurso.expirado")
    return { Icon: CalendarX, cls: "text-red-300", label: "Expirado", href: "/expired" };
  if (ev === "recurso.rescatado")
    return { Icon: RotateCcw, cls: "text-green-300", label: "Rescatado", href: "/kb" };
  return { Icon: Bell, cls: "text-slate-300", label: ev, href: "/kb" };
}

function formatRelative(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.floor(ms / 60_000);
  if (min < 1) return "ahora";
  if (min < 60) return `hace ${min} min`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `hace ${hr} h`;
  const d = Math.floor(hr / 24);
  return `hace ${d} d`;
}

export function NotificationsBell({ token }: { token: string | null }) {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const data = await apiCall<{ items: NotificationItem[]; count: number }>(
        "/notifications?limit=20", {}, token,
      );
      setItems(data.items);
      setUnread(data.items.filter((n) => !n.leido).length);
    } catch {
      /* el badge es opcional */
    }
  }, [token]);

  useEffect(() => {
    refresh();
    const onVis = () => {
      if (document.visibilityState === "visible") refresh();
    };
    document.addEventListener("visibilitychange", onVis);
    const interval = setInterval(refresh, 60_000);
    return () => {
      document.removeEventListener("visibilitychange", onVis);
      clearInterval(interval);
    };
  }, [refresh]);

  // close on outside click
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  async function markRead(id: string) {
    try {
      await apiCall(`/notifications/${id}/read`, { method: "POST" }, token);
      setItems((prev) => prev.map((n) => (n.id === id ? { ...n, leido: true } : n)));
      setUnread((u) => Math.max(0, u - 1));
    } catch {
      /* silencioso */
    }
  }

  async function markAll() {
    try {
      await apiCall("/notifications/read-all", { method: "POST" }, token);
      setItems((prev) => prev.map((n) => ({ ...n, leido: true })));
      setUnread(0);
    } catch {
      /* silencioso */
    }
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="p-1.5 rounded-lg hover:bg-white/5 text-muted hover:text-slate-100 transition-colors relative"
        title="Notificaciones"
      >
        <Bell className="w-4 h-4" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 bg-red-600 text-white text-[9px] font-bold px-1 py-px rounded-full min-w-[14px] text-center leading-none">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="absolute left-0 top-full mt-2 w-[320px] bg-surface border border-border rounded-xl shadow-2xl z-50 overflow-hidden"
          >
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-border">
              <span className="text-sm font-semibold">Notificaciones</span>
              {unread > 0 && (
                <button
                  onClick={markAll}
                  className="flex items-center gap-1 text-[11px] text-muted hover:text-slate-200 transition-colors"
                  title="Marcar todas como leídas"
                >
                  <CheckCheck className="w-3 h-3" />
                  Leer todas
                </button>
              )}
            </div>
            <div className="max-h-[400px] overflow-y-auto">
              {items.length === 0 ? (
                <div className="px-4 py-8 text-center text-xs text-muted">
                  No tienes notificaciones.
                </div>
              ) : (
                <ul className="divide-y divide-border">
                  {items.map((n) => {
                    const { Icon, cls, label, href } = eventMeta(n.evento_tipo);
                    const motiveLabel = n.motivo ? REASON_LABEL[n.motivo] ?? n.motivo : null;
                    return (
                      <li
                        key={n.id}
                        className={`px-4 py-3 hover:bg-white/[0.02] transition-colors ${
                          n.leido ? "opacity-60" : ""
                        }`}
                      >
                        <Link
                          href={href}
                          onClick={() => {
                            if (!n.leido) markRead(n.id);
                            setOpen(false);
                          }}
                          className="flex items-start gap-3"
                        >
                          <div className="flex-shrink-0 mt-0.5">
                            <Icon className={`w-4 h-4 ${cls}`} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-medium text-slate-100 line-clamp-1">
                              {n.titulo || n.url || label}
                            </p>
                            <p className="text-[11px] text-muted mt-0.5 line-clamp-1">
                              <span className={cls}>{label}</span>
                              {motiveLabel && <span> — {motiveLabel}</span>}
                            </p>
                            <p className="text-[10px] text-muted mt-0.5">
                              {formatRelative(n.created_at)}
                            </p>
                          </div>
                          {!n.leido && (
                            <span className="w-2 h-2 rounded-full bg-accent-light flex-shrink-0 mt-1.5" />
                          )}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
