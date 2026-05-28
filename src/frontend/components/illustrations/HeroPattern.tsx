// Pattern decorativo del hero: gradient radial sutil + dot grid muy
// tenue. Posicionado absolute para que el hero pueda apilar contenido
// encima sin afectar layout. No SVG por simplicidad — pure CSS.
export default function HeroPattern() {
  return (
    <>
      {/* Gradient radial púrpura desde arriba-izquierda */}
      <div
        aria-hidden
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 70% 50% at 30% 20%, rgba(124, 58, 237, 0.18), transparent 60%)",
        }}
      />
      {/* Dot grid sutil */}
      <div
        aria-hidden
        className="absolute inset-0 pointer-events-none opacity-[0.07]"
        style={{
          backgroundImage:
            "radial-gradient(circle, #8B5CF6 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />
      {/* Fade hacia el bottom */}
      <div
        aria-hidden
        className="absolute inset-x-0 bottom-0 h-32 pointer-events-none"
        style={{
          background: "linear-gradient(to bottom, transparent, #0D0E17)",
        }}
      />
    </>
  );
}
