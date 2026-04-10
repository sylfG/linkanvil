#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# upload_backlog_to_github.sh
#
# Sube todos los archivos de backlog (docs/src/backlog/*.md) a GitHub Issues
# y los añade al GitHub Project con el campo Priority = Must / Should / Could.
#
# PREREQS:
#   - gh CLI >= 2.40  instalado y autenticado  (gh auth status)
#   - jq  instalado  (apt install jq)
#
# USO:
#   bash .github/scripts/upload_backlog_to_github.sh
#   bash .github/scripts/upload_backlog_to_github.sh --dry-run
#   bash .github/scripts/upload_backlog_to_github.sh \
#       --repo OWNER/REPO --project 1
#
# OPCIONES:
#   --repo        OWNER/REPO     Repositorio destino  (default: repo actual)
#   --project     NUMBER         Número de proyecto    (default: $PROJECT_NUMBER)
#   --backlog-dir PATH           Ruta al directorio backlog
#   --dry-run                    Simulación: no crea nada en GitHub
#   --update                     Fuerza update explícito; además está activado por defecto
#   -h, --help                   Muestra esta ayuda
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Valores por defecto ───────────────────────────────────────────────────────
REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "USUARIO/REPO")}"
PROJECT_NUMBER="${PROJECT_NUMBER:-5}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKLOG_DIR="${BACKLOG_DIR:-"$(cd "$SCRIPT_DIR/../../docs/src/backlog" 2>/dev/null && pwd)"}"
PREVENTION_LOG="${PREVENTION_LOG:-"$(cd "$SCRIPT_DIR/../../docs/src" 2>/dev/null && pwd)/ERROR_PREVENTION_LOG.md"}"
DRY_RUN=0
UPDATE=1
SKIP_MILESTONES=0
SKIP_DEPS=0
CURRENT_PHASE="BOOT"
ERROR_RECORDED=0

declare -A FEATURE_TO_ISSUE=()
declare -A FEATURE_TO_NODE=()
declare -A ISSUE_TO_TITLE=()
declare -A EXISTING_TITLE_TO_ISSUE=()
declare -a BACKLOG_FILES=()
declare -a EXCLUDED_BACKLOG_FILES=()

# ── Parse argumentos CLI ──────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)        REPO="$2";           shift 2 ;;
    --project)     PROJECT_NUMBER="$2"; shift 2 ;;
    --backlog-dir) BACKLOG_DIR="$2";    shift 2 ;;
    --dry-run)     DRY_RUN=1;           shift   ;;
    --update)      UPDATE=1;            shift   ;;
    --skip-milestones) SKIP_MILESTONES=1; shift ;;
    --skip-deps)   SKIP_DEPS=1;         shift   ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -30
      exit 0 ;;
    *)
      echo "Opción desconocida: $1  (usa --help para ver las opciones)" >&2
      exit 1 ;;
  esac
done

# ── Colores ANSI ──────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  C_BLUE='\033[1;34m'; C_GREEN='\033[1;32m'
  C_YELLOW='\033[1;33m'; C_RED='\033[1;31m'
  C_GRAY='\033[0;37m'; C_RESET='\033[0m'
else
  C_BLUE=''; C_GREEN=''; C_YELLOW=''; C_RED=''; C_GRAY=''; C_RESET=''
fi

log()  { echo -e "${C_BLUE}[INFO]${C_RESET}  $*"; }
ok()   { echo -e "${C_GREEN}[OK]${C_RESET}    $*"; }
warn() { echo -e "${C_YELLOW}[WARN]${C_RESET}  $*"; }
die()  { echo -e "${C_RED}[ERROR]${C_RESET} $*" >&2; exit 1; }
dim()  { echo -e "${C_GRAY}        $*${C_RESET}"; }

cleanup_file() {
  local file_path="$1"
  [[ -n "$file_path" && -f "$file_path" ]] && rm -f "$file_path"
}

ensure_prevention_log() {
  local dir
  dir="$(dirname "$PREVENTION_LOG")"
  mkdir -p "$dir"
  if [[ ! -f "$PREVENTION_LOG" ]]; then
    cat > "$PREVENTION_LOG" <<'EOF'
# ERROR_PREVENTION_LOG

Registro de lecciones aprendidas para prevenir reincidencias durante la generación y publicación de requisitos.

## Formato de entrada

### YYYY-MM-DD HH:MM — [Fase/Componente]
- Causa raíz:
- Señal de detección:
- Corrección aplicada:
- Regla preventiva:
- Verificación:

---

## Entradas
EOF
  fi
}

append_prevention_entry() {
  local phase="$1" cause="$2" signal="$3" fix="$4" rule="$5" verification="$6"
  ensure_prevention_log
  {
    echo ""
    echo "### $(date '+%Y-%m-%d %H:%M') — [$phase]"
    echo "- Causa raíz: $cause"
    echo "- Señal de detección: $signal"
    echo "- Corrección aplicada: $fix"
    echo "- Regla preventiva: $rule"
    echo "- Verificación: $verification"
  } >> "$PREVENTION_LOG"
}

on_error() {
  local line_no="$1" cmd="$2" exit_code="$3"
  [[ "$ERROR_RECORDED" -eq 1 ]] && return 0
  ERROR_RECORDED=1
  append_prevention_entry \
    "FASE 6 / upload_backlog_to_github.sh / $CURRENT_PHASE" \
    "Error de ejecución en script de publicación" \
    "Comando fallido en línea $line_no con exit_code=$exit_code" \
    "Revisar el comando reportado y corregir el flujo de publicación" \
    "Añadir o ajustar validación previa para impedir reintentos con estado inválido" \
    "Comando: $cmd"
}

trap 'on_error "$LINENO" "$BASH_COMMAND" "$?"' ERR

# ── Mapa categoría → label slug ───────────────────────────────────────────────
category_to_label() {
  case "$1" in
    "UI / Presentation")  echo "ui-presentation" ;;
    "Logic / Business")   echo "logic-business"  ;;
    "Data")               echo "data"            ;;
    "Integration")        echo "integration"     ;;
    "Infrastructure")     echo "infrastructure"  ;;
    "Security")           echo "security"        ;;
    "Observability")      echo "observability"   ;;
    "DX / Tooling")       echo "dx-tooling"      ;;
    "Documentation")      echo "documentation"   ;;
    *)
      warn "Categoría no reconocida: '$1' → usando 'logic-business'"
      echo "logic-business" ;;
  esac
}

# ── Color fijo por label (hex sin #) ──────────────────────────────────────────
label_color() {
  case "$1" in
    "ui-presentation") echo "0075ca" ;;
    "logic-business")  echo "e4e669" ;;
    "data")            echo "d93f0b" ;;
    "integration")     echo "0e8a16" ;;
    "infrastructure")  echo "1d76db" ;;
    "security")        echo "b60205" ;;
    "observability")   echo "5319e7" ;;
    "dx-tooling")      echo "f9d0c4" ;;
    "documentation")   echo "006b75" ;;
    *)                 echo "cccccc" ;;
  esac
}

# ── Crear label si no existe ──────────────────────────────────────────────────
# Usa --force para actualizar el color si ya existe con otro.
# Acepta un segundo argumento opcional (color hex) para labels ad-hoc.
ensure_label() {
  local label="$1"
  local color="${2:-$(label_color "$label")}"
  dim "Verificando label '$label'..."
  [[ "$DRY_RUN" -eq 0 ]] && \
    gh label create "$label" \
      --repo "$REPO" \
      --color "$color" \
      --force 2>/dev/null || true
}

# ── Extraer épica de un archivo MD ───────────────────────────────────────────
# **Épica:** EPIC-00 — Setup e Infraestructura Base  →  "EPIC-00 — Setup e Infraestructura Base"
extract_epic() {
  grep -Em1 '\*\*[EÉ]pica:\*\*' "$1" 2>/dev/null \
    | sed 's/.*\*\*[EÉ]pica:\*\*[[:space:]]*//' \
    | sed 's/^[[:space:]]*//' \
    | tr -d '\r' \
    | cut -c 1-45 \
    | sed 's/[[:space:]]*$//' || true
}

# ── Extraer ID de feature del nombre de archivo ───────────────────────────────
# F-00.1_setup_laravel_livewire.md  →  F-00.1
extract_feature_id() {
  basename "$1" | grep -oE '^F-[0-9]+\.[0-9]+' || true
}

# ── Crear o reutilizar milestone por título de épica ─────────────────────────
ensure_milestone() {
  local title="$1"
  [[ -z "$title" ]] && return 0

  local existing
  existing=$(gh api "/repos/$REPO/milestones?state=all&per_page=100" \
    -q ".[] | select(.title == \"$title\") | .number" 2>/dev/null | head -1 || true)

  if [[ -n "$existing" ]]; then
    dim "  Milestone existente: '$title' (#$existing)" >&2
    echo "$existing"
    return 0
  fi

  local new_num
  new_num=$(gh api --method POST "/repos/$REPO/milestones" \
    -f title="$title" \
    -f state="open" \
    -q '.number' 2>/dev/null || echo "")

  if [[ -n "$new_num" && "$new_num" != "null" ]]; then
    ok "  Milestone creado: '$title' (#$new_num)" >&2
    echo "$new_num"
    return 0
  else
    warn "  No se pudo crear el milestone: '$title'" >&2
    return 1
  fi
}

# ── Extraer dependencias de un archivo MD ────────────────────────────────────
# Lee la sección "## 📦 Dependencias" y extrae las filas de la tabla.
# Salida: una línea por dependencia con formato "F-XX.Y:Sí" o "F-XX.Y:No"
extract_dependencies() {
  local f="$1"
  local in_deps=0

  while IFS= read -r line; do
    # Detectar inicio de sección dependencias
    if [[ "$line" =~ ^##[[:space:]].*Dependencias ]]; then
      in_deps=1
      continue
    fi
    # Fin de sección al encontrar otra sección ## o **Prioridad:**
    if [[ "$in_deps" -eq 1 ]]; then
      if [[ "$line" =~ ^##[[:space:]] || "$line" =~ ^\*\*Prioridad:\*\* || "$line" =~ ^---$ ]]; then
        break
      fi
      # Procesar solo filas de tabla que contienen una referencia a F-
      if [[ "$line" =~ ^\|.*\[F-[0-9] ]]; then
        local dep_id bloqueante ncols
        dep_id=$(echo "$line" | grep -oE '\[F-[0-9]+\.[0-9]+\]' | tr -d '[]' | head -1)
        # Contar separadores '|' para determinar número de columnas de datos
        ncols=$(echo "$line" | tr -cd '|' | wc -c)
        if [[ "$ncols" -ge 4 ]]; then
          # Formato 3 columnas: |Backlog|Motivo|Bloqueante|
          bloqueante=$(echo "$line" | awk -F'|' '{gsub(/[[:space:]]/,"",$4); print $4}' | tr -d '\r')
        else
          bloqueante="No"
        fi
        if [[ -n "$dep_id" ]]; then
          if [[ "$bloqueante" =~ ^([Ss][íi]|SI|YES|yes|true|True|✅)$ ]]; then
            echo "${dep_id}:Sí"
          else
            echo "${dep_id}:No"
          fi
        fi
      fi
    fi
  done < "$f"
}

# ── Construir body del issue sin la sección de dependencias ──────────────────
build_issue_body() {
  local source_file="$1"
  local temp_file
  local skip_section=0

  temp_file=$(mktemp)

  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^##[[:space:]].*Dependencias || "$line" =~ ^\*\*Notas:\*\* ]]; then
      skip_section=1
      continue
    fi

    if [[ "$skip_section" -eq 1 ]]; then
      if [[ "$line" =~ ^##[[:space:]] || "$line" =~ ^\*\*Prioridad:\*\* || "$line" =~ ^\*\*MoSCoW:\*\* || "$line" =~ ^\*\*Sprint:\*\* || "$line" =~ ^---$ ]]; then
        skip_section=0
      else
        continue
      fi
    fi

    printf '%s\n' "$line" >> "$temp_file"
  done < "$source_file"

  echo "$temp_file"
}

# ── Relación parent/sub-issue usando GraphQL oficial ─────────────────────────
add_sub_issue_relationship() {
  local parent_issue_node="$1" sub_issue_node="$2"
  gh api graphql \
    -H 'GraphQL-Features: sub_issues' \
    -f query='mutation($issueId: ID!, $subIssueId: ID!) {
      addSubIssue(input: {
        issueId: $issueId
        subIssueId: $subIssueId
        replaceParent: true
      }) {
        issue { id }
        subIssue { id }
      }
    }' \
    -F issueId="$parent_issue_node" \
    -F subIssueId="$sub_issue_node" \
    > /dev/null 2>&1 || true
}

# ── Relación blocked by usando GraphQL oficial ────────────────────────────────
add_blocked_by_relationship() {
  local issue_node="$1" blocking_issue_node="$2"
  gh api graphql \
    -f query='mutation($issueId: ID!, $blockingIssueId: ID!) {
      addBlockedBy(input: {
        issueId: $issueId
        blockingIssueId: $blockingIssueId
      }) {
        issue { id }
        blockingIssue { id }
      }
    }' \
    -F issueId="$issue_node" \
    -F blockingIssueId="$blocking_issue_node" \
    > /dev/null 2>&1 || true
}

# ── GraphQL: ID de nodo del proyecto ─────────────────────────────────────────
get_project_node_id() {
  local owner="${REPO%%/*}"
  local node_id=""

  # El cliente especificó que a veces es Usuario en vez de Organización.
  # Intentar como usuario primero
  node_id=$(gh api graphql \
    -f query='
      query($owner: String!, $n: Int!) {
        user(login: $owner) {
          projectV2(number: $n) { id }
        }
      }' \
    -F owner="$owner" \
    -F n="$PROJECT_NUMBER" \
    -q '.data.user.projectV2.id' 2>/dev/null || echo "")

  # Si github devuelve el JSON de error (contiene "errors"), lo limpiamos
  if [[ "$node_id" =~ "errors" || "$node_id" =~ "{" ]]; then
    node_id=""
  fi

  # Si falla, intentar como organización
  if [[ -z "$node_id" || "$node_id" == "null" ]]; then
    node_id=$(gh api graphql \
      -f query='
        query($owner: String!, $n: Int!) {
          organization(login: $owner) {
            projectV2(number: $n) { id }
          }
        }' \
      -F owner="$owner" \
      -F n="$PROJECT_NUMBER" \
      -q '.data.organization.projectV2.id' 2>/dev/null || echo "")
  fi
  
  # Limpieza final por si el gh api filtra un json de error
  if [[ "$node_id" =~ "errors" || "$node_id" =~ "{" ]]; then
    node_id=""
  fi

  echo "$node_id"
}

# ── GraphQL: ID del campo Priority ───────────────────────────────────────────
get_priority_field_id() {
  local pid="$1"
  gh api graphql \
    -f query='
      query($id: ID!) {
        node(id: $id) {
          ... on ProjectV2 {
            fields(first: 30) {
              nodes {
                ... on ProjectV2SingleSelectField { id name }
              }
            }
          }
        }
      }' \
    -F id="$pid" \
    -q '.data.node.fields.nodes[] | select(.name == "Priority") | .id'
}

# ── GraphQL: opciones actuales del campo Priority ────────────────────────────
get_priority_options_json() {
  local pid="$1"
  gh api graphql \
    -f query='
      query($id: ID!) {
        node(id: $id) {
          ... on ProjectV2 {
            fields(first: 30) {
              nodes {
                ... on ProjectV2SingleSelectField {
                  id
                  name
                  options { id name color }
                }
              }
            }
          }
        }
      }' \
    -F id="$pid" \
    -q '.data.node.fields.nodes[] | select(.name == "Priority") | .options'
}

# ── Migrar opciones Priority 0/1/2 → Must/Should/Could ──────────────────────
migrate_priority_options() {
  local project_id="$1" field_id="$2"
  local options_json zero_id one_id two_id
  local p0_id p1_id p2_id
  local must_id should_id could_id

  options_json=$(get_priority_options_json "$project_id")
  [[ -n "$options_json" && "$options_json" != "null" ]] \
    || die "No se pudieron leer las opciones del campo 'Priority'."

  zero_id=$(echo "$options_json" | jq -r '.[] | select(.name == "0") | .id' | head -1)
  one_id=$(echo "$options_json" | jq -r '.[] | select(.name == "1") | .id' | head -1)
  two_id=$(echo "$options_json" | jq -r '.[] | select(.name == "2") | .id' | head -1)

  p0_id=$(echo "$options_json" | jq -r '.[] | select(.name == "P0") | .id' | head -1)
  p1_id=$(echo "$options_json" | jq -r '.[] | select(.name == "P1") | .id' | head -1)
  p2_id=$(echo "$options_json" | jq -r '.[] | select(.name == "P2") | .id' | head -1)

  must_id=$(echo "$options_json" | jq -r '.[] | select(.name == "Must") | .id' | head -1)
  should_id=$(echo "$options_json" | jq -r '.[] | select(.name == "Should") | .id' | head -1)
  could_id=$(echo "$options_json" | jq -r '.[] | select(.name == "Could") | .id' | head -1)

  if [[ -n "$must_id" && -n "$should_id" && -n "$could_id" ]]; then
    log "Priority ya normalizada: Must / Should / Could"
    return 0
  fi

  [[ -z "$zero_id" && -n "$p0_id" ]] && zero_id="$p0_id"
  [[ -z "$one_id" && -n "$p1_id" ]] && one_id="$p1_id"
  [[ -z "$two_id" && -n "$p2_id" ]] && two_id="$p2_id"

  if [[ -z "$zero_id" || -z "$one_id" || -z "$two_id" ]]; then
    die "El campo 'Priority' no contiene las opciones esperadas. Debe tener 0/1/2, P0/P1/P2 o Must/Should/Could."
  fi

  log "Migrando Priority a Must/Should/Could"
  gh api graphql \
    -f query='mutation($fieldId: ID!) {
      updateProjectV2Field(input: {
        fieldId: $fieldId
        name: "Priority"
        singleSelectOptions: [
          { name: "Must", color: RED, description: "Must have" }
          { name: "Should", color: YELLOW, description: "Should have" }
          { name: "Could", color: BLUE, description: "Could have" }
        ]
      }) {
        projectV2Field {
          ... on ProjectV2SingleSelectField { id name }
        }
      }
    }' \
    -F fieldId="$field_id" \
    > /dev/null \
    || die "No se pudo migrar el campo 'Priority' a Must/Should/Could."

  ok "Priority migrada correctamente a Must / Should / Could"
}

# ── GraphQL: ID de opción (Must / Should / Could) ─────────────────────────────
get_priority_option_id() {
  local pid="$1" value="$2"
  gh api graphql \
    -f query='
      query($id: ID!) {
        node(id: $id) {
          ... on ProjectV2 {
            fields(first: 30) {
              nodes {
                ... on ProjectV2SingleSelectField {
                  name
                  options { id name }
                }
              }
            }
          }
        }
      }' \
    -F id="$pid" \
    -q ".data.node.fields.nodes[]
        | select(.name == \"Priority\")
        | .options[]
        | select(.name == \"$value\")
        | .id"
}

# ── GraphQL: obtener item existente del proyecto para un issue ───────────────
get_project_item_id_for_issue() {
  local pid="$1" issue_node="$2"
  gh api graphql \
    -f query='query($projectId: ID!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          items(first: 100) {
            nodes {
              id
              content {
                ... on Issue { id }
              }
            }
          }
        }
      }
    }' \
    -F projectId="$pid" \
    -q '.data.node.items.nodes[] | select(.content.id == "'"$issue_node"'") | .id' \
    2>/dev/null | head -1 || true
}

# ── GraphQL: añadir item al proyecto y asignar Priority ──────────────────────
add_to_project_with_priority() {
  local pid="$1" issue_node="$2" field_id="$3" option_id="$4"

  local item_id=""
  if ! item_id=$(gh api graphql \
    -f query='
      mutation($p: ID!, $c: ID!) {
        addProjectV2ItemById(input: { projectId: $p, contentId: $c }) {
          item { id }
        }
      }' \
    -F p="$pid" -F c="$issue_node" \
    -q '.data.addProjectV2ItemById.item.id' 2>/dev/null); then
    item_id=""
  fi

  if [[ -z "$item_id" || "$item_id" == "null" ]]; then
    item_id=$(get_project_item_id_for_issue "$pid" "$issue_node")
  fi

  [[ -n "$item_id" && "$item_id" != "null" ]] || {
    warn "No se pudo obtener el item del proyecto para asignar Priority"
    return 1
  }

  gh api graphql \
    -f query='
      mutation($p: ID!, $i: ID!, $f: ID!, $o: String!) {
        updateProjectV2ItemFieldValue(input: {
          projectId: $p, itemId: $i,
          fieldId: $f, value: { singleSelectOptionId: $o }
        }) {
          projectV2Item { id }
        }
      }' \
    -F p="$pid" -F i="$item_id" -F f="$field_id" -f o="$option_id" \
    > /dev/null
}

# ── Extraer metadatos de un archivo MD ───────────────────────────────────────

# Línea 1: # [CATEGORÍA] ID — Título
extract_title() {
  head -1 "$1" | sed 's/^# //'
}

# **Categoría:** `UI / Presentation`
extract_category() {
  grep -Em1 '\*\*Categoría:\*\*' "$1" 2>/dev/null \
    | cut -d'`' -f2
}

# Acepta tanto **Prioridad:** `Must` como **MoSCoW:** `MUST`
extract_priority() {
  local raw
  raw=$(grep -Em1 '\*\*Prioridad:\*\*|\*\*MoSCoW:\*\*' "$1" 2>/dev/null \
        | cut -d'`' -f2 \
        | tr '[:lower:]' '[:upper:]' \
        || true)
  case "$raw" in
    MUST)   echo "Must"   ;;
    SHOULD) echo "Should" ;;
    COULD)  echo "Could"  ;;
    "WON'T"|WONT|"WON'T HAVE"|"WONT HAVE") echo "Could" ;;
    *)      echo "Should" ;;   # fallback seguro
  esac
}

normalize_priority_raw() {
  local raw="$1"
  case "$raw" in
    MUST) echo "Must" ;;
    SHOULD) echo "Should" ;;
    COULD) echo "Could" ;;
    "WON'T"|WONT|"WON'T HAVE"|"WONT HAVE") echo "Could" ;;
    *) echo "" ;;
  esac
}

is_excluded_backlog_file() {
  local base
  base="$(basename "$1" | tr '[:upper:]' '[:lower:]')"
  [[ "$base" =~ ^f-00\.0_ ]] || [[ "$base" =~ (ejemplo|example) ]]
}

collect_backlog_files() {
  BACKLOG_FILES=()
  EXCLUDED_BACKLOG_FILES=()

  local f
  for f in "$BACKLOG_DIR"/*.md; do
    [[ -f "$f" ]] || continue
    if is_excluded_backlog_file "$f"; then
      EXCLUDED_BACKLOG_FILES+=("$f")
      continue
    fi
    BACKLOG_FILES+=("$f")
  done
}

validate_backlog_files() {
  local errors=0 warnings=0 f raw pr dep_count
  for f in "${BACKLOG_FILES[@]}"; do

    if grep -Eq '\[CATEGORÍA\]|\[Título|\[Nombre del escenario\]|\[rol del usuario|\[acción concreta|INSTRUCCIONES PARA LA IA' "$f"; then
      warn "Plantilla sin completar detectada: $(basename "$f")"
      (( errors++ )) || true
    fi

    raw=$(grep -Em1 '\*\*Prioridad:\*\*|\*\*MoSCoW:\*\*' "$f" 2>/dev/null | sed -E 's/.*`([^`]+)`.*/\1/' | tr '[:lower:]' '[:upper:]' || true)
    pr=$(normalize_priority_raw "$raw")
    if [[ -z "$pr" ]]; then
      warn "Prioridad inválida en $(basename "$f"): '$raw'"
      (( errors++ )) || true
    fi

    if ! grep -Eq '^##.*Dependencias' "$f"; then
      warn "Falta sección de dependencias en: $(basename "$f")"
      (( errors++ )) || true
    fi

    dep_count=$(extract_dependencies "$f" | wc -l | tr -d ' ')
    if [[ ( "$pr" == "Should" || "$pr" == "Could" ) && "$dep_count" -eq 0 ]]; then
      warn "Backlog $pr sin dependencias declaradas: $(basename "$f")"
      (( warnings++ )) || true
    fi
  done

  [[ "$warnings" -gt 0 ]] && warn "Precheck: $warnings advertencias funcionales (no bloqueantes)"

  if [[ "$errors" -gt 0 ]]; then
    die "Precheck falló: $errors errores detectados en backlogs. Revisa los warnings anteriores."
  fi
}

# ── Obtener número de issue existente con el mismo título (o vacío si no existe)
get_existing_issue_number() {
  local title="$1"
  echo "${EXISTING_TITLE_TO_ISSUE[$title]:-}"
}

# ── Cargar mapa de issues existentes por título ──────────────────────────────
load_existing_issue_map() {
  local issue_number issue_title
  while IFS=$'\t' read -r issue_number issue_title; do
    [[ -z "$issue_number" || -z "$issue_title" ]] && continue
    EXISTING_TITLE_TO_ISSUE["$issue_title"]="$issue_number"
  done < <(
    gh issue list \
      --repo "$REPO" \
      --state all \
      --limit 500 \
      --json number,title \
      -q '.[] | [.number, .title] | @tsv' 2>/dev/null || true
  )
}

# ── Obtener node ID de un issue por su número ─────────────────────────────────
get_issue_node_id() {
  local number="$1"
  gh api graphql \
    -f query='
      query($owner: String!, $repo: String!, $n: Int!) {
        repository(owner: $owner, name: $repo) {
          issue(number: $n) { id }
        }
      }' \
    -F owner="${REPO%%/*}" \
    -F repo="${REPO##*/}" \
    -F n="$number" \
    -q '.data.repository.issue.id'
}

# ── Procesar un único archivo de backlog ──────────────────────────────────────
# Retorna:  0 = creado/actualizado  |  2 = omitido (ya existe)  |  1 = error
# Siempre actualiza LAST_ISSUE_NUMBER con el número del issue (nuevo o existente).
process_file() {
  local f="$1" project_id="$2" field_id="$3"
  LAST_ISSUE_NUMBER=""

  local title category label priority epic issue_body_file
  title=$(extract_title "$f")
  category=$(extract_category "$f")
  priority=$(extract_priority "$f")
  label=$(category_to_label "$category")
  epic=$(extract_epic "$f")
  issue_body_file=$(build_issue_body "$f")

  printf "${C_BLUE}►${C_RESET} %-8s %-18s %s\n" \
    "[$priority]" "[$label]" "$title"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    dim "(dry-run) Issue simulado ✓"
    [[ -n "$epic" ]] && dim "(dry-run) Milestone: $epic"
    cleanup_file "$issue_body_file"
    LAST_ISSUE_NUMBER="0"
    return 0
  fi

  # ── Gestión de Milestone (Épica) ────────────────────────────────────────────
  local -a milestone_flag=()
  if [[ "$SKIP_MILESTONES" -eq 0 && -n "$epic" ]]; then
    dim "  Épica → Milestone: $epic"
    local m_id
    m_id=$(ensure_milestone "$epic")
    if [[ -n "$m_id" ]]; then
      milestone_flag=(--milestone "$m_id")
    fi
  fi

  local existing_number
  existing_number=$(get_existing_issue_number "$title")

  if [[ -n "$existing_number" ]]; then
    LAST_ISSUE_NUMBER="$existing_number"
    if [[ "$UPDATE" -eq 1 ]]; then
      dim "  Actualizando body del issue #$existing_number..."
      gh issue edit "$existing_number" \
        --repo "$REPO" \
        --body-file "$issue_body_file" \
        "${milestone_flag[@]}" > /dev/null
      local issue_node option_id
      issue_node=$(get_issue_node_id "$existing_number")
      option_id=$(get_priority_option_id "$project_id" "$priority")
      add_to_project_with_priority \
        "$project_id" "$issue_node" "$field_id" "$option_id"
      EXISTING_TITLE_TO_ISSUE["$title"]="$existing_number"
      cleanup_file "$issue_body_file"
      ok "  Issue #$existing_number actualizado  →  Priority: $priority"
      return 0
    else
      cleanup_file "$issue_body_file"
      warn "  Issue ya existente #$existing_number — omitido (usa --update para actualizar)"
      return 2
    fi
  fi

  ensure_label "$label"

  local issue_url issue_number issue_node option_id
  issue_url=$(gh issue create \
    --repo "$REPO" \
    --title "$title" \
    --label "$label" \
    --body-file "$issue_body_file" \
    "${milestone_flag[@]}")

  issue_number=$(echo "$issue_url" | grep -o '[0-9]*$')
  LAST_ISSUE_NUMBER="$issue_number"
  issue_node=$(get_issue_node_id "$issue_number")
  EXISTING_TITLE_TO_ISSUE["$title"]="$issue_number"

  option_id=$(get_priority_option_id "$project_id" "$priority")

  add_to_project_with_priority \
    "$project_id" "$issue_node" "$field_id" "$option_id"

  cleanup_file "$issue_body_file"

  local milestone_info=""
  [[ -n "$epic" && "$SKIP_MILESTONES" -eq 0 ]] && milestone_info=" | Milestone: $epic"
  ok "  $issue_url  →  Priority: $priority${milestone_info}"
  return 0
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  # ── Validaciones previas ────────────────────────────────────────────────────
  CURRENT_PHASE="VALIDACIONES_PREVIAS"
  command -v gh  &>/dev/null || die "gh CLI no encontrado. Instala desde: https://cli.github.com"
  command -v jq  &>/dev/null || die "jq no encontrado. Instala con: sudo apt install jq"
  gh auth status &>/dev/null || die "gh CLI no autenticado. Ejecuta: gh auth login"
  [[ -d "$BACKLOG_DIR" ]]    || die "Directorio backlog no encontrado: $BACKLOG_DIR"

  collect_backlog_files
  validate_backlog_files
  load_existing_issue_map

  # ── Cabecera ────────────────────────────────────────────────────────────────
  echo ""
  echo -e "${C_BLUE}══════════════════════════════════════════════════════${C_RESET}"
  echo -e "${C_BLUE}  upload_backlog_to_github.sh${C_RESET}"
  echo -e "${C_BLUE}══════════════════════════════════════════════════════${C_RESET}"
  log "Repositorio   : $REPO"
  log "Project V2 #  : $PROJECT_NUMBER"
  log "Backlog dir   : $BACKLOG_DIR"
  [[ "${#EXCLUDED_BACKLOG_FILES[@]}" -gt 0 ]] && warn "Backlogs excluidos (ejemplo/plantilla): ${#EXCLUDED_BACKLOG_FILES[@]}"
  [[ "$DRY_RUN"         -eq 1 ]] && warn "DRY RUN activado — no se creará nada en GitHub"
  [[ "$UPDATE"          -eq 1 ]] && warn "UPDATE activado — issues existentes serán actualizados"
  [[ "$SKIP_MILESTONES" -eq 1 ]] && warn "SKIP_MILESTONES — se omitirán milestones/épicas"
  [[ "$SKIP_DEPS"       -eq 1 ]] && warn "SKIP_DEPS — se omitirá la vinculación de dependencias"
  echo ""

  # ── Obtener IDs del proyecto ────────────────────────────────────────────────
  CURRENT_PHASE="CONFIG_PROYECTO"
  local project_id field_id
  if [[ "$DRY_RUN" -eq 0 ]]; then
    project_id=$(get_project_node_id) \
      || die "No se pudo obtener el ID del proyecto.\n  ¿Son correctos --org '$ORG' y --project $PROJECT_NUMBER?"
    field_id=$(get_priority_field_id "$project_id") \
      || die "No se encontró el campo 'Priority' en el proyecto.\n  ¿Está creado el campo Single-Select 'Priority'?"
    log "Project node ID  : $project_id"
    log "Priority field   : $field_id"
    migrate_priority_options "$project_id" "$field_id"
  else
    project_id="DRY_PROJECT_ID"
    field_id="DRY_FIELD_ID"
    warn "(dry-run) Normalización de Priority omitida"
  fi
  echo ""

  # ── Clasificar archivos por prioridad (orden de creación) ──────────────────
  local -a files_must=() files_should=() files_could=()
  for f in "${BACKLOG_FILES[@]}"; do
    case "$(extract_priority "$f")" in
      Must)   files_must+=("$f")   ;;
      Should) files_should+=("$f") ;;
      Could)  files_could+=("$f")  ;;
    esac
  done

  log "Must   : ${#files_must[@]} archivos"
  log "Should : ${#files_should[@]} archivos"
  log "Could  : ${#files_could[@]} archivos"
  echo ""

  # ═══════════════════════════════════════════════════════════════════════════
  # PASADA 1 — Crear issues (Must → Should → Could)
  # ═══════════════════════════════════════════════════════════════════════════
  CURRENT_PHASE="PASADA_1_CREACION_ISSUES"
  log "━━━ Pasada 1: creando issues ━━━"
  echo ""

  local created=0 skipped=0 failed=0

  local -a all_files=()
  [[ ${#files_must[@]}   -gt 0 ]] && all_files+=("${files_must[@]}")
  [[ ${#files_should[@]} -gt 0 ]] && all_files+=("${files_should[@]}")
  [[ ${#files_could[@]}  -gt 0 ]] && all_files+=("${files_could[@]}")

  for f in "${all_files[@]}"; do
    LAST_ISSUE_NUMBER=""
    local rc=0
    process_file "$f" "$project_id" "$field_id" || rc=$?

    if [[ "$rc" -eq 0 ]]; then
      (( created++ )) || true
    elif [[ "$rc" -eq 2 ]]; then
      (( skipped++ )) || true
    else
      warn "  Fallo procesando $(basename "$f")"
      (( failed++ )) || true
    fi

    # Registrar en el mapa feature_id → issue_number
    local feat_id feat_title
    feat_id=$(extract_feature_id "$f")
    feat_title=$(extract_title "$f")
    if [[ -n "$feat_id" && -n "$LAST_ISSUE_NUMBER" && "$LAST_ISSUE_NUMBER" != "0" ]]; then
      FEATURE_TO_ISSUE["$feat_id"]="$LAST_ISSUE_NUMBER"
      ISSUE_TO_TITLE["$LAST_ISSUE_NUMBER"]="$feat_title"
      FEATURE_TO_NODE["$feat_id"]="$(get_issue_node_id "$LAST_ISSUE_NUMBER")"
    fi

    echo ""
  done

  # ═══════════════════════════════════════════════════════════════════════════
  # PASADA 2 — Vincular dependencias como sub-issues + blocked-by
  # ═══════════════════════════════════════════════════════════════════════════
  if [[ "$SKIP_DEPS" -eq 0 ]]; then
    CURRENT_PHASE="PASADA_2_DEPENDENCIAS"
    echo ""
    log "━━━ Pasada 2: vinculando dependencias ━━━"
    echo ""

    local linked=0 blocked_count=0

    for f in "${BACKLOG_FILES[@]}"; do

      local feat_id issue_num
      feat_id=$(extract_feature_id "$f")
      [[ -z "$feat_id" ]] && continue
      issue_num="${FEATURE_TO_ISSUE[$feat_id]:-}"
      [[ -z "$issue_num" ]] && continue

      local has_deps=0
      local parent_linked=0
      while IFS=':' read -r dep_id bloqueante; do
        [[ -z "$dep_id" ]] && continue
        has_deps=1

        local dep_issue="${FEATURE_TO_ISSUE[$dep_id]:-}"
        local dep_issue_node="${FEATURE_TO_NODE[$dep_id]:-}"
        local issue_node="${FEATURE_TO_NODE[$feat_id]:-}"
        if [[ -z "$dep_issue" || -z "$dep_issue_node" || -z "$issue_node" ]]; then
          warn "  [$feat_id] Dependencia '$dep_id' no encontrada en los issues — omitida"
          continue
        fi

        printf "  ${C_BLUE}↳${C_RESET} #%s (%s)  ← parent de ←  #%s (%s)" \
          "$dep_issue" "$dep_id" "$issue_num" "$feat_id"

        if [[ "$DRY_RUN" -eq 0 ]]; then
          add_blocked_by_relationship "$issue_node" "$dep_issue_node"
          (( blocked_count++ )) || true
          printf "  ${C_RED}[🚫 BLOCKED BY #%s]${C_RESET}" "$dep_issue"
        else
          printf "  ${C_GRAY}(dry-run)${C_RESET}"
          printf "  ${C_RED}[blocked-by #%s serías marcado]${C_RESET}" "$dep_issue"
        fi

        echo ""
      done < <(extract_dependencies "$f")

      [[ "$has_deps" -gt 0 ]] && echo ""
    done

    ok "Sub-issues vinculados  : $linked"
    [[ "$blocked_count" -gt 0 ]] && ok "Relaciones 'Blocked by': $blocked_count"
    echo ""
  fi

  # ── Resumen final ───────────────────────────────────────────────────────────
  echo -e "${C_GREEN}══════════════════════════════════════════════════════${C_RESET}"
  ok "Issues creados/actualizados: $created"
  [[ "$skipped" -gt 0 ]] && warn "Issues omitidos  : $skipped  (título ya existía — usa --update)"
  [[ "$failed"  -gt 0 ]] && warn "Fallos           : $failed"
  ok "Proyecto         : https://github.com/orgs/$ORG/projects/$PROJECT_NUMBER"
  echo -e "${C_GREEN}══════════════════════════════════════════════════════${C_RESET}"
  echo ""
}

main "$@"
