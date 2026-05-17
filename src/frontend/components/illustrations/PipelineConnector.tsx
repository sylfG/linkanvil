// SVG decorativo: línea horizontal punteada con gradiente, para
// conectar las 3 cards del "Cómo funciona". Solo visible en desktop
// (md+), en móvil las cards apilan vertical y no necesitan conector.
export default function PipelineConnector() {
  return (
    <div
      aria-hidden
      className="hidden md:block absolute left-0 right-0 top-1/2 -translate-y-1/2 pointer-events-none -z-10"
    >
      <svg className="w-full h-2" viewBox="0 0 800 8" preserveAspectRatio="none">
        <defs>
          <linearGradient id="connector" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#7C3AED" stopOpacity="0" />
            <stop offset="15%" stopColor="#7C3AED" stopOpacity="0.5" />
            <stop offset="50%" stopColor="#8B5CF6" stopOpacity="0.7" />
            <stop offset="85%" stopColor="#7C3AED" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#7C3AED" stopOpacity="0" />
          </linearGradient>
        </defs>
        <line
          x1="0"
          y1="4"
          x2="800"
          y2="4"
          stroke="url(#connector)"
          strokeWidth="1.5"
          strokeDasharray="4 6"
        />
      </svg>
    </div>
  );
}
