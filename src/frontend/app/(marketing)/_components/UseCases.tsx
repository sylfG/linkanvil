"use client";
import { useCallback, useEffect, useState } from "react";
import useEmblaCarousel from "embla-carousel-react";
import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight } from "lucide-react";

const personas = [
  {
    name: "Marta",
    role: "Investigadora académica",
    color: "from-purple-500/30 to-fuchsia-500/30",
    initial: "M",
    quote:
      "Guardaba papers en 7 sitios distintos. Ahora LinkAnvil sabe cuándo un estudio fue refutado y me lo dice antes de que lo cite.",
    use: "Bibliografía dinámica para tesis doctoral en climatología",
  },
  {
    name: "Joel",
    role: "Periodista freelance",
    color: "from-blue-500/30 to-cyan-500/30",
    initial: "J",
    quote:
      "Mando URLs al bot de Telegram mientras camino. Cuando vuelvo a casa ya están clasificadas, archivadas y listas para consultar.",
    use: "Investigación en movilidad para artículos de fondo",
  },
  {
    name: "Naia",
    role: "Senior developer",
    color: "from-emerald-500/30 to-teal-500/30",
    initial: "N",
    quote:
      "Las docs de v0.1 ya no contaminan mis búsquedas. La colisión semántica las manda a cuarentena sola cuando llego con v0.2.",
    use: "Documentación técnica versionada de stacks",
  },
  {
    name: "Bruno",
    role: "Estudiante de máster",
    color: "from-amber-500/30 to-orange-500/30",
    initial: "B",
    quote:
      "Le pregunto al chat por temas del temario y me responde con extractos de los apuntes y artículos que yo mismo guardé.",
    use: "Repaso interactivo de asignaturas con material propio",
  },
];

export default function UseCases() {
  const [emblaRef, emblaApi] = useEmblaCarousel({
    loop: true,
    align: "start",
    slidesToScroll: 1,
  });
  const [selectedIdx, setSelectedIdx] = useState(0);

  const scrollPrev = useCallback(() => emblaApi?.scrollPrev(), [emblaApi]);
  const scrollNext = useCallback(() => emblaApi?.scrollNext(), [emblaApi]);
  const scrollTo = useCallback(
    (i: number) => emblaApi?.scrollTo(i),
    [emblaApi]
  );

  useEffect(() => {
    if (!emblaApi) return;
    const onSelect = () => setSelectedIdx(emblaApi.selectedScrollSnap());
    onSelect();
    emblaApi.on("select", onSelect);
    return () => {
      emblaApi.off("select", onSelect);
    };
  }, [emblaApi]);

  return (
    <section id="casos" className="py-20 md:py-28 border-t border-border/50">
      <div className="max-w-6xl mx-auto px-5 md:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.5 }}
          className="flex items-end justify-between gap-6 mb-10"
        >
          <div className="max-w-xl">
            <div className="text-xs uppercase tracking-widest text-accent-light font-medium mb-3">
              Casos de uso
            </div>
            <h2 className="text-3xl md:text-4xl font-semibold leading-tight tracking-[-0.02em] text-slate-100">
              No importa qué guardes. Importa qué hagas con ello.
            </h2>
          </div>
          <div className="hidden md:flex items-center gap-2">
            <button
              onClick={scrollPrev}
              aria-label="Anterior"
              className="w-9 h-9 rounded-lg bg-card border border-border hover:border-accent/40 text-muted hover:text-slate-200 transition-colors flex items-center justify-center"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={scrollNext}
              aria-label="Siguiente"
              className="w-9 h-9 rounded-lg bg-card border border-border hover:border-accent/40 text-muted hover:text-slate-200 transition-colors flex items-center justify-center"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </motion.div>

        {/* Embla viewport */}
        <div className="overflow-hidden -mx-5 md:-mx-8 px-5 md:px-8" ref={emblaRef}>
          <div className="flex gap-5">
            {personas.map((p) => (
              <div
                key={p.name}
                className="flex-[0_0_85%] sm:flex-[0_0_60%] lg:flex-[0_0_38%] min-w-0"
              >
                <article className="bg-card border border-border rounded-2xl p-6 h-full flex flex-col">
                  <div className="flex items-center gap-3 mb-4">
                    <div
                      className={`w-12 h-12 rounded-full bg-gradient-to-br ${p.color} border border-border flex items-center justify-center text-slate-100 font-semibold`}
                    >
                      {p.initial}
                    </div>
                    <div>
                      <div className="font-semibold text-sm text-slate-100">
                        {p.name}
                      </div>
                      <div className="text-xs text-muted">{p.role}</div>
                    </div>
                  </div>
                  <blockquote className="text-sm text-slate-200 leading-relaxed mb-4 italic">
                    "{p.quote}"
                  </blockquote>
                  <div className="mt-auto pt-4 border-t border-border/50">
                    <div className="text-[11px] text-muted uppercase tracking-wider mb-1">
                      Uso principal
                    </div>
                    <div className="text-xs text-slate-300">{p.use}</div>
                  </div>
                </article>
              </div>
            ))}
          </div>
        </div>

        {/* Dots */}
        <div className="flex items-center justify-center gap-2 mt-6">
          {personas.map((_, i) => (
            <button
              key={i}
              onClick={() => scrollTo(i)}
              aria-label={`Ir al caso ${i + 1}`}
              className={`h-1.5 rounded-full transition-all ${
                selectedIdx === i ? "w-6 bg-accent-light" : "w-1.5 bg-border"
              }`}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
