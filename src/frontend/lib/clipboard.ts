"use client";

/**
 * Copy text to the clipboard with a graceful fallback.
 *
 * `navigator.clipboard` only exists on secure contexts (HTTPS, localhost,
 * 127.0.0.1). When the app is served over plain HTTP on a LAN IP — which
 * is how LinkAnvil is accessed during development / homelab use — the
 * Clipboard API is `undefined` and calls throw `Cannot read properties of
 * undefined (reading 'writeText')`. Fall back to the legacy execCommand
 * path, which all current browsers still support precisely for this case.
 *
 * Returns true on success so callers can decide whether to show a
 * confirmation tick or an error toast.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  if (typeof window === "undefined") return false;

  if (navigator?.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Permission denied or transient failure — fall through to legacy.
    }
  }

  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    // Off-screen but inside the layout so iOS Safari accepts the selection.
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "0";
    ta.style.left = "-9999px";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    ta.setSelectionRange(0, text.length);
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}
