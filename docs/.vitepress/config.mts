import { defineConfig, type DefaultTheme } from "vitepress";
import { withMermaid } from "vitepress-plugin-mermaid";
import { readdirSync, existsSync } from "node:fs";
import { join } from "node:path";

// ---------------------------------------------------------------------------
// Sidebar dinámico — enumeración del backlog del Extractor_de_Requisitos
// ---------------------------------------------------------------------------
//
// El subrepo `Extractor_de_Requisitos/` contiene 54 features distribuidas en
// 10 épicas (E-00 … E-09) bajo `backlog/F-XX.Y_<slug>.md`. Antes el config
// listaba esos paths a mano y se desincronizaba en cuanto alguien añadía o
// renombraba un feature — esta versión los enumera leyendo el filesystem en
// build-time, así VitePress siempre publica lo que realmente existe en disco.
// ---------------------------------------------------------------------------

const SRC_DIR = join(__dirname, "..", "src");
const BACKLOG_DIR = join(SRC_DIR, "Extractor_de_Requisitos", "backlog");

// Nombres "humanos" para cada épica. El número/orden vive aquí, no en el
// filesystem, para que un E-XX sin features todavía aparezca como sección
// vacía durante la planificación.
const EPICS: Array<{ id: string; label: string }> = [
  { id: "00", label: "E-00 · Setup" },
  { id: "01", label: "E-01 · Ingesta" },
  { id: "02", label: "E-02 · Procesamiento IA" },
  { id: "03", label: "E-03 · RAG" },
  { id: "04", label: "E-04 · Chat" },
  { id: "05", label: "E-05 · Curación" },
  { id: "06", label: "E-06 · Observabilidad" },
  { id: "07", label: "E-07 · Offline" },
  { id: "08", label: "E-08 · Auth" },
  { id: "09", label: "E-09 · UX" },
];

/**
 * Convierte `F-01.2_endpoint-unificado-de-ingesta-.md`
 * → "F-01.2 · Endpoint Unificado De Ingesta"
 */
function backlogLabel(filename: string): string {
  const stem = filename.replace(/\.md$/, "");
  const match = stem.match(/^F-(\d{2})\.(\d+)_(.+)$/);
  if (!match) return stem;
  const [, epic, idx, slug] = match;
  const human = slug
    .replace(/[-_]+/g, " ")
    .replace(/\s+$/g, "")
    .replace(/\b\w/g, (c) => c.toUpperCase());
  return `F-${epic}.${idx} · ${human}`;
}

/**
 * Lista los backlogs de una épica en orden natural (F-01.1, F-01.2…F-01.10).
 * Devuelve [] si el directorio backlog no existe (el build no falla).
 */
function backlogItemsForEpic(epicId: string): DefaultTheme.SidebarItem[] {
  if (!existsSync(BACKLOG_DIR)) return [];
  const all = readdirSync(BACKLOG_DIR)
    .filter((f) => f.startsWith(`F-${epicId}.`) && f.endsWith(".md"))
    .sort((a, b) => {
      // Orden numérico real: F-01.10 va después de F-01.2 (no antes).
      const re = /^F-\d{2}\.(\d+)_/;
      const na = parseInt(a.match(re)?.[1] ?? "0", 10);
      const nb = parseInt(b.match(re)?.[1] ?? "0", 10);
      return na - nb;
    });
  return all.map((f) => ({
    text: backlogLabel(f),
    link: `/Extractor_de_Requisitos/backlog/${f.replace(/\.md$/, "")}`,
  }));
}

function buildEpicGroups(): DefaultTheme.SidebarItem[] {
  return EPICS.map(({ id, label }) => ({
    text: label,
    collapsed: true,
    items: backlogItemsForEpic(id),
  }));
}

// ---------------------------------------------------------------------------
// Config principal
// ---------------------------------------------------------------------------

export default withMermaid(
  defineConfig({
    title: "Documentación del Proyecto",
    description:
      "Sistema centralizado de documentación, arquitectura y backlog de requisitos.",
    lang: "es-ES",

    // GitHub Pages — el repo se publica en sylfG.github.io/linkanvil/
    base: "/linkanvil/",
    srcDir: "./src",

    // Drafts archivados: existen en disco pero NO se publican ni aparecen
    // en el sidebar. Es papelera operativa, no documentación.
    srcExclude: ["**/old_/**", "**/review/**"],

    ignoreDeadLinks: true,

    mermaid: {
      theme: "dark",
    },

    themeConfig: {
      logo: { light: "/logo-light.png", dark: "/logo-dark.png" },
      siteTitle: "LinkAnvil",
      socialLinks: [
        { icon: "github", link: "https://github.com/sylfG/linkanvil" },
      ],

      nav: [
        { text: "Inicio", link: "/" },
        { text: "Documentación", link: "/0-resumen" },
        { text: "Extracción de requisitos", link: "/Extractor_de_Requisitos/" },
      ],

      sidebar: [
        {
          text: "📋 Proyecto",
          collapsed: false,
          items: [
            { text: "0 · Resumen", link: "/0-resumen" },
            { text: "1 · Instalación y configuración", link: "/1-instalacion-configuracion" },
            { text: "2 · Catálogo de servicios", link: "/2-resumen-servicios" },
            { text: "3 · Componentes", link: "/3-componentes" },
            { text: "4 · Arquitectura", link: "/4-arquitectura" },
            { text: "5 · Herramientas IA", link: "/5-herramientas-ia" },
            { text: "7 · Prompts del sistema", link: "/7-prompts" },
            { text: "8 · Ciclo de vida", link: "/8-lifecycle" },
            { text: "9 · Ejemplo completo de flujo", link: "/9-ejemplo_flujo" },
            { text: "10 · Demo público", link: "/10-demo" },
            { text: "11 · Glosario", link: "/11-Glosario" },
          ],
        },
        {
          text: "🧭 Extracción de requisitos",
          collapsed: true,
          items: [
            { text: "Cómo se usó", link: "/Extractor_de_Requisitos/" },
            { text: "0 · Contexto bruto", link: "/Extractor_de_Requisitos/0_descripcion_proyecto" },
            { text: "1 · Épicas y features", link: "/Extractor_de_Requisitos/1_epics_and_features" },
            { text: "2 · Riesgos y ADRs", link: "/Extractor_de_Requisitos/2_architecture_risks" },
            { text: "3 · Diagramas C4", link: "/Extractor_de_Requisitos/3_c4_diagrams" },
            { text: "Audit log", link: "/Extractor_de_Requisitos/AUDIT_LOG" },
            ...buildEpicGroups(),
          ],
        },
      ],

      outline: { level: [2, 3], label: "En esta página" },
      docFooter: { prev: "Anterior", next: "Siguiente" },
    },
  }),
);
