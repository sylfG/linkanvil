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
    | "recurso.rescatado"
    | "recurso.eliminado";
  recurso_id?: string;
  url?: string;
  titulo?: string;
  motivo?: string;
  created_at?: string;
  // True cuando el evento es local (dispatch tras una acción del
  // usuario) para feedback instantáneo, sin esperar la cadena
  // outbox → RabbitMQ → notifier → Redis → SSE. Los listeners pueden
  // usar este flag para insertar entradas optimistas y deduplicarlas
  // cuando llegue la versión real del backend ~2 s más tarde.
  optimistic?: boolean;
}

type Listener = (ev: ResourceEvent) => void;

interface ResourceStreamCtx {
  subscribe: (cb: Listener) => () => void;
  dispatch: (ev: ResourceEvent) => void;
}

const Ctx = createContext<ResourceStreamCtx | null>(null);

/**
 * Provider con UN solo EventSource hacia /api/resources/stream y
 * fan-out a múltiples suscriptores. Los navegadores limitan a ~6
 * conexiones HTTP/1.1 por origen y cada `useSSE` abría una propia,
 * llegando a colapsar. Centralizar evita el límite y permite además
 * inyectar eventos locales (`dispatch`) tras acciones del usuario,
 * sin esperar a que la cadena outbox→RabbitMQ→notifier→Redis traiga
 * el evento real.
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

  const dispatch = useCallback((ev: ResourceEvent) => {
    listenersRef.current.forEach((cb) => {
      try {
        cb(ev);
      } catch {
        /* un listener fallido no afecta al resto */
      }
    });
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

  return (
    <Ctx.Provider value={{ subscribe, dispatch }}>{children}</Ctx.Provider>
  );
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

/**
 * Hook para inyectar un evento local en el bus tras una acción del
 * usuario (e.g. tras confirmar un modal). Despierta a todos los
 * listeners en el siguiente tick para que actualicen sus contadores y
 * listas sin esperar a la cadena del backend. La cadena real llega
 * 2-3 s después y los listeners deben deduplicar si registran items
 * optimistas en estado local (ver bell).
 */
export function useResourceStreamDispatch() {
  const ctx = useContext(Ctx);
  return ctx?.dispatch ?? (() => {});
}
