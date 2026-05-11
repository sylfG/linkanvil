"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain, MessageSquare, Link2, BookOpen, AlertTriangle, CalendarX,
  LogOut, Menu, X, Plus, Trash2,
  User, Bot, CheckCircle2, AlertCircle, Loader2, Key, Copy, Check,
} from "lucide-react";
import { useAuthStore } from "@/lib/auth";
import { useChatStore } from "@/lib/chats";
import { apiCall } from "@/lib/api";
import { ResourceStreamProvider, useResourceStream } from "@/lib/resource_stream";
import { NotificationsBell } from "./_NotificationsBell";

type NavItem = {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  badge?: "quarantine" | "expired";
};

const NAV: NavItem[] = [
  { href: "/ingest", icon: Link2, label: "Ingestar URLs" },
  { href: "/kb", icon: BookOpen, label: "Base de Conocimiento" },
  { href: "/quarantine", icon: AlertTriangle, label: "Cuarentena", badge: "quarantine" },
  { href: "/expired", icon: CalendarX, label: "Expirados", badge: "expired" },
];

// ── Profile modal ─────────────────────────────────────────────────────────────

function ProfileModal({ onClose }: { onClose: () => void }) {
  const { token, user, setAuth } = useAuthStore();
  const [botToken, setBotToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!botToken.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await apiCall<any>("/profile/telegram", { method: "PUT", body: JSON.stringify({ bot_token: botToken.trim() }) }, token);
      setResult({ ok: true, msg: `Bot @${res.bot_username} conectado correctamente.` });
      const me = await apiCall<any>("/auth/me", {}, token);
      if (user) setAuth(token!, me);
      setBotToken("");
    } catch (err: any) {
      setResult({ ok: false, msg: err.message });
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      {/* backdrop */}
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 bg-black/60"
        onClick={onClose}
      />
      {/* panel */}
      <motion.div
        initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }}
        transition={{ type: "spring", damping: 28, stiffness: 300 }}
        className="fixed bottom-0 left-0 right-0 md:left-auto md:right-auto md:w-[420px] md:bottom-4 md:left-4 z-50 bg-surface border border-border rounded-t-2xl md:rounded-2xl shadow-2xl overflow-y-auto max-h-[90vh]"
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <User className="w-4 h-4 text-accent-light" />
            <span className="font-semibold text-sm">Perfil</span>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-white/10 text-muted hover:text-slate-200 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* Account */}
          <div className="bg-card border border-border rounded-xl p-4 space-y-3">
            <p className="text-xs text-muted uppercase tracking-wider font-medium">Cuenta</p>
            <div>
              <p className="text-xs text-muted mb-0.5">Email</p>
              <p className="text-sm text-slate-100">{user?.email}</p>
            </div>
            <div>
              <p className="text-xs text-muted mb-0.5">Tenant ID</p>
              <div className="flex items-center gap-2">
                <code className="text-xs bg-surface border border-border px-2 py-1 rounded-lg font-mono text-slate-300 flex-1 truncate">
                  {user?.tenant_id}
                </code>
                <button
                  onClick={() => { navigator.clipboard.writeText(user?.tenant_id ?? ""); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
                  className="p-1.5 rounded-lg bg-surface border border-border hover:border-accent/40 transition-colors"
                >
                  {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3 text-muted" />}
                </button>
              </div>
            </div>
          </div>

          {/* Telegram */}
          <div className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center gap-2 mb-1">
              <Bot className="w-4 h-4 text-accent-light" />
              <span className="font-semibold text-sm">Bot de Telegram</span>
              {user?.telegram_bot_active && (
                <span className="ml-auto text-xs bg-green-800/30 text-green-300 border border-green-700/30 px-2 py-0.5 rounded-full flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> Activo
                </span>
              )}
            </div>
            <p className="text-xs text-muted mb-3">Envía URLs a tu bot y se añadirán a tu base de conocimiento.</p>

            {result && (
              <div className={`mb-3 p-2.5 rounded-lg flex items-center gap-2 text-xs ${result.ok ? "bg-green-900/20 border border-green-700/30 text-green-300" : "bg-red-900/20 border border-red-700/30 text-red-300"}`}>
                {result.ok ? <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" /> : <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />}
                {result.msg}
              </div>
            )}

            <form onSubmit={handleSave} className="flex gap-2">
              <div className="relative flex-1">
                <Key className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-muted pointer-events-none" />
                <input
                  type="password"
                  value={botToken}
                  onChange={(e) => setBotToken(e.target.value)}
                  placeholder="123456789:ABCdefGh…"
                  className="w-full bg-surface border border-border rounded-lg pl-7 pr-3 py-2 text-xs text-slate-100 placeholder-muted outline-none focus:border-accent-light transition-colors font-mono"
                />
              </div>
              <button
                type="submit"
                disabled={loading || !botToken.trim()}
                className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover disabled:opacity-40 text-white text-xs font-medium px-3 py-2 rounded-lg transition-colors whitespace-nowrap"
              >
                {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                {loading ? "Guardando..." : "Guardar"}
              </button>
            </form>
          </div>
        </div>
      </motion.div>
    </>
  );
}

// ── sidebar nav + chat history ────────────────────────────────────────────────

function SidebarContent({ onNavClick }: { onNavClick?: () => void }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, clearAuth, token } = useAuthStore();
  const { sessions, activeId, setActive, createSession, deleteSession, messagesMap } = useChatStore();
  const [profileOpen, setProfileOpen] = useState(false);
  const [quarantineCount, setQuarantineCount] = useState(0);
  const [expiredCount, setExpiredCount] = useState(0);

  const refreshCounts = useCallback(async () => {
    if (!token) return;
    try {
      const [q, e] = await Promise.all([
        apiCall<{ count: number }>("/resources/quarantine?count_only=true", {}, token),
        apiCall<{ count: number }>("/resources/expired?count_only=true", {}, token),
      ]);
      setQuarantineCount(q.count);
      setExpiredCount(e.count);
    } catch {
      /* el badge es opcional, no rompemos el sidebar si la API falla */
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    refreshCounts();
    const onVis = () => {
      if (document.visibilityState === "visible") refreshCounts();
    };
    document.addEventListener("visibilitychange", onVis);
    // Red de seguridad (5 min) ahora que SSE está activo.
    const interval = setInterval(refreshCounts, 5 * 60_000);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [token, pathname, refreshCounts]);

  // SSE: cualquier transición recalcula los badges al instante.
  useResourceStream(token, () => { refreshCounts(); });

  async function newChat() {
    if (!token) return;
    // Reusa una sesión vacía existente si la hay: o (a) ya tenemos sus
    // mensajes cargados localmente y son 0, o (b) la sesión sigue con el
    // título por defecto "Nueva conversación" (titulo NULL en backend),
    // que es el indicador fiable de "aún no se envió ningún mensaje".
    const emptyExisting = sessions.find((s) => {
      const msgs = messagesMap[s.id];
      if (msgs !== undefined) return msgs.length === 0;
      return s.title === "Nueva conversación";
    });
    if (emptyExisting) {
      setActive(emptyExisting.id);
      router.push("/");
      onNavClick?.();
      return;
    }
    await createSession(token);
    router.push("/");
    onNavClick?.();
  }

  return (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 py-5 border-b border-border flex-shrink-0">
        <div className="w-8 h-8 rounded-lg bg-accent/20 flex items-center justify-center flex-shrink-0">
          <Brain className="w-5 h-5 text-accent-light" />
        </div>
        <span className="font-bold text-slate-100 flex-1">LinkAnvil</span>
        <NotificationsBell token={token} />
      </div>

      {/* Scrollable nav + history */}
      <div className="flex-1 overflow-y-auto p-3 space-y-1 min-h-0">
        {/* Main nav */}
        {NAV.map(({ href, icon: Icon, label, badge }) => {
          const active = pathname === href;
          const badgeCount =
            badge === "quarantine" ? quarantineCount :
            badge === "expired" ? expiredCount : 0;
          const showBadge = !!badge && badgeCount > 0;
          const badgeCls =
            badge === "expired"
              ? "bg-red-700/40 text-red-200 border border-red-600/40"
              : "bg-amber-700/40 text-amber-200 border border-amber-600/40";
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavClick}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                active
                  ? "bg-accent/20 text-accent-light"
                  : "text-muted hover:text-slate-100 hover:bg-white/5"
              }`}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              <span className="flex-1">{label}</span>
              {showBadge && (
                <span className={`ml-auto ${badgeCls} text-[10px] font-semibold px-1.5 py-0.5 rounded-full min-w-[20px] text-center`}>
                  {badgeCount > 99 ? "99+" : badgeCount}
                </span>
              )}
            </Link>
          );
        })}

        {/* Chat history — siempre presente para que "Nuevo chat" sea
            visible incluso sin sesiones aún */}
        <div className="pt-3">
          <div className="px-3 mb-1">
            <span className="text-[11px] text-muted uppercase tracking-wider font-medium">Conversaciones</span>
          </div>
          {/* Botón "Nuevo chat" fijo justo bajo la cabecera Conversaciones.
              sticky top-0 lo mantiene visible cuando la lista de chats
              scrollea por debajo. */}
          <div className="sticky top-0 z-10 bg-surface pb-1">
            <button
              onClick={newChat}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-accent/20 hover:bg-accent/30 text-accent-light text-sm font-medium w-full transition-colors"
            >
              <Plus className="w-4 h-4 flex-shrink-0" />
              Nuevo chat
            </button>
          </div>
          {sessions.length > 0 && (
            <div className="space-y-0.5">
              {sessions.map((s) => (
                <div
                  key={s.id}
                  className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors ${
                    s.id === activeId ? "bg-accent/15 text-slate-200" : "text-muted hover:text-slate-200 hover:bg-white/5"
                  }`}
                  onClick={() => { setActive(s.id); router.push("/"); onNavClick?.(); }}
                >
                  <MessageSquare className="w-3.5 h-3.5 flex-shrink-0 opacity-60" />
                  <span className="text-xs truncate flex-1">{s.title}</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); if (token) deleteSession(s.id, token); }}
                    className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-white/10 transition-all flex-shrink-0"
                    title="Eliminar"
                  >
                    <Trash2 className="w-3 h-3 text-muted hover:text-red-400" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Bottom: user + logout */}
      <div className="p-3 border-t border-border flex-shrink-0">
        <button
          onClick={() => setProfileOpen(true)}
          className="flex items-center gap-2.5 px-3 py-2.5 w-full rounded-lg hover:bg-white/5 transition-colors text-left group"
        >
          <div className="w-7 h-7 rounded-full bg-accent/20 flex items-center justify-center flex-shrink-0">
            <User className="w-3.5 h-3.5 text-accent-light" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs text-slate-300 truncate">{user?.email}</p>
            <p className="text-[10px] text-muted">Ver perfil</p>
          </div>
        </button>
        <button
          onClick={() => { clearAuth(); router.push("/login"); }}
          className="flex items-center gap-3 px-3 py-2 w-full rounded-lg text-sm text-muted hover:text-red-400 hover:bg-red-900/10 transition-colors mt-1"
        >
          <LogOut className="w-4 h-4" />
          Cerrar sesión
        </button>
      </div>

      <AnimatePresence>
        {profileOpen && <ProfileModal onClose={() => setProfileOpen(false)} />}
      </AnimatePresence>
    </div>
  );
}

// ── layout ────────────────────────────────────────────────────────────────────

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { token } = useAuthStore();
  const { init } = useChatStore();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => { setHydrated(true); }, []);
  useEffect(() => { if (hydrated && !token) router.push("/login"); }, [hydrated, token, router]);
  useEffect(() => { if (hydrated && token) init(token).catch(() => {}); }, [hydrated, token]);

  if (!hydrated || !token) {
    return (
      <div className="min-h-screen bg-bg flex items-center justify-center">
        <span className="w-8 h-8 border-2 border-accent/30 border-t-accent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <ResourceStreamProvider token={token}>
    <div className="flex h-screen overflow-hidden bg-bg">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex flex-col w-60 border-r border-border bg-surface flex-shrink-0">
        <SidebarContent />
      </aside>

      {/* Mobile header */}
      <div className="md:hidden fixed top-0 inset-x-0 z-40 bg-surface border-b border-border flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2">
          <Brain className="w-5 h-5 text-accent-light" />
          <span className="font-bold text-sm">LinkAnvil</span>
        </div>
        <button onClick={() => setMobileOpen(!mobileOpen)} className="p-1.5 rounded-lg hover:bg-white/5 transition-colors">
          {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Mobile drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="md:hidden fixed inset-0 z-30 bg-black/60"
              onClick={() => setMobileOpen(false)}
            />
            <motion.div
              initial={{ x: "-100%" }} animate={{ x: 0 }} exit={{ x: "-100%" }}
              transition={{ type: "spring", damping: 25, stiffness: 300 }}
              className="md:hidden fixed left-0 top-0 bottom-0 z-40 w-64 bg-surface border-r border-border"
            >
              <SidebarContent onNavClick={() => setMobileOpen(false)} />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Main */}
      <main className="flex-1 overflow-hidden flex flex-col md:pt-0 pt-14">
        {children}
      </main>
    </div>
    </ResourceStreamProvider>
  );
}
