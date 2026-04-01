# Documento Maestro de Entrada (Contexto Fuente)

Este archivo es la entrada principal del workflow.

Objetivo:

- Recibir informacion bruta del cliente (entrevistas, conversaciones, notas, correos, actas, tickets, enlaces).
- Permitir que la IA extraiga requisitos y genere automaticamente las fases posteriores.

Regla clave:

- No escribir aqui requisitos ya procesados (no epics, no features, no backlog).
- Aqui solo se guarda contexto fuente y datos operativos minimos.

---

## Reglas de Uso

- Mantener encabezados 0 a 10 sin renombrar.
- Pegar informacion lo mas literal posible cuando venga del cliente.
- Si algo no existe, escribir: No disponible.
- Si un dato no aplica, escribir: No aplica (motivo).
- Actualizar fecha y version en cada cambio.

---

## 0. Datos Operativos del Proyecto (Obligatorio)

| Campo | Valor |
| --- | --- |
| Nombre del proyecto | [Completar] |
| Codigo interno (si existe) | [Completar] |
| Fecha ultima actualizacion (YYYY-MM-DD) | [Completar] |
| Responsable funcional | [Completar] |
| Responsable tecnico | [Completar] |
| Estado del discovery (`Borrador`, `En captura`, `Listo para extraccion IA`) | [Completar] |

---

## 1. Contexto GitHub (Obligatorio para Fase 6)

| Campo | Valor | Ejemplo |
| --- | --- | --- |
| URL del repositorio | [Completar] | <https://github.com/mi-org/mi-repo> |
| Repositorio (`OWNER/REPO`) | [Completar] | mi-org/mi-repo |
| Organizacion GitHub | [Completar] | mi-org |
| GitHub Project Number (numero) | [Completar] | 14 |
| Publicar milestones por epica (`Si` o `No`) | [Completar] | Si |
| Vincular dependencias nativas (`Si` o `No`) | [Completar] | Si |

Prerequisitos tecnicos (check rapido):

- gh CLI autenticado.
- jq instalado.
- GitHub Project con campo Priority (`Must`, `Should`, `Could`).

---

## 2. Inventario de Fuentes de Contexto (Obligatorio)

Anotar todas las fuentes desde las que la IA debe extraer requisitos.

| ID | Tipo de fuente | Fecha | Autor/Origen | Estado (`Pendiente`, `Procesada`) | Ubicacion o referencia |
| --- | --- | --- | --- | --- | --- |
| SRC-01 | Entrevista | [Completar] | [Completar] | Pendiente | [Completar] |
| SRC-02 | Conversacion | [Completar] | [Completar] | Pendiente | [Completar] |
| SRC-03 | Documento cliente | [Completar] | [Completar] | Pendiente | [Completar] |

Tipos sugeridos:

- Entrevista
- Conversacion
- Email
- Acta de reunion
- Documento cliente
- Ticketing
- Enlace externo

---

## 3. Contexto Bruto del Cliente (Obligatorio)

Pegar aqui contenido literal o resumido fiel del cliente.

### 3.1 Transcripciones / Conversaciones

[Pegado literal o resumen fiel]

### 3.2 Notas de entrevistas

[Pegado literal o resumen fiel]

### 3.3 Correos / mensajes relevantes

[Pegado literal o resumen fiel]

### 3.4 Documentos externos y enlaces

- [Titulo] - [URL o referencia] - [Resumen de 2-3 lineas]

---

## 4. Hechos Confirmados (sin derivar requisitos) (Obligatorio)

Solo hechos ya confirmados por el cliente. No inferencias.

- Hecho 1: [Completar]
- Hecho 2: [Completar]
- Hecho 3: [Completar]

---

## 5. Restricciones y Condicionantes Conocidos (Obligatorio)

Ejemplos: legales, presupuestarios, tecnologicos, tiempos, dependencias externas.

- Restriccion 1: [Completar]
- Restriccion 2: [Completar]
- Restriccion 3: [Completar]

---

## 6. Supuestos y Huecos de Informacion (Obligatorio)

Este bloque ayuda a la IA a detectar incertidumbre antes de extraer requisitos.

| Tema | Tipo (`Supuesto` o `Dato faltante`) | Impacto (`Alto`, `Medio`, `Bajo`) | Accion para resolver |
| --- | --- | --- | --- |
| [Completar] | Supuesto | Alto | [Completar] |
| [Completar] | Dato faltante | Medio | [Completar] |

---

## 7. Criterios de Extraccion para la IA (Obligatorio)

Definir como quieres que la IA procese las fuentes.

| Parametro | Valor |
| --- | --- |
| Idioma de salida | [Completar] |
| Nivel de detalle esperado (`Alto`, `Medio`, `Bajo`) | [Completar] |
| Priorizar rapidez o exhaustividad (`Rapidez`, `Equilibrado`, `Exhaustivo`) | [Completar] |
| Tolerancia a inferencia (`Minima`, `Moderada`, `Alta`) | [Completar] |
| Enfoque principal (`Negocio`, `Tecnico`, `Mixto`) | [Completar] |

Notas opcionales para el agente:

- [Completar]

---

## 8. Glosario y Terminologia del Cliente (Recomendado)

Terminos de dominio para evitar interpretaciones incorrectas.

| Termino | Definicion del cliente | Sinónimos/alias |
| --- | --- | --- |
| [Completar] | [Completar] | [Completar] |
| [Completar] | [Completar] | [Completar] |

---

## 9. Semaforo por Fase (Control Operativo)

Actualizar solo cuando la informacion minima para una fase este lista.

| Fase | Minimo requerido | Estado (`Pendiente` o `Listo`) |
| --- | --- | --- |
| Fase 1 - Epics y Features | Bloques 0, 2, 3, 4, 6, 7 | Pendiente |
| Fase 2 - Arquitectura y Riesgos | Bloques 0, 3, 5, 6, 7 | Pendiente |
| Fase 3 - Backlog por feature | Bloques 0, 2, 3, 4, 5, 7 | Pendiente |
| Fase 4 - Diagramas C4 | Bloques 0, 3, 5, 7 | Pendiente |
| Fase 5 - Publicacion VitePress | Bloques 0, 9 y artefactos previos aprobados | Pendiente |
| Fase 6 - Subida a GitHub | Bloques 1 y backlog aprobado | Pendiente |

---

## 10. Registro de Cambios y Aprobaciones

| Fecha | Cambio realizado | Responsable | Aprobado por |
| --- | --- | --- | --- |
| [Completar] | Creacion/actualizacion de contexto fuente | [Completar] | [Completar] |
