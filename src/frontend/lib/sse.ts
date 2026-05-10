"use client";
import { useEffect, useRef, useState } from "react";

export interface IngestEvent {
  recurso_id?: string;
  url: string;
  titulo?: string;
  estado: string;
  type?: string;
}

export function useSSE<T = IngestEvent>(
  url: string | null,
  onEvent?: (ev: T) => void,
) {
  const [events, setEvents] = useState<T[]>([]);
  const esRef = useRef<EventSource | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!url) return;
    const es = new EventSource(url);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as T & { type?: string };
        if (data.type === "connected") return;
        setEvents((prev) => [data as T, ...prev]);
        onEventRef.current?.(data as T);
      } catch {}
    };

    es.onerror = () => {
      // Auto-reconnect is handled by EventSource
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [url]);

  return { events, clear: () => setEvents([]) };
}
