#!/usr/bin/env python3

from __future__ import annotations

import copy
import os
import platform
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from modeio_middleware.cli.setup_lib.common import (
    SetupError,
    ensure_object,
    normalize_gateway_base_url,
    read_json_file,
    utc_timestamp,
    write_json_file,
)

OPENCLAW_PROVIDER_ID = "modeio-middleware"
OPENCLAW_MODEL_ID = "middleware-default"
OPENCLAW_MODEL_REF = f"{OPENCLAW_PROVIDER_ID}/{OPENCLAW_MODEL_ID}"
OPENCLAW_MODEL_NAME = "Modeio Middleware Default"
OPENCLAW_DEFAULT_API_KEY = "modeio-middleware"
OPENCLAW_DEFAULT_STATE_DIRNAME = ".openclaw"
OPENCLAW_CONFIG_FILENAMES = {
    "openclaw.json",
    "clawdbot.json",
    "moltbot.json",
    "moldbot.json",
}


def _detect_os_name(os_name: Optional[str] = None) -> str:
    if os_name:
        return os_name.strip().lower()
    return platform.system().strip().lower()


def default_openclaw_config_path(
    *,
    os_name: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    home: Optional[Path] = None,
) -> Path:
    resolved_env = env or os.environ
    override = resolved_env.get("OPENCLAW_CONFIG_PATH", "").strip()
    if override:
        return Path(override).expanduser()

    resolved_home = home or Path.home()
    system_name = _detect_os_name(os_name)
    if system_name == "windows":
        app_data = resolved_env.get("APPDATA", "").strip()
        if app_data:
            return Path(app_data) / "openclaw" / "openclaw.json"
        return resolved_home / "AppData" / "Roaming" / "openclaw" / "openclaw.json"

    return resolved_home / ".openclaw" / "openclaw.json"


def default_openclaw_models_cache_path(
    *,
    config_path: Path,
    env: Optional[Dict[str, str]] = None,
    home: Optional[Path] = None,
) -> Path:
    resolved_env = env or os.environ

    raw_agent_dir = (
        resolved_env.get("OPENCLAW_AGENT_DIR", "").strip()
        or resolved_env.get("PI_CODING_AGENT_DIR", "").strip()
    )
    if raw_agent_dir:
        return Path(raw_agent_dir).expanduser() / "models.json"

    raw_state_dir = (
        resolved_env.get("OPENCLAW_STATE_DIR", "").strip()
        or resolved_env.get("CLAWDBOT_STATE_DIR", "").strip()
    )
    if raw_state_dir:
        return Path(raw_state_dir).expanduser() / "agents" / "main" / "agent" / "models.json"

    if config_path.name.strip().lower() in OPENCLAW_CONFIG_FILENAMES:
        return config_path.parent / "agents" / "main" / "agent" / "models.json"

    resolved_home = home or Path.home()
    return resolved_home / OPENCLAW_DEFAULT_STATE_DIRNAME / "agents" / "main" / "agent" / "models.json"


def _default_openclaw_provider_model() -> Dict[str, Any]:
    return {
        "id": OPENCLAW_MODEL_ID,
        "name": OPENCLAW_MODEL_NAME,
    }


def _upsert_openclaw_provider_model(models_value: Any) -> Tuple[Sequence[Any], bool]:
    default_model = _default_openclaw_provider_model()
    if not isinstance(models_value, list):
        return [default_model], True

    updated_models = copy.deepcopy(models_value)
    for index, model in enumerate(updated_models):
        if not isinstance(model, dict):
            continue
        if model.get("id") != OPENCLAW_MODEL_ID:
            continue

        changed = False
        if model.get("name") != OPENCLAW_MODEL_NAME:
            model["name"] = OPENCLAW_MODEL_NAME
            changed = True
        updated_models[index] = model
        return updated_models, changed

    updated_models.append(default_model)
    return updated_models, True


def apply_openclaw_provider_route(
    config: Dict[str, Any],
    gateway_base_url: str,
) -> Tuple[Dict[str, Any], bool]:
    updated = copy.deepcopy(config)
    changed = False
    normalized = normalize_gateway_base_url(gateway_base_url)

    models_obj = ensure_object(updated.get("models"), "models")
    if models_obj.get("mode") != "merge":
        models_obj["mode"] = "merge"
        changed = True

    providers_obj = ensure_object(models_obj.get("providers"), "models.providers")
    provider_obj = ensure_object(
        providers_obj.get(OPENCLAW_PROVIDER_ID),
        f"models.providers.{OPENCLAW_PROVIDER_ID}",
    )

    if provider_obj.get("baseUrl") != normalized:
        provider_obj["baseUrl"] = normalized
        changed = True

    if provider_obj.get("api") != "openai-completions":
        provider_obj["api"] = "openai-completions"
        changed = True

    if provider_obj.get("authHeader") is not False:
        provider_obj["authHeader"] = False
        changed = True

    current_api_key = provider_obj.get("apiKey")
    if not isinstance(current_api_key, str) or not current_api_key.strip():
        if current_api_key != OPENCLAW_DEFAULT_API_KEY:
            changed = True
        provider_obj["apiKey"] = OPENCLAW_DEFAULT_API_KEY

    provider_models, models_changed = _upsert_openclaw_provider_model(provider_obj.get("models"))
    if models_changed:
        changed = True
    provider_obj["models"] = provider_models

    providers_obj[OPENCLAW_PROVIDER_ID] = provider_obj
    models_obj["providers"] = providers_obj
    updated["models"] = models_obj

    agents_obj = ensure_object(updated.get("agents"), "agents")
    defaults_obj = ensure_object(agents_obj.get("defaults"), "agents.defaults")

    model_obj = ensure_object(defaults_obj.get("model"), "agents.defaults.model")
    if model_obj.get("primary") != OPENCLAW_MODEL_REF:
        model_obj["primary"] = OPENCLAW_MODEL_REF
        changed = True
    defaults_obj["model"] = model_obj

    defaults_models_obj = ensure_object(defaults_obj.get("models"), "agents.defaults.models")
    route_obj = ensure_object(
        defaults_models_obj.get(OPENCLAW_MODEL_REF),
        f"agents.defaults.models.{OPENCLAW_MODEL_REF}",
    )
    params_obj = ensure_object(
        route_obj.get("params"),
        f"agents.defaults.models.{OPENCLAW_MODEL_REF}.params",
    )
    if params_obj.get("transport") != "sse":
        params_obj["transport"] = "sse"
        changed = True
    route_obj["params"] = params_obj
    defaults_models_obj[OPENCLAW_MODEL_REF] = route_obj
    defaults_obj["models"] = defaults_models_obj

    agents_obj["defaults"] = defaults_obj
    updated["agents"] = agents_obj
    return updated, changed


def remove_openclaw_provider_route(
    config: Dict[str, Any],
    gateway_base_url: str,
    *,
    force_remove: bool,
) -> Tuple[Dict[str, Any], bool, Optional[str], str]:
    updated = copy.deepcopy(config)

    models_obj = updated.get("models")
    if not isinstance(models_obj, dict):
        return updated, False, None, "models_missing"

    providers_obj = models_obj.get("providers")
    if not isinstance(providers_obj, dict):
        return updated, False, None, "providers_missing"

    provider_obj = providers_obj.get(OPENCLAW_PROVIDER_ID)
    if not isinstance(provider_obj, dict):
        return updated, False, None, "provider_missing"

    raw_base_url = provider_obj.get("baseUrl")
    removed_base_url = raw_base_url if isinstance(raw_base_url, str) else None

    if not force_remove:
        if not isinstance(raw_base_url, str) or not raw_base_url.strip():
            return updated, False, None, "provider_base_url_not_set"

        normalized_target = normalize_gateway_base_url(gateway_base_url)
        normalized_current = raw_base_url.rstrip("/")
        if normalized_current != normalized_target:
            return updated, False, raw_base_url, "provider_base_url_mismatch"

    del providers_obj[OPENCLAW_PROVIDER_ID]
    models_obj["providers"] = providers_obj
    updated["models"] = models_obj

    agents_obj = updated.get("agents")
    if isinstance(agents_obj, dict):
        defaults_obj = agents_obj.get("defaults")
        if isinstance(defaults_obj, dict):
            model_obj = defaults_obj.get("model")
            if isinstance(model_obj, dict) and model_obj.get("primary") == OPENCLAW_MODEL_REF:
                del model_obj["primary"]

            defaults_models_obj = defaults_obj.get("models")
            if isinstance(defaults_models_obj, dict):
                defaults_models_obj.pop(OPENCLAW_MODEL_REF, None)

    return updated, True, removed_base_url, "removed"


def apply_openclaw_models_cache_provider(
    config: Dict[str, Any],
    gateway_base_url: str,
) -> Tuple[Dict[str, Any], bool]:
    updated = copy.deepcopy(config)
    changed = False
    normalized = normalize_gateway_base_url(gateway_base_url)

    models_obj = updated.get("models")
    if isinstance(models_obj, dict) or models_obj is None:
        models_obj = ensure_object(models_obj, "models")
        providers_obj = ensure_object(models_obj.get("providers"), "models.providers")
        provider_parent = "models"
    else:
        providers_obj = ensure_object(updated.get("providers"), "providers")
        provider_parent = "root"

    provider_obj = ensure_object(
        providers_obj.get(OPENCLAW_PROVIDER_ID),
        (
            f"models.providers.{OPENCLAW_PROVIDER_ID}"
            if provider_parent == "models"
            else f"providers.{OPENCLAW_PROVIDER_ID}"
        ),
    )

    if provider_obj.get("baseUrl") != normalized:
        provider_obj["baseUrl"] = normalized
        changed = True

    if provider_obj.get("api") != "openai-completions":
        provider_obj["api"] = "openai-completions"
        changed = True

    if provider_obj.get("authHeader") is not False:
        provider_obj["authHeader"] = False
        changed = True

    current_api_key = provider_obj.get("apiKey")
    if not isinstance(current_api_key, str) or not current_api_key.strip():
        if current_api_key != OPENCLAW_DEFAULT_API_KEY:
            changed = True
        provider_obj["apiKey"] = OPENCLAW_DEFAULT_API_KEY

    provider_models, models_changed = _upsert_openclaw_provider_model(provider_obj.get("models"))
    if models_changed:
        changed = True
    provider_obj["models"] = provider_models

    providers_obj[OPENCLAW_PROVIDER_ID] = provider_obj
    if provider_parent == "models":
        models_obj["providers"] = providers_obj
        updated["models"] = models_obj
    else:
        updated["providers"] = providers_obj
    return updated, changed


def remove_openclaw_models_cache_provider(
    config: Dict[str, Any],
    gateway_base_url: str,
    *,
    force_remove: bool,
) -> Tuple[Dict[str, Any], bool, Optional[str], str]:
    updated = copy.deepcopy(config)

    models_obj = updated.get("models")
    if isinstance(models_obj, dict):
        providers_obj = models_obj.get("providers")
        provider_parent = "models"
    else:
        providers_obj = updated.get("providers")
        provider_parent = "root"

    if not isinstance(providers_obj, dict):
        if provider_parent == "models":
            providers_obj = updated.get("providers")
            provider_parent = "root"
        if not isinstance(providers_obj, dict):
            return updated, False, None, "providers_missing"

    provider_obj = providers_obj.get(OPENCLAW_PROVIDER_ID)
    if not isinstance(provider_obj, dict):
        return updated, False, None, "provider_missing"

    raw_base_url = provider_obj.get("baseUrl")
    removed_base_url = raw_base_url if isinstance(raw_base_url, str) else None

    if not force_remove:
        if not isinstance(raw_base_url, str) or not raw_base_url.strip():
            return updated, False, None, "provider_base_url_not_set"

        normalized_target = normalize_gateway_base_url(gateway_base_url)
        normalized_current = raw_base_url.rstrip("/")
        if normalized_current != normalized_target:
            return updated, False, raw_base_url, "provider_base_url_mismatch"

    del providers_obj[OPENCLAW_PROVIDER_ID]
    if provider_parent == "models":
        models_obj["providers"] = providers_obj
        updated["models"] = models_obj
    else:
        updated["providers"] = providers_obj
    return updated, True, removed_base_url, "removed"


def apply_openclaw_config_file(
    *,
    config_path: Path,
    gateway_base_url: str,
    create_if_missing: bool,
) -> Dict[str, Any]:
    existed = config_path.exists()
    if not existed and not create_if_missing:
        raise SetupError(
            f"OpenClaw config not found: {config_path}. Use --create-openclaw-config to create it."
        )

    config_data: Dict[str, Any] = {}
    if existed:
        config_data = read_json_file(config_path)

    updated, changed = apply_openclaw_provider_route(config_data, gateway_base_url)
    backup_path = None
    if changed:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if existed:
            backup_path = config_path.with_name(f"{config_path.name}.bak.{utc_timestamp()}")
            shutil.copy2(config_path, backup_path)
        write_json_file(config_path, updated)

    return {
        "path": str(config_path),
        "changed": changed,
        "created": (not existed) and changed,
        "backupPath": str(backup_path) if backup_path else None,
    }


def uninstall_openclaw_config_file(
    *,
    config_path: Path,
    gateway_base_url: str,
    force_remove: bool,
) -> Dict[str, Any]:
    if not config_path.exists():
        return {
            "path": str(config_path),
            "changed": False,
            "backupPath": None,
            "reason": "config_not_found",
            "removedBaseUrl": None,
        }

    config_data = read_json_file(config_path)
    updated, changed, removed_value, reason = remove_openclaw_provider_route(
        config_data,
        gateway_base_url,
        force_remove=force_remove,
    )

    backup_path = None
    if changed:
        backup_path = config_path.with_name(f"{config_path.name}.bak.{utc_timestamp()}")
        shutil.copy2(config_path, backup_path)
        write_json_file(config_path, updated)

    return {
        "path": str(config_path),
        "changed": changed,
        "backupPath": str(backup_path) if backup_path else None,
        "reason": reason,
        "removedBaseUrl": removed_value,
    }


def apply_openclaw_models_cache_file(
    *,
    models_cache_path: Path,
    gateway_base_url: str,
) -> Dict[str, Any]:
    existed = models_cache_path.exists()

    config_data: Dict[str, Any] = {}
    if existed:
        config_data = read_json_file(models_cache_path)

    updated, changed = apply_openclaw_models_cache_provider(config_data, gateway_base_url)
    backup_path = None
    if changed:
        models_cache_path.parent.mkdir(parents=True, exist_ok=True)
        if existed:
            backup_path = models_cache_path.with_name(f"{models_cache_path.name}.bak.{utc_timestamp()}")
            shutil.copy2(models_cache_path, backup_path)
        write_json_file(models_cache_path, updated)

    return {
        "path": str(models_cache_path),
        "changed": changed,
        "created": (not existed) and changed,
        "backupPath": str(backup_path) if backup_path else None,
    }


def uninstall_openclaw_models_cache_file(
    *,
    models_cache_path: Path,
    gateway_base_url: str,
    force_remove: bool,
) -> Dict[str, Any]:
    if not models_cache_path.exists():
        return {
            "path": str(models_cache_path),
            "changed": False,
            "backupPath": None,
            "reason": "config_not_found",
            "removedBaseUrl": None,
        }

    config_data = read_json_file(models_cache_path)
    updated, changed, removed_value, reason = remove_openclaw_models_cache_provider(
        config_data,
        gateway_base_url,
        force_remove=force_remove,
    )

    backup_path = None
    if changed:
        backup_path = models_cache_path.with_name(f"{models_cache_path.name}.bak.{utc_timestamp()}")
        shutil.copy2(models_cache_path, backup_path)
        write_json_file(models_cache_path, updated)

    return {
        "path": str(models_cache_path),
        "changed": changed,
        "backupPath": str(backup_path) if backup_path else None,
        "reason": reason,
        "removedBaseUrl": removed_value,
    }
