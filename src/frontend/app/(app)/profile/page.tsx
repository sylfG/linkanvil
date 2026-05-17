"use client";
import { useEffect, useMemo, useState } from "react";
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
  ShieldCheck,
  ShieldAlert,
  Shield,
  ShieldOff,
  CalendarX,
  FileText,
} from "lucide-react";
import { apiCall } from "@/lib/api";
import {
  useAuthStore,
  AUDIT_PRESETS,
  AUDIT_POLICY_KEYS,
  DEFAULT_AUDIT_POLICY,
  matchPreset,
  type AuditPolicy,
  type AuditPolicyKey,
  type AuditDecision,
  type AuditPresetName,
} from "@/lib/auth";
import { copyToClipboard } from "@/lib/clipboard";

// Etiquetas humanas para las 6 celdas. Agrupadas en dos secciones según
// temporal_class para que la card se lea como una matriz, no como una
// lista plana de 6 ítems desordenados.
const CELL_LABELS: Record<AuditPolicyKey, { titulo: string; desc: string }> = {
  evento_pasado_alto: {
    titulo: "Valor archivístico alto",
    desc: "Post-mortems, papers retrospectivos, informes oficiales del evento.",
  },
  evento_pasado_medio: {
    titulo: "Valor archivístico medio",
    desc: "Crónicas, notas de prensa, cobertura periodística estándar.",
  },
  evento_pasado_nulo: {
    titulo: "Valor archivístico nulo",
    desc: "Ofertas vencidas, anuncios caducados, contenido sin reutilización.",
  },
  referencia_pasada_alto: {
    titulo: "Valor archivístico alto",
    desc: "Análisis estructural con datos verificables, papers, informes.",
  },
  referencia_pasada_medio: {
    titulo: "Valor archivístico medio",
    desc: "Artículos descriptivos con valor moderado.",
  },
  referencia_pasada_nulo: {
    titulo: "Valor archivístico nulo",
    desc: "Contenido obsoleto sin reusable.",
  },
};

const DECISION_OPTIONS: { value: AuditDecision; label: string; help: string }[] = [
  {
    value: "activo",
    label: "Activo en KB",
    help: "Queda disponible en la base de conocimiento principal y participa en el RAG por defecto.",
  },
  {
    value: "cuarentena",
    label: "Cuarentena (triaje manual)",
    help: "Va a /quarantine con un período de gracia. Tú decides rescatar o expirar.",
  },
  {
    value: "expirado",
    label: "Archivo histórico",
    help: "Se vectoriza igualmente pero queda en /expired. Recuperable en chat solo si activas el toggle Archivo ON.",
  },
];

const PRESET_META: Record<AuditPresetName, { label: string; icon: typeof ShieldAlert; desc: string }> = {
  estricto: {
    label: "Estricto",
    icon: ShieldAlert,
    desc: "Cualquier contenido pasado va a cuarentena. Tú decides una a una si rescatar o archivar.",
  },
  equilibrado: {
    label: "Equilibrado",
    icon: Shield,
    desc: "Valor alto se archiva automáticamente; medio/nulo va a cuarentena. Confía en el LLM cuando dice 'alto'.",
  },
  permisivo: {
    label: "Permisivo",
    icon: ShieldOff,
    desc: "Como equilibrado, pero las referencias de valor medio siguen activas en la KB.",
  },
};

export default function ProfilePage() {
  const { token, user, setAuth } = useAuthStore();
  const [botToken, setBotToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const [policy, setPolicy] = useState<AuditPolicy>(
    user?.audit_policy ?? DEFAULT_AUDIT_POLICY,
  );
  const [savingPolicy, setSavingPolicy] = useState(false);
  const [policyOk, setPolicyOk] = useState<boolean | null>(null);

  useEffect(() => {
    if (user?.audit_policy) setPolicy(user.audit_policy);
  }, [user?.audit_policy]);

  const currentPreset = useMemo(() => matchPreset(policy), [policy]);

  async function savePolicy(next: AuditPolicy) {
    if (!token || savingPolicy) return;
    setSavingPolicy(true);
    setPolicyOk(null);
    try {
      await apiCall(
        "/profile/audit-policy",
        { method: "PUT", body: JSON.stringify({ policy: next }) },
        token,
      );
      setPolicy(next);
      // Refrescamos /auth/me para que la store quede consistente con el server
      // (útil si otro cliente hiciera cambios concurrentes).
      const me = await apiCall<any>("/auth/me", {}, token);
      if (token) setAuth(token, me);
      setPolicyOk(true);
      setTimeout(() => setPolicyOk(null), 2500);
    } catch {
      setPolicyOk(false);
      setTimeout(() => setPolicyOk(null), 4000);
    } finally {
      setSavingPolicy(false);
    }
  }

  function applyPreset(name: AuditPresetName) {
    void savePolicy({ ...AUDIT_PRESETS[name] });
  }

  function setCell(key: AuditPolicyKey, value: AuditDecision) {
    void savePolicy({ ...policy, [key]: value });
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!botToken.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await apiCall<any>(
        "/profile/telegram",
        { method: "PUT", body: JSON.stringify({ bot_token: botToken.trim() }) },
        token,
      );
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

  async function copyTenantId() {
    if (!user?.tenant_id) return;
    const done = await copyToClipboard(user.tenant_id);
    if (!done) return;
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

      {/* Auditoría de recursos — policy matrix por celda (migración 0007) */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="bg-card border border-border rounded-2xl p-5 mt-5"
      >
        <div className="flex items-center gap-2 mb-1">
          <ShieldCheck className="w-4 h-4 text-accent-light" />
          <h2 className="font-semibold">Auditoría de recursos</h2>
          {policyOk === true && (
            <span className="ml-auto text-xs bg-green-800/30 text-green-300 border border-green-700/30 px-2 py-0.5 rounded-full flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> Guardado
            </span>
          )}
          {policyOk === false && (
            <span className="ml-auto text-xs bg-red-800/30 text-red-300 border border-red-700/30 px-2 py-0.5 rounded-full flex items-center gap-1">
              <AlertCircle className="w-3 h-3" /> Error
            </span>
          )}
        </div>
        <p className="text-sm text-muted mb-2">
          Qué hace LinkAnvil al ingerir un recurso cuya fecha es pasada
          (artículos retrospectivos, noticias antiguas, eventos cerrados).
        </p>
        <p className="text-xs text-muted mb-5">
          {currentPreset ? (
            <>
              Configuración actual: preset{" "}
              <span className="text-accent-light font-medium">
                {PRESET_META[currentPreset].label}
              </span>
            </>
          ) : (
            <span className="text-accent-light font-medium">
              Configuración personalizada
            </span>
          )}
        </p>

        {/* Preset shortcuts: rellenan las 6 celdas de un click */}
        <div className="mb-5">
          <p className="text-xs text-muted uppercase tracking-wider mb-2">
            Cargar preset
          </p>
          <div className="grid grid-cols-3 gap-2">
            {(Object.keys(AUDIT_PRESETS) as AuditPresetName[]).map((name) => {
              const meta = PRESET_META[name];
              const Icon = meta.icon;
              const isActive = currentPreset === name;
              return (
                <button
                  key={name}
                  onClick={() => applyPreset(name)}
                  disabled={savingPolicy}
                  className={`p-2.5 rounded-lg border transition-colors flex flex-col items-center gap-1 text-xs ${
                    isActive
                      ? "bg-accent/15 border-accent/40 text-slate-100"
                      : "bg-surface border-border hover:border-accent/30 text-slate-300"
                  } ${savingPolicy ? "opacity-60 cursor-wait" : ""}`}
                  title={meta.desc}
                >
                  <Icon
                    className={`w-4 h-4 ${
                      isActive ? "text-accent-light" : "text-muted"
                    }`}
                  />
                  {meta.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Matriz fina por celda. Dos secciones: evento_pasado / referencia_pasada */}
        <div className="space-y-5">
          <PolicySection
            title="Eventos con fecha pasada"
            icon={CalendarX}
            description="Ferias, deadlines, ofertas o citas cuya fecha ya ha pasado."
            cells={["evento_pasado_alto", "evento_pasado_medio", "evento_pasado_nulo"]}
            policy={policy}
            disabled={savingPolicy}
            onChange={setCell}
          />
          <PolicySection
            title="Referencias descriptivas pasadas"
            icon={FileText}
            description="Artículos, análisis o crónicas sobre algo que ya ocurrió."
            cells={[
              "referencia_pasada_alto",
              "referencia_pasada_medio",
              "referencia_pasada_nulo",
            ]}
            policy={policy}
            disabled={savingPolicy}
            onChange={setCell}
          />
        </div>

        <p className="text-xs text-muted mt-4 leading-relaxed">
          Los recursos ever-green (tutoriales, docs estables) y los eventos
          futuros siempre quedan activos en la KB independientemente de la
          configuración.
        </p>
      </motion.div>
    </div>
  );
}

// Componente auxiliar: agrupa 3 celdas del mismo temporal_class.
function PolicySection({
  title,
  icon: Icon,
  description,
  cells,
  policy,
  disabled,
  onChange,
}: {
  title: string;
  icon: typeof CalendarX;
  description: string;
  cells: AuditPolicyKey[];
  policy: AuditPolicy;
  disabled: boolean;
  onChange: (key: AuditPolicyKey, value: AuditDecision) => void;
}) {
  return (
    <div className="bg-surface/40 border border-border rounded-xl p-4">
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-3.5 h-3.5 text-accent-light" />
        <h3 className="font-medium text-sm text-slate-100">{title}</h3>
      </div>
      <p className="text-xs text-muted mb-3">{description}</p>
      <div className="space-y-2.5">
        {cells.map((cell) => {
          const meta = CELL_LABELS[cell];
          return (
            <div
              key={cell}
              className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2"
            >
              <div className="min-w-0 sm:flex-1">
                <p className="text-xs text-slate-200">{meta.titulo}</p>
                <p className="text-[11px] text-muted leading-snug">{meta.desc}</p>
              </div>
              <select
                value={policy[cell]}
                onChange={(e) => onChange(cell, e.target.value as AuditDecision)}
                disabled={disabled}
                className="bg-card border border-border rounded-md text-xs text-slate-100 px-2 py-1.5 outline-none focus:border-accent-light transition-colors min-w-[170px] disabled:opacity-60 disabled:cursor-wait"
                title={DECISION_OPTIONS.find((o) => o.value === policy[cell])?.help}
              >
                {DECISION_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value} title={opt.help}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          );
        })}
      </div>
    </div>
  );
}
