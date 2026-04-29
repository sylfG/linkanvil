"use client";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  User,
  Bot,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Key,
  Copy,
  Check,
} from "lucide-react";
import { apiCall } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";

export default function ProfilePage() {
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
      const res = await apiCall<any>(
        "/profile/telegram",
        { method: "PUT", body: JSON.stringify({ bot_token: botToken.trim() }) },
        token
      );
      setResult({ ok: true, msg: `Bot @${res.bot_username} conectado correctamente.` });
      // Refresh user
      const me = await apiCall<any>("/auth/me", {}, token);
      if (user) setAuth(token!, me);
      setBotToken("");
    } catch (err: any) {
      setResult({ ok: false, msg: err.message });
    } finally {
      setLoading(false);
    }
  }

  function copyTenantId() {
    if (!user?.tenant_id) return;
    navigator.clipboard.writeText(user.tenant_id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 max-w-2xl mx-auto w-full">
      <div className="mb-6">
        <h1 className="text-xl font-bold flex items-center gap-2">
          <User className="w-5 h-5 text-accent-light" />
          Perfil
        </h1>
      </div>

      {/* Account info */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-card border border-border rounded-2xl p-5 mb-5"
      >
        <h2 className="font-semibold mb-4 text-sm text-muted uppercase tracking-wider">
          Cuenta
        </h2>
        <div className="space-y-3">
          <div>
            <p className="text-xs text-muted mb-1">Email</p>
            <p className="text-sm text-slate-100">{user?.email}</p>
          </div>
          <div>
            <p className="text-xs text-muted mb-1">Tenant ID</p>
            <div className="flex items-center gap-2">
              <code className="text-xs bg-surface border border-border px-2 py-1.5 rounded-lg font-mono text-slate-300 flex-1 truncate">
                {user?.tenant_id}
              </code>
              <button
                onClick={copyTenantId}
                className="p-1.5 rounded-lg bg-surface border border-border hover:border-accent/40 transition-colors"
                title="Copiar"
              >
                {copied ? (
                  <Check className="w-3.5 h-3.5 text-green-400" />
                ) : (
                  <Copy className="w-3.5 h-3.5 text-muted" />
                )}
              </button>
            </div>
          </div>
          <div>
            <p className="text-xs text-muted mb-1">Miembro desde</p>
            <p className="text-sm text-slate-300">
              {user?.created_at
                ? new Date(user.created_at).toLocaleDateString("es-ES", {
                    year: "numeric",
                    month: "long",
                    day: "numeric",
                  })
                : "—"}
            </p>
          </div>
        </div>
      </motion.div>

      {/* Telegram bot */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="bg-card border border-border rounded-2xl p-5"
      >
        <div className="flex items-center gap-2 mb-1">
          <Bot className="w-4 h-4 text-accent-light" />
          <h2 className="font-semibold">Bot de Telegram</h2>
          {user?.telegram_bot_active && (
            <span className="ml-auto text-xs bg-green-800/30 text-green-300 border border-green-700/30 px-2 py-0.5 rounded-full flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> Activo
            </span>
          )}
        </div>
        <p className="text-sm text-muted mb-5">
          Conecta tu propio bot de Telegram. Las URLs que envíes al bot se añadirán
          automáticamente a tu base de conocimiento.
        </p>

        <div className="bg-surface border border-border rounded-xl p-4 mb-5 text-sm space-y-2">
          <p className="font-medium text-slate-200">Cómo crear un bot:</p>
          <ol className="list-decimal pl-4 space-y-1 text-muted">
            <li>
              Abre Telegram y busca <span className="text-accent-light">@BotFather</span>
            </li>
            <li>
              Envía <code className="bg-card px-1 rounded text-xs">/newbot</code> y sigue las instrucciones
            </li>
            <li>Copia el token que te proporciona BotFather</li>
            <li>Pégalo aquí y guarda</li>
          </ol>
        </div>

        {result && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className={`mb-4 p-3 rounded-lg flex items-center gap-2 text-sm ${
              result.ok
                ? "bg-green-900/20 border border-green-700/30 text-green-300"
                : "bg-red-900/20 border border-red-700/30 text-red-300"
            }`}
          >
            {result.ok ? (
              <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
            )}
            {result.msg}
          </motion.div>
        )}

        <form onSubmit={handleSave} className="flex gap-2">
          <div className="relative flex-1">
            <Key className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted pointer-events-none" />
            <input
              type="password"
              value={botToken}
              onChange={(e) => setBotToken(e.target.value)}
              placeholder="123456789:ABCdefGhIJKlmNoPQRstuVWXyz"
              className="w-full bg-surface border border-border rounded-lg pl-8 pr-3 py-2.5 text-sm text-slate-100 placeholder-muted outline-none focus:border-accent-light transition-colors font-mono"
            />
          </div>
          <button
            type="submit"
            disabled={loading || !botToken.trim()}
            className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-2.5 rounded-lg transition-colors whitespace-nowrap"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            {loading ? "Guardando..." : "Guardar bot"}
          </button>
        </form>
      </motion.div>
    </div>
  );
}
