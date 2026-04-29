"use client";
import { useEffect, useRef, useState } from "react";

export interface IngestEvent {
  recurso_id?: string;
  url: string;
  titulo?: string;
  estado: string;
  type?: string;
}

export function useSSE(url: string | null, onEvent?: (ev: IngestEvent) => void) {
  const [events, setEvents] = useState<IngestEvent[]>([]);
  const esRef = useRef<EventSource | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!url) return;
    const es = new EventSource(url);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const data: IngestEvent = JSON.parse(e.data);
        if (data.type === "connected") return;
        setEvents((prev) => [data, ...prev]);
        onEventRef.current?.(data);
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
