import type { ReactNode } from "react";

// Route group PÚBLICO. A diferencia de (app)/layout.tsx no hay guard:
// cualquiera puede ver la landing sin token. Si está logueado, el botón
// principal del Hero cambia a "Ir a tu cerebro" — la landing sigue
// siendo navegable (no force redirect) para que usuarios puedan ver
// cambios de marketing.
export default function MarketingLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-bg text-slate-100 overflow-x-hidden">
      {children}
    </div>
  );
}
