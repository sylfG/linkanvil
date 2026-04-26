"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Unhandled error:", error);
  }, [error]);

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center p-6">
      <div className="max-w-md w-full bg-surface border border-border rounded-2xl p-6 space-y-4 text-center">
        <h1 className="text-lg font-semibold text-slate-100">Algo se rompió</h1>
        <p className="text-sm text-muted">
          Ha ocurrido un error inesperado en la aplicación. Puedes intentar
          recargar la sección o volver a la página principal.
        </p>
        {process.env.NODE_ENV !== "production" && error.message && (
          <pre className="text-left text-xs text-red-300 bg-red-900/10 border border-red-900/30 rounded-lg p-3 overflow-auto max-h-40">
            {error.message}
            {error.digest ? `\n\ndigest: ${error.digest}` : ""}
          </pre>
        )}
        <div className="flex gap-2 justify-center">
          <button
            onClick={reset}
            className="px-4 py-2 rounded-lg bg-accent hover:bg-accent-hover text-white text-sm transition-colors"
          >
            Reintentar
          </button>
          <a
            href="/"
            className="px-4 py-2 rounded-lg border border-border text-sm text-slate-200 hover:bg-white/5 transition-colors"
          >
            Volver al inicio
          </a>
        </div>
      </div>
    </div>
  );
}
