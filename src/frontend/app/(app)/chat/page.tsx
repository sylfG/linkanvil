"use client";
import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send, Bot, User, Zap, Cpu, RefreshCw,
  Copy, Check, Download, ExternalLink, ChevronLeft, Archive, Info,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { API_URL, handleAuthFailure } from "@/lib/api";
import { DemoHint } from "@/components/DemoHint";
import { copyToClipboard } from "@/lib/clipboard";
import { useAuthStore } from "@/lib/auth";
import { useChatStore, type ChatMessage, type RagSource } from "@/lib/chats";

// ── helpers ───────────────────────────────────────────────────────────────────

function CopyBtn({ text }: { text: string }) {
  const [ok, setOk] = useState(false);
  return (
    <button
      onClick={async (e) => { e.stopPropagation(); const done = await copyToClipboard(text); if (done) { setOk(true); setTimeout(() => setOk(false), 1800); } }}
      className="p-1 rounded hover:bg-white/10 text-muted hover:text-slate-300 transition-colors"
      title="Copiar"
    >
      {ok ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

// ── flip card bubble ──────────────────────────────────────────────────────────

function AssistantBubble({ msg, isLast, isStreaming }: { msg: ChatMessage; isLast: boolean; isStreaming: boolean }) {
  const [flipped, setFlipped] = useState(false);
  const [face, setFace] = useState<"front" | "back">("front");
  const hasSources = (msg.sources?.length ?? 0) > 0;

  function flip() {
    if (isStreaming) return;
    const target = face === "front" ? "back" : "front";
    setFlipped(true);
    setTimeout(() => {
      setFace(target);
      setFlipped(false);
    }, 220);
  }

  return (
    <div className="flex gap-3">
      <div className="w-7 h-7 rounded-full bg-slate-700/60 flex items-center justify-center flex-shrink-0 mt-0.5">
        <Bot className="w-4 h-4 text-slate-300" />
      </div>

      <div className="max-w-[80%] flex flex-col gap-1.5">
        {/* Card */}
        <motion.div
          animate={{ rotateY: flipped ? 90 : 0, opacity: flipped ? 0 : 1 }}
          transition={{ duration: 0.22, ease: "easeInOut" }}
          className="relative px-4 py-3 rounded-2xl rounded-tl-sm text-sm leading-relaxed bg-card border border-border text-slate-200 group"
          style={{ perspective: 800 }}
        >
          {/* actions row */}
          <div className="absolute top-2 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            {hasSources && face === "front" && !isStreaming && (
              <button
                onClick={flip}
                className="flex items-center gap-1 px-2 py-0.5 text-[11px] bg-accent/15 hover:bg-accent/25 border border-accent/25 text-accent-light rounded-full transition-colors"
                title="Ver fuentes RAG"
              >
                <ExternalLink className="w-3 h-3" />
                {msg.sources!.length} fuente{msg.sources!.length !== 1 ? "s" : ""}
              </button>
            )}
            {face === "back" && (
              <button
                onClick={flip}
                className="flex items-center gap-1 px-2 py-0.5 text-[11px] bg-slate-700 hover:bg-slate-600 border border-slate-600 text-slate-300 rounded-full transition-colors"
              >
                <ChevronLeft className="w-3 h-3" />
                Respuesta
              </button>
            )}
            {face === "front" && <CopyBtn text={msg.content} />}
          </div>

          {/* Front face: markdown */}
          {face === "front" && (
            <>
              {msg.content ? (
                <div className="prose prose-invert prose-sm max-w-none
                  prose-headings:text-slate-100 prose-headings:font-semibold
                  prose-h1:text-base prose-h2:text-sm prose-h3:text-sm
                  prose-p:text-slate-200 prose-p:leading-relaxed
                  prose-strong:text-slate-100
                  prose-code:text-accent-light prose-code:bg-accent/10 prose-code:px-1 prose-code:rounded prose-code:text-xs prose-code:before:content-none prose-code:after:content-none
                  prose-pre:bg-slate-900 prose-pre:border prose-pre:border-border prose-pre:rounded-lg prose-pre:text-xs
                  prose-a:text-accent-light prose-a:no-underline hover:prose-a:underline
                  prose-ul:pl-4 prose-ol:pl-4 prose-li:text-slate-200
                  prose-blockquote:border-accent/40 prose-blockquote:text-muted
                  prose-hr:border-border pr-20">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              ) : isLast && isStreaming ? (
                <span className="flex gap-1">
                  {[0, 1, 2].map((j) => (
                    <span key={j} className="w-1.5 h-1.5 bg-muted rounded-full animate-pulse-soft" style={{ animationDelay: `${j * 0.2}s` }} />
                  ))}
                </span>
              ) : null}
            </>
          )}

          {/* Back face: sources */}
          {face === "back" && hasSources && (
            <div className="pr-24">
              <p className="text-xs font-semibold text-accent-light mb-2.5">Fuentes RAG utilizadas</p>
              <div className="space-y-1.5 max-h-56 overflow-y-auto">
                {msg.sources!.map((s, i) => (
                  <a
                    key={i}
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-start gap-2 p-1.5 rounded-lg hover:bg-white/5 group/src transition-colors"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <ExternalLink className="w-3 h-3 mt-0.5 flex-shrink-0 text-muted group-hover/src:text-accent-light" />
                    <div className="min-w-0">
                      <p className="text-slate-300 text-xs truncate">{s.title || s.url}</p>
                      <p className="text-muted text-[10px] truncate">{s.url}</p>
                    </div>
                    <span className="ml-auto flex-shrink-0 text-[10px] font-mono text-accent-light/60">{s.score}</span>
                  </a>
                ))}
              </div>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const { token } = useAuthStore();
  const { activeId, createSession, getMessages, setLocalMessages, loadMessages, appendMessages } = useChatStore();
  const [model, setModel] = useState("cerebro-lite");
  const [useRag, setUseRag] = useState(true);
  // Archivo histórico (migración 0007): toggle que incluye recursos en
  // estado 'expirado' al RAG. OFF por defecto: el archivo no contamina
  // la KB activa salvo que el usuario lo pida explícitamente.
  const [useArchive, setUseArchive] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const messages: ChatMessage[] = activeId ? getMessages(activeId) : [];

  // La sesión se crea en lazy desde send() al primer mensaje, así
  // recargar la página sin escribir no genera conversaciones huérfanas.

  // Load messages when active session changes (lazy)
  useEffect(() => {
    if (activeId && token && getMessages(activeId).length === 0) {
      loadMessages(activeId, token).catch(() => {});
    }
  }, [activeId, token]);

  function scrollToBottom() {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  }

  function setMessages(updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) {
    if (!activeId) return;
    const next = typeof updater === "function" ? updater(getMessages(activeId)) : updater;
    setLocalMessages(activeId, next);
  }

  function exportToMarkdown() {
    const lines: string[] = [`# Chat — ${new Date().toLocaleString()}\n`];
    for (const m of messages) {
      lines.push(`## ${m.role === "user" ? "Usuario" : "Asistente"}\n`);
      lines.push(m.content + "\n");
      if (m.sources?.length) {
        lines.push("\n**Fuentes RAG:**");
        for (const s of m.sources) lines.push(`- [${s.title || s.url}](${s.url}) (score: ${s.score})`);
        lines.push("");
      }
    }
    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `chat-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function send() {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");

    let id = activeId;
    if (!id && token) {
      id = await createSession(token);
    }
    if (!id) return;

    const userMsg: ChatMessage = { role: "user", content: text };
    const newMessages: ChatMessage[] = [...getMessages(id), userMsg];
    setLocalMessages(id, newMessages);
    scrollToBottom();
    setStreaming(true);

    const ac = new AbortController();
    abortRef.current = ac;
    setLocalMessages(id, [...newMessages, { role: "assistant", content: "" }]);

    let assistantContent = "";
    let aborted = false;

    try {
      const buildHeaders = (bearer: string | null | undefined): Record<string, string> => {
        const csrf = (typeof document !== "undefined")
          ? ([...document.cookie.matchAll(/(?:^|; )cerebro_csrf=([^;]*)/g)].pop()?.[1] ?? "")
          : "";
        return {
          "Content-Type": "application/json",
          ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
          ...(csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {}),
        };
      };
      const fireChat = (bearer: string | null | undefined) =>
        fetch(`${API_URL}/chat`, {
          method: "POST",
          headers: buildHeaders(bearer),
          credentials: "include",
          body: JSON.stringify({ messages: newMessages, model, use_rag: useRag, include_archive: useArchive }),
          signal: ac.signal,
        });

      let res = await fireChat(token);

      if (res.status === 401) {
        const outcome = await handleAuthFailure(res);
        if (outcome === "logout") throw new Error("Sesión expirada");
        // Refresh succeeded — re-read the rotated token from the store
        // and retry the streaming request once.
        const rotated = useAuthStore.getState().token;
        res = await fireChat(rotated);
      }

      // Migración 0008: 402 BYOK required (usuario registrado sin keys
      // configuradas) y 429 demo_daily_quota_exceeded — los dos llegan
      // como JSON con { detail: { error, message } }. Surface user-friendly.
      if (res.status === 402 || res.status === 429) {
        let detail: any = null;
        try {
          detail = (await res.json())?.detail ?? null;
        } catch {
          /* response body wasn't JSON */
        }
        if (detail?.error === "byok_required") {
          throw new Error(
            "Necesitas configurar tus claves de LLM en Perfil → Claves de LLM antes de chatear.",
          );
        }
        if (detail?.error === "demo_daily_quota_exceeded") {
          throw new Error(
            "El demo público alcanzó su límite diario (20 chats). Regístrate para uso ilimitado con tus propias claves.",
          );
        }
        throw new Error(detail?.message || `HTTP ${res.status}`);
      }

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const reader = res.body!.getReader();
      const dec = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (raw === "[DONE]") break;
          try {
            const parsed = JSON.parse(raw);
            if (parsed.type === "sources") {
              const sources = parsed.sources as RagSource[];
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = { ...updated[updated.length - 1], sources };
                return updated;
              });
              continue;
            }
            if (parsed.type === "error") {
              // Backend signalled an error mid-stream (e.g. upstream LLM
              // failure). Surface it instead of letting the bubble look empty.
              throw new Error(parsed.message || "Error en el stream del modelo.");
            }
            const delta = parsed?.choices?.[0]?.delta?.content ?? "";
            if (delta) {
              assistantContent += delta;
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  ...updated[updated.length - 1],
                  content: updated[updated.length - 1].content + delta,
                };
                return updated;
              });
              scrollToBottom();
            }
          } catch (e) {
            console.warn("SSE chunk parse error:", raw, e);
          }
        }
      }
    } catch (err: any) {
      if (err.name === "AbortError") {
        aborted = true;
      } else {
        // Si el error trae mensaje propio (BYOK/cuota/etc.) lo respetamos.
        // Si no, fallback genérico apuntando al stack LiteLLM.
        const friendlyMsg =
          typeof err?.message === "string" && err.message.length > 0
            ? `⚠️ ${err.message}`
            : "⚠️ Error al conectar con el modelo. Comprueba que LiteLLM esté activo.";
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: friendlyMsg,
          };
          return updated;
        });
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
      scrollToBottom();
      // Persist to Postgres only if stream completed and produced content.
      // Read sources from state (set during stream) rather than via closure.
      if (!aborted && assistantContent && token) {
        const finalMessages = getMessages(id);
        const last = finalMessages[finalMessages.length - 1];
        const assistantMsg: ChatMessage = {
          role: "assistant",
          content: assistantContent,
          sources: last?.role === "assistant" ? last.sources : undefined,
        };
        appendMessages(id, [userMsg, assistantMsg], token).catch(() => {});
      }
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-surface flex-shrink-0 flex-wrap">
        <DemoHint
          label="Demo"
          variant="sparkle"
          hint="Las virtual-keys del demo vienen pre-configuradas con un free-tier limitado. Cuota: 20 chats/día por IP. Las conversaciones se borran al expirar la sesión."
        />
        <label
          className="text-[10px] uppercase tracking-wider text-muted hidden md:inline"
          title="Modelo a usar para la respuesta"
        >
          Modelo
        </label>
        <select
          value={model}
          onChange={(e) => setModel(e.target.value)}
          title="Lite es rápido y suficiente para preguntas cortas. Pro razona mejor preguntas complejas a cambio de latencia."
          className="bg-card border border-border rounded-lg px-3 py-1.5 text-sm text-slate-200 outline-none"
        >
          <option value="cerebro-lite">🚀 Lite — rápido</option>
          <option value="cerebro-pro">🧠 Pro — razonamiento</option>
        </select>

        <button
          onClick={() => setUseRag(!useRag)}
          aria-pressed={useRag}
          title={
            useRag
              ? "RAG activado: cada pregunta busca primero en tu base de conocimiento (Qdrant) y el modelo responde citando las fuentes. Apágalo para chatear solo con conocimiento general del LLM."
              : "RAG desactivado: el modelo responde con su conocimiento general SIN consultar tu KB. Útil para preguntas genéricas o cuando no necesitas citas."
          }
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
            useRag ? "bg-accent/20 border-accent/40 text-accent-light" : "bg-transparent border-border text-muted"
          }`}
        >
          <Zap className="w-3.5 h-3.5" />
          RAG {useRag ? "ON" : "OFF"}
          <Info className="w-3 h-3 opacity-60" />
        </button>

        <button
          onClick={() => setUseArchive(!useArchive)}
          disabled={!useRag}
          aria-pressed={useArchive && useRag}
          title={
            useRag
              ? useArchive
                ? "Archivo activado: el RAG también consulta recursos en estado 'expirado' (archivo histórico). Útil cuando necesitas datos de eventos pasados, post-mortems o referencias antiguas."
                : "Archivo desactivado: el RAG ignora el archivo histórico y solo cita recursos activos. Encendido lo incluye sin tener que rescatarlos."
              : "Archivo requiere RAG activado. Enciende RAG primero."
          }
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
            useArchive && useRag
              ? "bg-amber-500/15 border-amber-400/40 text-amber-300"
              : "bg-transparent border-border text-muted"
          }`}
        >
          <Archive className="w-3.5 h-3.5" />
          Archivo {useArchive && useRag ? "ON" : "OFF"}
          <Info className="w-3 h-3 opacity-60" />
        </button>

        {messages.length > 0 && (
          <>
            <button
              onClick={exportToMarkdown}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-muted hover:text-slate-200 hover:bg-white/5 transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              Exportar
            </button>
            <button
              onClick={() => { if (token) createSession(token).catch(() => {}); }}
              className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-muted hover:text-slate-200 hover:bg-white/5 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Nuevo chat
            </button>
          </>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-4 max-w-md mx-auto">
            <div className="opacity-40">
              <Cpu className="w-12 h-12" />
            </div>
            <p className="text-lg font-medium opacity-80">
              Pregunta a tu segundo cerebro
            </p>
            <p className="text-sm text-muted leading-relaxed">
              Escribe tu pregunta abajo. Las respuestas se generan con el
              modelo seleccionado, y cuando RAG está activado se citan las
              fuentes de tu base de conocimiento.
            </p>

            {/* Mini-leyenda de los toggles, visible siempre que el chat
                esté vacío. Refuerza la idea de "modelos × fuentes" y
                desactiva la sensación de "¿qué hacen estos botones?". */}
            <div className="w-full text-left bg-card border border-border rounded-xl p-4 space-y-2 mt-2">
              <p className="text-[11px] uppercase tracking-wider text-muted font-medium mb-2">
                Toggles arriba — qué hacen
              </p>
              <div className="flex items-start gap-2">
                <Zap className="w-3.5 h-3.5 text-accent-light flex-shrink-0 mt-0.5" />
                <p className="text-xs text-slate-200 leading-relaxed">
                  <strong className="text-accent-light">RAG ON</strong>:
                  cada pregunta busca primero en tu KB (chunks vectoriales
                  en Qdrant) y el modelo cita las fuentes encontradas.
                  Apágalo para chatear solo con el conocimiento general
                  del LLM.
                </p>
              </div>
              <div className="flex items-start gap-2">
                <Archive className="w-3.5 h-3.5 text-amber-300 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-slate-200 leading-relaxed">
                  <strong className="text-amber-300">Archivo ON</strong>:
                  el RAG también incluye recursos en estado{" "}
                  <code className="text-[10px] bg-bg/60 px-1 rounded">
                    expirado
                  </code>{" "}
                  (archivo histórico — post-mortems, eventos pasados, etc.).
                  Requiere RAG activado.
                </p>
              </div>
            </div>
          </div>
        )}

        <AnimatePresence>
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}
            >
              {msg.role === "user" ? (
                <>
                  <div className="w-7 h-7 rounded-full bg-accent/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <User className="w-4 h-4 text-accent-light" />
                  </div>
                  <div className="max-w-[80%] px-4 py-3 rounded-2xl rounded-tr-sm text-sm leading-relaxed bg-accent/20 text-slate-100 group relative">
                    <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <CopyBtn text={msg.content} />
                    </div>
                    <p className="pr-6 whitespace-pre-wrap">{msg.content}</p>
                  </div>
                </>
              ) : (
                <AssistantBubble
                  msg={msg}
                  isLast={i === messages.length - 1}
                  isStreaming={streaming}
                />
              )}
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-border bg-surface flex-shrink-0">
        <div className="flex gap-2 items-end bg-card border border-border rounded-xl p-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
            }}
            rows={1}
            placeholder="Escribe tu pregunta… (Enter para enviar)"
            className="flex-1 bg-transparent text-sm text-slate-100 placeholder-muted outline-none resize-none py-1.5 px-2 max-h-32"
            style={{ minHeight: "36px" }}
          />
          <button
            onClick={send}
            disabled={!input.trim() || streaming}
            className="w-9 h-9 rounded-lg bg-accent hover:bg-accent-hover disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-colors flex-shrink-0"
          >
            <Send className="w-4 h-4 text-white" />
          </button>
        </div>
      </div>
    </div>
  );
}
