"use client";

import { useEffect } from "react";

export default function AppSectionError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("App section error:", error);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center h-full p-6 gap-4 text-center">
      <h2 className="text-base font-semibold text-slate-100">No pudimos cargar esta sección</h2>
      <p className="text-sm text-muted max-w-sm">
        El servidor o tu conexión devolvieron un error. Reintenta o navega a
        otra sección desde el menú lateral.
      </p>
      {process.env.NODE_ENV !== "production" && error.message && (
        <pre className="text-left text-xs text-red-300 bg-red-900/10 border border-red-900/30 rounded-lg p-3 overflow-auto max-h-32 max-w-md">
          {error.message}
        </pre>
      )}
      <button
        onClick={reset}
        className="px-4 py-2 rounded-lg bg-accent hover:bg-accent-hover text-white text-sm transition-colors"
      >
        Reintentar
      </button>
    </div>
  );
}
