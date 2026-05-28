"use client";
import Image from "next/image";

// Logo oficial de LinkAnvil. La PNG es cuadrada (586×586) — funciona en
// cualquier tamaño sin distorsionar. Por defecto usamos la variante para
// fondos oscuros (logo-dark.png) porque toda la app es dark-mode-first.
//
// Centralizamos el componente para que cambiar el asset (rebrand, retina,
// favicon dinámico) sea una sola edición.
export default function Logo({
  size = 32,
  variant = "dark",
  className = "",
  priority = false,
}: {
  size?: number;
  variant?: "dark" | "light";
  className?: string;
  priority?: boolean;
}) {
  const src = variant === "light" ? "/logo-light.png" : "/logo-dark.png";
  return (
    <Image
      src={src}
      alt="LinkAnvil"
      width={size}
      height={size}
      priority={priority}
      className={className}
    />
  );
}
