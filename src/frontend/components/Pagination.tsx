"use client";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationProps {
  page: number;          // 1-indexed
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}

/**
 * Paginador cliente sencillo: prev / indicador / next.
 * Se oculta automáticamente si el total cabe en una sola página.
 */
export function Pagination({ page, pageSize, total, onChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return null;

  const canPrev = page > 1;
  const canNext = page < totalPages;

  return (
    <div className="flex items-center justify-center gap-3 mt-6 select-none">
      <button
        onClick={() => canPrev && onChange(page - 1)}
        disabled={!canPrev}
        aria-label="Página anterior"
        className="p-2 rounded-lg bg-card border border-border text-muted hover:text-slate-100 hover:border-accent/40 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        <ChevronLeft className="w-4 h-4" />
      </button>

      <span className="text-sm text-muted tabular-nums">
        Página <span className="text-slate-200 font-medium">{page}</span> de{" "}
        <span className="text-slate-200 font-medium">{totalPages}</span>
      </span>

      <button
        onClick={() => canNext && onChange(page + 1)}
        disabled={!canNext}
        aria-label="Página siguiente"
        className="p-2 rounded-lg bg-card border border-border text-muted hover:text-slate-100 hover:border-accent/40 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        <ChevronRight className="w-4 h-4" />
      </button>
    </div>
  );
}

export const PAGE_SIZE = 9;
