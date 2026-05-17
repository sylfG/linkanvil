import type { Metadata } from "next";
import Nav from "./_components/Nav";
import Hero from "./_components/Hero";
import Problem from "./_components/Problem";
import Solution from "./_components/Solution";
import HowItWorks from "./_components/HowItWorks";
import Features from "./_components/Features";
import UseCases from "./_components/UseCases";
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
  },
};

// La landing es la cara pública de LinkAnvil. Ensambla 8 secciones más
// nav fijo y footer. Cada sección es server-renderable salvo donde un
// hook cliente (framer-motion, useEmblaCarousel, useAuthStore) lo
// requiere — ahí los componentes hijos llevan "use client".
export default function MarketingPage() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <Problem />
        <Solution />
        <HowItWorks />
        <Features />
        <UseCases />
        <CTABanner />
        <FAQ />
      </main>
      <Footer />
    </>
  );
}
