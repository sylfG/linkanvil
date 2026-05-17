// Ilustración SVG abstracta: pila de "tarjetas" representando bookmarks
// abandonados. Las del fondo más opacas, las del frente más nítidas pero
// torcidas (sugiriendo desorden). Sin emociones, solo composición
// visual que refuerza el concepto del "cementerio digital".
export default function BookmarkGraveyard() {
  return (
    <svg
      viewBox="0 0 400 300"
      className="w-full h-auto"
      role="img"
      aria-label="Pila desordenada de bookmarks olvidados"
    >
      <defs>
        <linearGradient id="card-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#1C1D2E" />
          <stop offset="100%" stopColor="#13141F" />
        </linearGradient>
        <linearGradient id="card-grad-active" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#2A2B3D" />
          <stop offset="100%" stopColor="#1C1D2E" />
        </linearGradient>
      </defs>

      {/* Fondo de tarjetas dispersas */}
      {[
        { x: 30, y: 60, rot: -8, opacity: 0.35 },
        { x: 220, y: 50, rot: 6, opacity: 0.4 },
        { x: 90, y: 140, rot: -3, opacity: 0.55 },
        { x: 250, y: 130, rot: 9, opacity: 0.5 },
        { x: 50, y: 210, rot: -12, opacity: 0.7 },
        { x: 200, y: 220, rot: 5, opacity: 0.8 },
      ].map((c, i) => (
        <g
          key={i}
          transform={`translate(${c.x},${c.y}) rotate(${c.rot})`}
          opacity={c.opacity}
        >
          <rect
            width="130"
            height="60"
            rx="8"
            fill="url(#card-grad)"
            stroke="#2A2B3D"
            strokeWidth="1"
          />
          <rect x="12" y="14" width="80" height="6" rx="2" fill="#2A2B3D" />
          <rect x="12" y="28" width="50" height="4" rx="2" fill="#2A2B3D" opacity="0.6" />
          <rect x="12" y="40" width="30" height="4" rx="2" fill="#2A2B3D" opacity="0.4" />
        </g>
      ))}

      {/* Tarjeta destacada en accent (la que SÍ se usaría) */}
      <g transform="translate(140, 90) rotate(-2)">
        <rect
          width="130"
          height="60"
          rx="8"
          fill="url(#card-grad-active)"
          stroke="#7C3AED"
          strokeWidth="1.5"
          opacity="0.95"
        />
        <rect x="12" y="14" width="80" height="6" rx="2" fill="#8B5CF6" />
        <rect x="12" y="28" width="60" height="4" rx="2" fill="#8B5CF6" opacity="0.7" />
        <rect x="12" y="40" width="40" height="4" rx="2" fill="#8B5CF6" opacity="0.5" />
        {/* Pequeño "✨" sugerido */}
        <circle cx="115" cy="20" r="3" fill="#8B5CF6" opacity="0.9" />
        <circle cx="118" cy="14" r="1.5" fill="#8B5CF6" opacity="0.7" />
      </g>
    </svg>
  );
}
