#!/usr/bin/env python3

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Iterable, Iterator, List

from modeio_middleware.core.plugin_manager import ActivePlugin, PluginManager
from modeio_middleware.core.sse import parse_sse_data_line, serialize_sse_data_line


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
    on_finish: Callable[[], None] | None = None,
) -> Iterator[bytes]:
    runtime_degraded = list(degraded)
    try:
        for raw_line in upstream_response.iter_lines(chunk_size=1, decode_unicode=False):
            if isinstance(raw_line, str):
                line_bytes = raw_line.encode("utf-8")
            else:
                line_bytes = raw_line

            parsed_event = parse_sse_data_line(line_bytes)
            if parsed_event is None:
                yield line_bytes + b"\n"
                continue

            is_done_event = parsed_event.get("data_type") == "done"

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
                error_line = b"data: " + json.dumps(payload, ensure_ascii=False).encode("utf-8")
                yield error_line + b"\n\n"
                yield b"data: [DONE]\n\n"
                break

            line_bytes = serialize_sse_data_line(event_result.event)
            yield line_bytes + b"\n"

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
            error_line = b"data: " + json.dumps(payload, ensure_ascii=False).encode("utf-8")
            yield error_line + b"\n\n"
            yield b"data: [DONE]\n\n"
    finally:
        upstream_response.close()
        if on_finish is not None:
            try:
                on_finish()
            except Exception:
                pass
