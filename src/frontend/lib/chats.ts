"use client";
import { create } from "zustand";
import { apiCall } from "./api";

export interface RagSource {
  title: string;
  url: string;
  score: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: RagSource[];
}

export interface ChatSession {
  id: string;
  title: string;
  updatedAt: number;
}

interface ChatsState {
  sessions: ChatSession[];
  messagesMap: Record<string, ChatMessage[]>;
  activeId: string | null;

  // Sync
  setActive: (id: string | null) => void;
  getActive: () => ChatSession | null;
  getMessages: (id: string) => ChatMessage[];
  setLocalMessages: (id: string, msgs: ChatMessage[]) => void;

  // Async (API-backed)
  init: (token: string) => Promise<void>;
  createSession: (token: string) => Promise<string>;
  deleteSession: (id: string, token: string) => Promise<void>;
  loadMessages: (id: string, token: string) => Promise<void>;
  appendMessages: (id: string, msgs: ChatMessage[], token: string) => Promise<void>;
}

function toSession(s: any): ChatSession {
  return {
    id: s.id,
    title: s.titulo ?? "Nueva conversación",
    updatedAt: new Date(s.ultimo_acceso).getTime(),
  };
}

function toMessage(m: any): ChatMessage {
  return {
    role: m.role as "user" | "assistant",
    content: m.content,
    sources: m.sources?.length ? (m.sources as RagSource[]) : undefined,
  };
}

export const useChatStore = create<ChatsState>()((set, get) => ({
  sessions: [],
  messagesMap: {},
  activeId: null,

  setActive(id) {
    set({ activeId: id });
  },

  getActive() {
    const { sessions, activeId } = get();
    return sessions.find((s) => s.id === activeId) ?? null;
  },

  getMessages(id) {
    return get().messagesMap[id] ?? [];
  },

  setLocalMessages(id, msgs) {
    set((s) => ({ messagesMap: { ...s.messagesMap, [id]: msgs } }));
  },

  async init(token) {
    const data = await apiCall<{ items: any[]; total: number }>("/chats?limit=200", {}, token);
    const sessions = data.items.map(toSession);
    set((s) => {
      const activeId = s.activeId ?? sessions[0]?.id ?? null;
      return { sessions, activeId };
    });
  },

  async createSession(token) {
    const data = await apiCall<any>("/chats", { method: "POST", body: "{}" }, token);
    const session = toSession(data);
    set((s) => ({ sessions: [session, ...s.sessions], activeId: session.id }));
    return session.id;
  },

  async deleteSession(id, token) {
    await apiCall<any>(`/chats/${id}`, { method: "DELETE" }, token);
    set((s) => {
      const sessions = s.sessions.filter((sess) => sess.id !== id);
      const { [id]: _, ...rest } = s.messagesMap;
      return {
        sessions,
        messagesMap: rest,
        activeId: s.activeId === id ? (sessions[0]?.id ?? null) : s.activeId,
      };
    });
  },

  async loadMessages(id, token) {
    const data = await apiCall<any[]>(`/chats/${id}/messages`, {}, token);
    const msgs = data.map(toMessage);
    set((s) => ({ messagesMap: { ...s.messagesMap, [id]: msgs } }));
  },

  async appendMessages(id, msgs, token) {
    const payload = msgs.map((m) => ({
      role: m.role,
      content: m.content,
      sources: m.sources ?? [],
    }));
    await apiCall<any[]>(`/chats/${id}/messages`, {
      method: "POST",
      body: JSON.stringify(payload),
    }, token);
    // Update session title locally from first user message
    const firstUser = msgs.find((m) => m.role === "user");
    if (firstUser) {
      set((s) => ({
        sessions: s.sessions.map((sess) => {
          if (sess.id !== id) return sess;
          const title =
            sess.title === "Nueva conversación"
              ? firstUser.content.slice(0, 50) + (firstUser.content.length > 50 ? "…" : "")
              : sess.title;
          return { ...sess, title, updatedAt: Date.now() };
        }),
      }));
    }
  },
}));
