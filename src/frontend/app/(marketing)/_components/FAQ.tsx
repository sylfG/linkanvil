"use client";
import { motion } from "framer-motion";
import { Plus } from "lucide-react";

const faqs = [
  {
    q: "¿Es self-hosted o un servicio gestionado?",
    a: "LinkAnvil es 100% self-hosted via Docker Compose. Todos los servicios (API, scraper, embedder, base vectorial, LLM proxy) corren en tu infraestructura. Eso te da control absoluto sobre tus datos.",
  },
  {
    q: "¿Qué LLM usa por debajo?",
    a: "Usamos LiteLLM como proxy unificado: puedes conectar OpenAI, Anthropic, NVIDIA NIM, modelos locales (Ollama) o cualquier proveedor compatible. El sistema viene preconfigurado con dos perfiles: cerebro-lite (rápido) y cerebro-pro (mejor razonamiento).",
  },
  {
    q: "¿Funciona con varias personas en la misma instancia?",
    a: "Sí. Arquitectura multi-tenant nativa: cada usuario tiene su propio tenant_id y los datos están aislados a nivel de fila en Postgres + filtrados por tenant en Qdrant. Comparten el mismo recurso global cuando coincide la URL para ahorrar coste de scraping y embedding.",
  },
  {
    q: "¿Mis datos son privados?",
    a: "Toda la base vive en tu Postgres y tu Qdrant. El único componente externo es el LLM al que LiteLLM se conecta — si quieres privacidad total, configura LiteLLM contra un modelo local (Llama 3, Mistral, etc.) y ningún byte sale de tu red.",
  },
  {
    q: "¿Qué pasa con el contenido que ya pasó (eventos viejos, papers retrospectivos)?",
    a: "La policy del tenant decide. Por defecto (preset Equilibrado), contenido pasado con valor archivístico alto se manda al archivo histórico — sigue indexado y recuperable en el chat con el toggle 'Archivo ON'. Contenido pasado de valor medio o nulo va a cuarentena para que tú decidas.",
  },
  {
    q: "¿Cómo empiezo?",
    a: "El demo está listo: visita /login, copia las credenciales que aparecen abajo del formulario y entras a una cuenta con datos sembrados. Si te gusta, crea tu cuenta o despliega tu propia instancia desde el repo público.",
  },
];

export default function FAQ() {
  return (
    <section id="faq" className="py-20 md:py-28 border-t border-border/50">
      <div className="max-w-3xl mx-auto px-5 md:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.5 }}
          className="text-center mb-12"
        >
          <div className="text-xs uppercase tracking-widest text-accent-light font-medium mb-3">
            Preguntas frecuentes
          </div>
          <h2 className="text-3xl md:text-4xl font-semibold leading-tight tracking-[-0.02em] text-slate-100">
            Lo que la gente pregunta primero.
          </h2>
        </motion.div>

        <div className="space-y-3">
          {faqs.map((f, i) => (
            <motion.details
              key={f.q}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-20px" }}
              transition={{ duration: 0.4, delay: i * 0.05 }}
              className="group bg-card border border-border rounded-xl overflow-hidden transition-colors hover:border-accent/30"
            >
              <summary className="flex items-center justify-between gap-4 p-5 cursor-pointer list-none">
                <span className="font-medium text-slate-100 text-sm md:text-base">
                  {f.q}
                </span>
                <Plus className="w-4 h-4 text-muted flex-shrink-0 transition-transform group-open:rotate-45" />
              </summary>
              <div className="px-5 pb-5 text-sm text-muted leading-relaxed">
                {f.a}
              </div>
            </motion.details>
          ))}
        </div>
      </div>
    </section>
  );
}
