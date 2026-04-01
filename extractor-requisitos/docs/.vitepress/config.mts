import { defineConfig } from 'vitepress';
import { withMermaid } from 'vitepress-plugin-mermaid';  // Necesario para diagramas C4/Mermaid

export default withMermaid(
  defineConfig({
    title: "Documentación del Proyecto",
    description: "Sistema centralizado de documentación, arquitectura y backlog de requisitos.",
    lang: 'es-ES',

    // Para GitHub Pages (Ajustar con el nombre del repositorio si es necesario)
    // base: '/nombre-del-repositorio/',
    srcDir: './src',

    ignoreDeadLinks: true,

    mermaid: {
      theme: 'dark'
    },

    themeConfig: {
      nav: [
        { text: 'Inicio', link: '/' },
        { text: 'Épicas y Features', link: '/1_epics_and_features' },
        { text: 'Arquitectura', link: '/2_architecture_risks' },
        { text: 'Auditoría', link: '/AUDIT_LOG' },
      ],

      sidebar: [
        // ── Documentación del proyecto ──────────────────────────────────────
        {
          text: '📋 Proyecto',
          items: [
            { text: '📖 Descripción del Proyecto', link: '/0_descripcion_proyecto' },
            { text: '🎯 Épicas y Features', link: '/1_epics_and_features' },
            { text: '🏛️ Arquitectura y Riesgos (STRIDE)', link: '/2_architecture_risks' },
            { text: '📐 Diagramas C4 Model', link: '/3_c4_diagrams' },
            { text: '📋 Registro de Auditoría', link: '/AUDIT_LOG' },
          ]
        },

        // ── Backlog ─────────────────────────────────────────────────────────
        {
          text: '📦 Backlog',
          collapsed: false,
          items: [
            // Aquí se irán añadiendo los enlaces a las historias de usuario / requisitos
            // Ejemplo: { text: 'F-XX.X — Nombre de la feature', link: '/backlog/archivo_ejemplo' },
          ]
        }
      ],

      socialLinks: [
        { icon: 'github', link: 'https://github.com/usuario/repositorio' }
      ],

      footer: {
        message: 'Documentación Técnica y Backlog',
        copyright: 'Copyright © 2026 — Generado con Extractor de Requisitos Autónomo'
      },

      search: {
        provider: 'local'
      },

      editLink: {
        pattern: 'https://github.com/usuario/repositorio/edit/main/docs/:path',
        text: 'Editar esta página en GitHub'
      },

      lastUpdated: {
        text: 'Última actualización',
        formatOptions: {
          dateStyle: 'short',
          timeStyle: 'short'
        }
      }
    }
  })
)
