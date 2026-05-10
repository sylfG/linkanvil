"use client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
} from "react";

export interface ResourceEvent {
  evento_tipo:
    | "recurso.cuarentena"
    | "recurso.expirado"
    | "recurso.rescatado";
  recurso_id?: string;
  url?: string;
  titulo?: string;
  motivo?: string;
  created_at?: string;
}

type Listener = (ev: ResourceEvent) => void;

interface ResourceStreamCtx {
  subscribe: (cb: Listener) => () => void;
}

const Ctx = createContext<ResourceStreamCtx | null>(null);

/**
 * Provider con UN solo EventSource hacia /api/resources/stream y
 * fan-out a múltiples suscriptores. Los navegadores limitan a ~6
 * conexiones HTTP/1.1 por origen y cada `useSSE` abría una propia,
 * llegando a colapsar (algunas suscripciones se quedan en queue y
 * nunca reciben). Centralizar evita el límite y duplica trabajo.
 */
export function ResourceStreamProvider({
  token,
  children,
}: {
  token: string | null | undefined;
  children: React.ReactNode;
}) {
  const listenersRef = useRef<Set<Listener>>(new Set());

  const subscribe = useCallback((cb: Listener) => {
    listenersRef.current.add(cb);
    return () => {
      listenersRef.current.delete(cb);
    };
  }, []);

  useEffect(() => {
    if (!token) return;
    const url = `/api/resources/stream?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as ResourceEvent & { type?: string };
        if (data.type === "connected") return;
        listenersRef.current.forEach((cb) => {
          try {
            cb(data);
          } catch {
            /* un listener fallido no afecta al resto */
          }
        });
      } catch {
        /* payload no JSON */
      }
    };

    es.onerror = () => {
      // EventSource auto-reconnects; no hacemos nada explícito.
    };

    return () => {
      es.close();
    };
  }, [token]);

  return <Ctx.Provider value={{ subscribe }}>{children}</Ctx.Provider>;
}

/**
 * Hook para suscribirse a los eventos del stream compartido. No abre
 * conexión nueva — simplemente registra/deregistra un callback.
 */
export function useResourceStream(
  _token: string | null | undefined,
  onEvent?: (ev: ResourceEvent) => void,
) {
  const ctx = useContext(Ctx);
  const cbRef = useRef(onEvent);
  cbRef.current = onEvent;

  useEffect(() => {
    if (!ctx || !cbRef.current) return;
    return ctx.subscribe((ev) => {
      cbRef.current?.(ev);
    });
  }, [ctx]);
}
