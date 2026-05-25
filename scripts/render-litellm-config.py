#!/usr/bin/env python3
"""
render-litellm-config.py — Genera infra/litellm/config.yaml desde la plantilla
+ el catálogo de proveedores + el .env del repo.

Uso:
    python3 scripts/render-litellm-config.py
    python3 scripts/render-litellm-config.py --dry-run        # imprime sin escribir
    python3 scripts/render-litellm-config.py --env=/path/.env # .env alternativo

Exit codes:
    0 → config sin cambios (no-op) o --dry-run OK
    1 → error (config inválida, proveedor sin embeddings adecuados, etc.)
    2 → config cambiada y reescrita (señal para que up.sh haga --force-recreate)
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write(
        "✖ PyYAML no instalado en el host. Ejecuta: sudo apt-get install python3-yaml\n"
    )
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parent.parent
PROVIDERS_YAML = REPO_ROOT / "infra" / "litellm" / "providers.yaml"
TEMPLATE_YAML = REPO_ROOT / "infra" / "litellm" / "config.template.yaml"
OUTPUT_YAML = REPO_ROOT / "infra" / "litellm" / "config.yaml"
DEFAULT_ENV = REPO_ROOT / ".env"

CHAT_GROUPS = ("cerebro-lite", "cerebro-pro")


def parse_env(path: Path) -> dict[str, str]:
    """Lee un .env estilo dotenv (KEY=value). Comentarios y líneas vacías ignorados."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def is_real(value: str | None) -> bool:
    """True si el valor no es vacío, no es placeholder _CHANGE_ME ni 'your_*_here'."""
    if not value:
        return False
    if value.endswith("_CHANGE_ME"):
        return False
    if value.startswith("your_") and value.endswith("_here"):
        return False
    return True


def build_model_entry(group: str, provider: str, p_cfg: dict, model: str) -> dict:
    """
    Construye una entry de model_list para un proveedor + modelo concreto.
    El model_name lleva sufijo __<provider> para que se pueda direccionar
    explícitamente desde router_settings.fallbacks.
    """
    litellm_params: dict = {
        "model": f"{p_cfg['prefix']}{model}",
        "api_key": f"os.environ/{p_cfg['env_var']}",
    }
    if p_cfg.get("api_base"):
        litellm_params["api_base"] = p_cfg["api_base"]
    return {
        "model_name": f"{group}__{provider}",
        "litellm_params": litellm_params,
    }


def build_alias_entry(group: str, provider: str, p_cfg: dict, model: str) -> dict:
    """Entry idéntica pero con el model_name canónico (sin sufijo)."""
    entry = build_model_entry(group, provider, p_cfg, model)
    entry["model_name"] = group
    return entry


def render(providers: dict, env: dict) -> tuple[str, dict]:
    """
    Devuelve (yaml_text, metadata) — el YAML final y un dict con resumen para log.
    Lanza SystemExit(1) si la configuración es inválida.
    """
    priority_csv = env.get("LLM_PROVIDERS_PRIORITY", "").strip()
    if not priority_csv:
        sys.stderr.write(
            "✖ LLM_PROVIDERS_PRIORITY vacía en .env. "
            "Ejecuta `bash up.sh` (te pedirá los proveedores).\n"
        )
        sys.exit(1)

    priority = [p.strip() for p in priority_csv.split(",") if p.strip()]
    unknown = [p for p in priority if p not in providers]
    if unknown:
        sys.stderr.write(f"✖ Proveedores desconocidos en LLM_PROVIDERS_PRIORITY: {unknown}\n")
        sys.stderr.write(f"   Disponibles: {sorted(providers.keys())}\n")
        sys.exit(1)

    # Filtrar a los que tienen API key real
    active = [p for p in priority if is_real(env.get(providers[p]["env_var"]))]
    if not active:
        sys.stderr.write(
            "✖ Ningún proveedor de LLM_PROVIDERS_PRIORITY tiene API key real.\n"
            "   Edita .env y rellena al menos una <PROVIDER>_API_KEY.\n"
        )
        sys.exit(1)

    # ── Construir model_list para chat ─────────────────────────────────────
    model_list: list[dict] = []
    for group in CHAT_GROUPS:
        models_key = "lite_models" if group == "cerebro-lite" else "pro_models"
        primary = active[0]
        # Alias canónico = primer proveedor (lo que el cliente invoca por defecto)
        for model in providers[primary][models_key]:
            model_list.append(build_alias_entry(group, primary, providers[primary], model))
        # Entries con sufijo __<provider> para todos los activos (incluye primario,
        # para que sirva como referencia explícita en fallbacks).
        for provider in active:
            for model in providers[provider][models_key]:
                model_list.append(build_model_entry(group, provider, providers[provider], model))

    # ── Embeddings ─────────────────────────────────────────────────────────
    try:
        emb_dim = int(env.get("EMBEDDINGS_DIM", "1024"))
    except ValueError:
        sys.stderr.write(f"✖ EMBEDDINGS_DIM debe ser entero: {env.get('EMBEDDINGS_DIM')}\n")
        sys.exit(1)

    emb_provider_pref = env.get("EMBEDDINGS_PROVIDER", "auto").strip() or "auto"

    if emb_provider_pref == "auto":
        # Primer activo cuya dim coincida
        emb_provider = next(
            (p for p in active if providers[p].get("embedding_dim") == emb_dim),
            None,
        )
        if emb_provider is None:
            sys.stderr.write(
                f"✖ Ningún proveedor activo soporta embeddings de dim={emb_dim}.\n"
                f"   Activos: {active}\n"
                f"   Soluciones: añade un proveedor compatible "
                f"(NVIDIA, Mistral o Cohere para 1024) o cambia EMBEDDINGS_DIM.\n"
            )
            sys.exit(1)
    else:
        if emb_provider_pref not in providers:
            sys.stderr.write(f"✖ EMBEDDINGS_PROVIDER desconocido: {emb_provider_pref}\n")
            sys.exit(1)
        if emb_provider_pref not in active:
            sys.stderr.write(
                f"✖ EMBEDDINGS_PROVIDER={emb_provider_pref} no está en LLM_PROVIDERS_PRIORITY "
                f"o no tiene API key real.\n"
            )
            sys.exit(1)
        p_cfg = providers[emb_provider_pref]
        if not p_cfg.get("embedding_model"):
            sys.stderr.write(f"✖ Proveedor {emb_provider_pref} no ofrece embeddings.\n")
            sys.exit(1)
        if p_cfg.get("embedding_dim") != emb_dim:
            sys.stderr.write(
                f"✖ {emb_provider_pref} tiene dim={p_cfg.get('embedding_dim')}, "
                f"pero EMBEDDINGS_DIM={emb_dim}.\n"
            )
            sys.exit(1)
        emb_provider = emb_provider_pref

    p_cfg = providers[emb_provider]
    emb_entry = {
        "model_name": "cerebro-embeddings",
        "litellm_params": {
            "model": f"{p_cfg['prefix']}{p_cfg['embedding_model']}",
            "api_key": f"os.environ/{p_cfg['env_var']}",
            "encoding_format": "float",
        },
    }
    if p_cfg.get("api_base"):
        emb_entry["litellm_params"]["api_base"] = p_cfg["api_base"]
    model_list.append(emb_entry)

    # ── Fallbacks para chat (los embeddings no tienen fallback) ────────────
    fallbacks_block = ""
    if len(active) > 1:
        fallbacks_block = "  fallbacks:\n"
        for group in CHAT_GROUPS:
            chain = [f"{group}__{p}" for p in active[1:]]
            fallbacks_block += f"    - {group}: {chain}\n"

    # ── Render del YAML ───────────────────────────────────────────────────
    model_list_yaml = yaml.safe_dump(
        model_list,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    # Indentar 2 espacios para encajar bajo `model_list:` en la plantilla
    model_list_indented = "\n".join("  " + line if line else "" for line in model_list_yaml.splitlines())

    template = TEMPLATE_YAML.read_text()
    rendered = (
        template
        .replace("{{MODEL_LIST}}", model_list_indented)
        .replace("{{FALLBACKS}}", fallbacks_block.rstrip())
    )

    metadata = {
        "active_providers": active,
        "primary": active[0],
        "embeddings_provider": emb_provider,
        "embeddings_model": p_cfg["embedding_model"],
        "embeddings_dim": emb_dim,
        "model_list_count": len(model_list),
    }
    return rendered, metadata


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="No escribir; imprimir a stdout.")
    ap.add_argument("--env", default=str(DEFAULT_ENV), help="Ruta al .env (default: ./.env)")
    args = ap.parse_args()

    if not PROVIDERS_YAML.exists():
        sys.stderr.write(f"✖ No existe {PROVIDERS_YAML}\n")
        return 1
    if not TEMPLATE_YAML.exists():
        sys.stderr.write(f"✖ No existe {TEMPLATE_YAML}\n")
        return 1

    catalog = yaml.safe_load(PROVIDERS_YAML.read_text())
    providers = catalog.get("providers", {})
    if not providers:
        sys.stderr.write(f"✖ Catálogo vacío en {PROVIDERS_YAML}\n")
        return 1

    env = parse_env(Path(args.env))
    rendered, meta = render(providers, env)

    if args.dry_run:
        sys.stdout.write(rendered)
        return 0

    # Comparar con el archivo previo
    previous = OUTPUT_YAML.read_text() if OUTPUT_YAML.exists() else ""
    if previous == rendered:
        print("✔ infra/litellm/config.yaml sin cambios "
              f"(primary={meta['primary']}, embeddings={meta['embeddings_provider']} "
              f"[{meta['embeddings_model']}] dim={meta['embeddings_dim']})")
        return 0

    OUTPUT_YAML.write_text(rendered)
    arrow = " → ".join(meta["active_providers"])
    print(f"✔ Proveedores activos: {arrow}")
    print(f"✔ Embeddings: {meta['embeddings_provider']} [{meta['embeddings_model']}] "
          f"({meta['embeddings_dim']} dim)")
    print(f"✔ infra/litellm/config.yaml regenerado ({meta['model_list_count']} entries)")
    return 2


if __name__ == "__main__":
    sys.exit(main())
