import type { Metadata } from "next";
import Nav from "./_components/Nav";
import Hero from "./_components/Hero";
import VideoIntro from "./_components/VideoIntro";
import Problem from "./_components/Problem";
import Solution from "./_components/Solution";
import HowItWorks from "./_components/HowItWorks";
import RealExamples from "./_components/RealExamples";
import NightlyAudit from "./_components/NightlyAudit";
import CTABanner from "./_components/CTABanner";
import FAQ from "./_components/FAQ";
import Footer from "./_components/Footer";

export const metadata: Metadata = {
  title: "LinkAnvil — Tu segundo cerebro, sin el caos",
  description:
    "Guarda URLs, papers, tutoriales. LinkAnvil los clasifica, archiva y te deja preguntar al chat con tus fuentes. Self-hosted, multi-tenant, RAG con archivo histórico opt-in.",
  openGraph: {
    title: "LinkAnvil — Tu segundo cerebro, sin el caos",
    description:
      "Tu base de conocimiento personal, navegable por significado. Prueba el demo gratis.",
    type: "website",
    images: ["/logo-dark.png"],
  },
};

// La landing es la cara pública de LinkAnvil. Orden de secciones:
//   Hero → VideoIntro → Problem → Solution (6 pilares) → HowItWorks
//   → RealExamples → NightlyAudit → CTABanner → FAQ
//
// Decisiones de composición:
//   - Solution absorbe lo que antes era "Features" (eliminamos la
//     duplicidad — ambas listaban los 6 pilares).
//   - RealExamples va ANTES de NightlyAudit: el lector ve URLs reales
//     clasificadas y entiende qué necesita el cron a continuación.
//   - UseCases (personas) eliminado: los ejemplos reales con URLs
//     comunican mejor el caso de uso que las quotes genéricas.
//
// Cada sección es server-renderable salvo donde un hook cliente
// (framer-motion, useAuthStore) lo requiere — ahí los hijos llevan
// "use client".
export default function MarketingPage() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <VideoIntro />
        <Problem />
        <Solution />
        <HowItWorks />
        <RealExamples />
        <NightlyAudit />
        <CTABanner />
        <FAQ />
      </main>
      <Footer />
    </>
  );
}
