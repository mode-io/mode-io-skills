from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List


def build_sandbox_paths(root: Path) -> Dict[str, Path]:
    home = root / "home"
    xdg_root = root / "xdg"
    openclaw_state = root / "openclaw-state"
    return {
        "root": root,
        "home": home,
        "xdg_config": xdg_root / "config",
        "xdg_state": xdg_root / "state",
        "xdg_cache": xdg_root / "cache",
        "opencode_config": xdg_root / "config" / "opencode" / "opencode.json",
        "openclaw_state": openclaw_state,
        "openclaw_config": openclaw_state / "openclaw.json",
        "openclaw_models_cache": openclaw_state / "agents" / "main" / "agent" / "models.json",
    }


def build_sandbox_env(
    parent_env: Dict[str, str],
    paths: Dict[str, Path],
    *,
    gateway_base_url: str,
    upstream_api_key: str,
) -> Dict[str, str]:
    allowlist = (
        "PATH",
        "LANG",
        "LC_ALL",
        "TERM",
        "TMPDIR",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
    )
    env = {
        key: value
        for key, value in parent_env.items()
        if key in allowlist and isinstance(value, str) and value
    }
    env.update(
        {
            "HOME": str(paths["home"]),
            "XDG_CONFIG_HOME": str(paths["xdg_config"]),
            "XDG_STATE_HOME": str(paths["xdg_state"]),
            "XDG_CACHE_HOME": str(paths["xdg_cache"]),
            "OPENAI_BASE_URL": gateway_base_url,
            "OPENAI_API_KEY": parent_env.get("OPENAI_API_KEY", "").strip() or upstream_api_key,
            "OPENCLAW_CONFIG_PATH": str(paths["openclaw_config"]),
            "OPENCLAW_STATE_DIR": str(paths["openclaw_state"]),
            "OPENCLAW_AGENT_DIR": str(paths["openclaw_models_cache"].parent),
            "PI_CODING_AGENT_DIR": str(paths["openclaw_models_cache"].parent),
            "MODEIO_GATEWAY_UPSTREAM_API_KEY": upstream_api_key,
            "MODEIO_TAP_UPSTREAM_API_KEY": upstream_api_key,
            "PYTHONUNBUFFERED": "1",
        }
    )
    return env


def seed_codex_credentials(real_home: Path, sandbox_home: Path) -> List[str]:
    seeded: List[str] = []
    source_root = real_home / ".codex"
    target_root = sandbox_home / ".codex"
    if not source_root.exists():
        return seeded

    for relative in ("auth.json",):
        src = source_root / relative
        if not src.exists():
            continue
        dst = target_root / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        seeded.append(relative)
    return seeded


def upsert_openclaw_provider_model(provider_obj: Dict[str, object], model_id: str) -> bool:
    changed = False
    desired_model = {"id": model_id, "name": f"Live Smoke {model_id}"}

    raw_models = provider_obj.get("models")
    if not isinstance(raw_models, list):
        provider_obj["models"] = [desired_model]
        return True

    found = False
    new_models: List[object] = []
    for item in raw_models:
        if not isinstance(item, dict):
            new_models.append(item)
            continue

        item_id = item.get("id")
        if item_id == model_id:
            found = True
            if item.get("name") != desired_model["name"]:
                item = dict(item)
                item["name"] = desired_model["name"]
                changed = True
            new_models.append(item)
            continue

        if item_id == "middleware-default":
            changed = True
            continue

        new_models.append(item)

    if not found:
        new_models.append(desired_model)
        changed = True

    provider_obj["models"] = new_models
    return changed


def apply_openclaw_live_model_to_config(payload: Dict[str, object], model_id: str) -> bool:
    changed = False
    models_obj = payload.get("models")
    if not isinstance(models_obj, dict):
        return changed

    providers_obj = models_obj.get("providers")
    if not isinstance(providers_obj, dict):
        return changed

    provider_obj = providers_obj.get("modeio-middleware")
    if not isinstance(provider_obj, dict):
        return changed

    if upsert_openclaw_provider_model(provider_obj, model_id):
        changed = True

    target_ref = f"modeio-middleware/{model_id}"

    agents_obj = payload.get("agents")
    if not isinstance(agents_obj, dict):
        agents_obj = {}
        payload["agents"] = agents_obj
        changed = True

    defaults_obj = agents_obj.get("defaults")
    if not isinstance(defaults_obj, dict):
        defaults_obj = {}
        agents_obj["defaults"] = defaults_obj
        changed = True

    model_obj = defaults_obj.get("model")
    if not isinstance(model_obj, dict):
        model_obj = {}
        defaults_obj["model"] = model_obj
        changed = True

    if model_obj.get("primary") != target_ref:
        model_obj["primary"] = target_ref
        changed = True

    defaults_models_obj = defaults_obj.get("models")
    if not isinstance(defaults_models_obj, dict):
        defaults_models_obj = {}
        defaults_obj["models"] = defaults_models_obj
        changed = True

    route_obj = defaults_models_obj.get(target_ref)
    if not isinstance(route_obj, dict):
        route_obj = {}
        defaults_models_obj[target_ref] = route_obj
        changed = True

    params_obj = route_obj.get("params")
    if not isinstance(params_obj, dict):
        params_obj = {}
        route_obj["params"] = params_obj
        changed = True

    if params_obj.get("transport") != "sse":
        params_obj["transport"] = "sse"
        changed = True

    stale_ref = "modeio-middleware/middleware-default"
    if stale_ref in defaults_models_obj and stale_ref != target_ref:
        del defaults_models_obj[stale_ref]
        changed = True

    return changed


def apply_openclaw_live_model_to_cache(payload: Dict[str, object], model_id: str) -> bool:
    changed = False
    providers_obj = None

    models_obj = payload.get("models")
    if isinstance(models_obj, dict):
        candidate = models_obj.get("providers")
        if isinstance(candidate, dict):
            providers_obj = candidate

    if providers_obj is None:
        candidate = payload.get("providers")
        if isinstance(candidate, dict):
            providers_obj = candidate

    if not isinstance(providers_obj, dict):
        return changed

    provider_obj = providers_obj.get("modeio-middleware")
    if not isinstance(provider_obj, dict):
        return changed

    if upsert_openclaw_provider_model(provider_obj, model_id):
        changed = True
    return changed


def rewrite_openclaw_model_for_live(
    *,
    config_path: Path,
    models_cache_path: Path,
    model_id: str,
) -> Dict[str, object]:
    report = {
        "modelId": model_id,
        "configPath": str(config_path),
        "modelsCachePath": str(models_cache_path),
        "configChanged": False,
        "modelsCacheChanged": False,
    }

    if config_path.exists():
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and apply_openclaw_live_model_to_config(payload, model_id):
            config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            report["configChanged"] = True

    if models_cache_path.exists():
        payload = json.loads(models_cache_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and apply_openclaw_live_model_to_cache(payload, model_id):
            models_cache_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            report["modelsCacheChanged"] = True

    return report
