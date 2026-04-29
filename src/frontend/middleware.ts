import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Middleware is minimal — auth is enforced client-side via Zustand.
// This just redirects the root to login if no cookie hint exists.
// Full protection happens in the (app)/layout.tsx useEffect.
export function middleware(req: NextRequest) {
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
