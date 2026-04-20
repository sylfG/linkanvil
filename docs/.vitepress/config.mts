import { defineConfig } from 'vitepress';
import { withMermaid } from 'vitepress-plugin-mermaid';  // Necesario para diagramas C4/Mermaid

export default withMermaid(
  defineConfig({
    title: "Documentación del Proyecto",
    description: "Sistema centralizado de documentación, arquitectura y backlog de requisitos.",
    lang: 'es-ES',

    // Para GitHub Pages (Ajustar con el nombre del repositorio si es necesario)
    base: '/linkanvil/',
    srcDir: './src',

    ignoreDeadLinks: true,

    mermaid: {
      theme: 'dark'
    },

    themeConfig: {
      socialLinks: [
        { icon: 'github', link: 'https://github.com/sylfG/linkanvil' }
      ],
      nav: [
  {
    'text': 'Inicio',
    'link': '/'
  },
  {
    'text': 'Documentación',
    'link': '/0_0_resumen'
  }
],

      sidebar: [
        {
                'text': '📋 Proyecto',
                'items': [
                        {
                                'text': '📝 Resumen',
                                'link': '/0_0_resumen'
                        },
                        {
                                'text': '📖 Descripción del Proyecto',
                                'link': '/0_descripcion_proyecto'
                        },
                        {
                                'text': '🎯 Épicas y Features',
                                'link': '/1_epics_and_features'
                        },
                        {
                                'text': '🏛️ Arquitectura y Riesgos',
                                'link': '/2_architecture_risks'
                        },
                        {
                                'text': '📐 Diagramas C4',
                                'link': '/3_c4_diagrams'
                        },
                        {
                                'text': '☁️ Resumen de Servicios',
                                'link': '/5_resumen_servicios'
                        },
                        {
                                'text': '🏗️ Arquitectura',
                                'link': '/6_arquitectura'
                        },
                        {
                                'text': '🔄 Ejemplo de Flujo',
                                'link': '/7_ejemplo_flujo'
                        },
                        {
                                'text': '⚙️ Instalación y Configuración',
                                'link': '/8_instalacion_y_configuracion'
                        },
                        {
                                'text': '📝 Log de Auditoría',
                                'link': '/AUDIT_LOG'
                        }
                ]
        },
        {
                'text': '📦 Backlog',
                'collapsed': false,
                'items': [
                        {
                                'text': 'F-00.1 — Configuracion de docker compos',
                                'link': '/backlog/F-00.1_configuracion-de-docker-compos'
                        },
                        {
                                'text': 'F-00.2 — Despliegue de api gateway y pr',
                                'link': '/backlog/F-00.2_despliegue-de-api-gateway-y-pr'
                        },
                        {
                                'text': 'F-00.3 — Configuracion y despliegue del',
                                'link': '/backlog/F-00.3_configuracion-y-despliegue-del'
                        },
                        {
                                'text': 'F-00.4 — Esquemas de base de datos rela',
                                'link': '/backlog/F-00.4_esquemas-de-base-de-datos-rela'
                        },
                        {
                                'text': 'F-00.5 — Despliegue de almacenamiento e',
                                'link': '/backlog/F-00.5_despliegue-de-almacenamiento-e'
                        },
                        {
                                'text': 'F-00.6 — Despliegue de base de datos ve',
                                'link': '/backlog/F-00.6_despliegue-de-base-de-datos-ve'
                        },
                        {
                                'text': 'F-01.1 — Filtro deduplicador en tiempo ',
                                'link': '/backlog/F-01.1_filtro-deduplicador-en-tiempo-'
                        },
                        {
                                'text': 'F-01.2 — Endpoint unificado de ingesta ',
                                'link': '/backlog/F-01.2_endpoint-unificado-de-ingesta-'
                        },
                        {
                                'text': 'F-01.3 — Soporte para captura mediante ',
                                'link': '/backlog/F-01.3_soporte-para-captura-mediante-'
                        },
                        {
                                'text': 'F-01.4 — Soporte para captura mediante ',
                                'link': '/backlog/F-01.4_soporte-para-captura-mediante-'
                        },
                        {
                                'text': 'F-01.5 — Cola de mensajes muertos dlq p',
                                'link': '/backlog/F-01.5_cola-de-mensajes-muertos-dlq-p'
                        },
                        {
                                'text': 'F-02.1 — Scraper de ruteo dinamico patr',
                                'link': '/backlog/F-02.1_scraper-de-ruteo-dinamico-patr'
                        },
                        {
                                'text': 'F-02.2 — Llm gateway con circuit breake',
                                'link': '/backlog/F-02.2_llm-gateway-con-circuit-breake'
                        },
                        {
                                'text': 'F-02.3 — Pipeline zero defect forzar sa',
                                'link': '/backlog/F-02.3_pipeline-zero-defect-forzar-sa'
                        },
                        {
                                'text': 'F-02.4 — Clasificacion inteligente de c',
                                'link': '/backlog/F-02.4_clasificacion-inteligente-de-c'
                        },
                        {
                                'text': 'F-03.1 — Implementacion de patron outbo',
                                'link': '/backlog/F-03.1_implementacion-de-patron-outbo'
                        },
                        {
                                'text': 'F-03.2 — Generacion paralela de embeddi',
                                'link': '/backlog/F-03.2_generacion-paralela-de-embeddi'
                        },
                        {
                                'text': 'F-03.3 — Colisionador semantico en back',
                                'link': '/backlog/F-03.3_colisionador-semantico-en-back'
                        },
                        {
                                'text': 'F-03.4 — Multi tenancy estrutural con a',
                                'link': '/backlog/F-03.4_multi-tenancy-estrutural-con-a'
                        },
                        {
                                'text': 'F-03.5 — Soporte nativo y rapido de exp',
                                'link': '/backlog/F-03.5_soporte-nativo-y-rapido-de-exp'
                        },
                        {
                                'text': 'F-04.1 — Chatbot rag conversacional int',
                                'link': '/backlog/F-04.1_chatbot-rag-conversacional-int'
                        },
                        {
                                'text': 'F-04.2 — Persistencia multi sesion ultr',
                                'link': '/backlog/F-04.2_persistencia-multi-sesion-ultr'
                        },
                        {
                                'text': 'F-04.3 — Panel de control web administr',
                                'link': '/backlog/F-04.3_panel-de-control-web-administr'
                        },
                        {
                                'text': 'F-04.4 — Compactacion de largo contexto',
                                'link': '/backlog/F-04.4_compactacion-de-largo-contexto'
                        },
                        {
                                'text': 'F-04.5 — Function calling activo y sobe',
                                'link': '/backlog/F-04.5_function-calling-activo-y-sobe'
                        },
                        {
                                'text': 'F-05.1 — Auditoria temporal relacional ',
                                'link': '/backlog/F-05.1_auditoria-temporal-relacional-'
                        },
                        {
                                'text': 'F-05.2 — Interfaz en dashboard para ban',
                                'link': '/backlog/F-05.2_interfaz-en-dashboard-para-ban'
                        },
                        {
                                'text': 'F-05.3 — Auditoria exhaustiva basada en',
                                'link': '/backlog/F-05.3_auditoria-exhaustiva-basada-en'
                        },
                        {
                                'text': 'F-06.1 — Instaciacion de opentelemetry ',
                                'link': '/backlog/F-06.1_instaciacion-de-opentelemetry-'
                        },
                        {
                                'text': 'F-06.2 — Exportacion y despliegue del r',
                                'link': '/backlog/F-06.2_exportacion-y-despliegue-del-r'
                        },
                        {
                                'text': 'F-06.3 — Setup monitor activo prometheu',
                                'link': '/backlog/F-06.3_setup-monitor-activo-prometheu'
                        },
                        {
                                'text': 'F-06.4 — Limite automatico estrangulami',
                                'link': '/backlog/F-06.4_limite-automatico-estrangulami'
                        },
                        {
                                'text': 'F-07.1 — Exportacion formato boveda llm wiki',
                                'link': '/backlog/F-07.1_exportacion-formato-boveda-llm-wiki'
                        },
                        {
                                'text': 'F-07.2 — Traduccion aristas a enlaces obsidian',
                                'link': '/backlog/F-07.2_traduccion-aristas-a-enlaces-obsidian'
                        },
                        {
                                'text': 'F-07.3 — Generador de cache caliente hot md',
                                'link': '/backlog/F-07.3_generador-de-cache-caliente-hot-md'
                        },
                        {
                                'text': 'F-08.1 — Sistema de login',
                                'link': '/backlog/F-08.1_sistema-de-login'
                        },
                        {
                                'text': 'F-08.2 — Sistema de roles y tenant unico',
                                'link': '/backlog/F-08.2_sistema-de-roles-y-tenant-unico'
                        },
                        {
                                'text': 'F-09.1 — Soporte multilenguaje',
                                'link': '/backlog/F-09.1_soporte-multilenguaje'
                        },
                        {
                                'text': 'F-09.2 — Integracion accesibilidad',
                                'link': '/backlog/F-09.2_integracion-accesibilidad'
                        }
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
