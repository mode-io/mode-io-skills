#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Iterator, List

from modeio_middleware.core.plugin_manager import ActivePlugin, PluginManager
from modeio_middleware.core.sse import iter_sse_events, serialize_sse_event


def iter_transformed_sse_stream(
    *,
    upstream_response: Any,
    plugin_manager: PluginManager,
    active_plugins: Iterable[ActivePlugin],
    request_id: str,
    endpoint_kind: str,
    profile: str,
    request_context: Dict[str, Any],
    shared_state: Dict[str, Any],
    on_plugin_error: str,
    degraded: List[str],
    services: Dict[str, Any] | None = None,
    connector_capabilities: Dict[str, bool] | None = None,
    on_finish: Callable[[], None] | None = None,
) -> Iterator[bytes]:
    runtime_degraded = list(degraded)
    try:
        for parsed_event in iter_sse_events(upstream_response.iter_lines()):
            is_done_event = parsed_event.get("data_type") == "done"
            if parsed_event.get("data_type") == "none":
                yield serialize_sse_event(parsed_event)
                continue

            event_result = plugin_manager.apply_post_stream_event(
                active_plugins,
                request_id=request_id,
                endpoint_kind=endpoint_kind,
                profile=profile,
                request_context=request_context,
                event=parsed_event,
                shared_state=shared_state,
                on_plugin_error=on_plugin_error,
                services=services,
                connector_capabilities=connector_capabilities,
            )
            runtime_degraded.extend(event_result.degraded)

            if event_result.blocked:
                runtime_degraded.append("stream_blocked")
                payload = {
                    "error": {
                        "message": event_result.block_message,
                        "type": "modeio_error",
                        "code": "MODEIO_PLUGIN_BLOCKED",
                    }
                }
                yield serialize_sse_event({"data_type": "json", "payload": payload})
                yield serialize_sse_event({"data_type": "done"})
                break

            yield serialize_sse_event(event_result.event)

            if is_done_event:
                break

        end_result = plugin_manager.apply_post_stream_end(
            active_plugins,
            request_id=request_id,
            endpoint_kind=endpoint_kind,
            profile=profile,
            request_context=request_context,
            shared_state=shared_state,
            on_plugin_error=on_plugin_error,
            services=services,
            connector_capabilities=connector_capabilities,
        )
        runtime_degraded.extend(end_result.degraded)
        if end_result.blocked:
            payload = {
                "error": {
                    "message": end_result.block_message,
                    "type": "modeio_error",
                    "code": "MODEIO_PLUGIN_BLOCKED",
                }
            }
            yield serialize_sse_event({"data_type": "json", "payload": payload})
            yield serialize_sse_event({"data_type": "done"})
    finally:
        upstream_response.close()
        if on_finish is not None:
            try:
                on_finish()
            except Exception:
                pass
