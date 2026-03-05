#!/usr/bin/env python3

from __future__ import annotations

import json
import select
import subprocess
import threading
from typing import Any, Dict, List

from modeio_middleware.core.errors import MiddlewareError
from modeio_middleware.protocol.messages import JSONRPC_VERSION


class JsonRpcStdioSupervisor:
    def __init__(self, *, plugin_name: str, command: List[str]):
        if not isinstance(command, list) or not command:
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"plugin '{plugin_name}' stdio command must be a non-empty array",
                retryable=False,
            )
        for index, item in enumerate(command):
            if not isinstance(item, str) or not item.strip():
                raise MiddlewareError(
                    500,
                    "MODEIO_CONFIG_ERROR",
                    f"plugin '{plugin_name}' stdio command[{index}] must be a non-empty string",
                    retryable=False,
                )

        self.plugin_name = plugin_name
        self.command = [item.strip() for item in command]
        self._lock = threading.Lock()
        self._next_id = 1
        self._process = self._start_process()

    def _start_process(self) -> subprocess.Popen[str]:
        try:
            process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as error:
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"failed to start stdio plugin process for '{self.plugin_name}'",
                retryable=False,
                details={"command": self.command},
            ) from error

        if process.stdin is None or process.stdout is None:
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"stdio plugin '{self.plugin_name}' missing stdio pipes",
                retryable=False,
            )
        return process

    def _ensure_alive(self) -> None:
        code = self._process.poll()
        if code is not None:
            raise RuntimeError(f"stdio plugin process exited with code {code}")

    def _next_request_id(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value

    def _readline_with_timeout(self, timeout_ms: int) -> str:
        if self._process.stdout is None:
            raise RuntimeError("stdout pipe is not available")

        timeout_seconds = max(float(timeout_ms), 1.0) / 1000.0
        readable, _, _ = select.select([self._process.stdout], [], [], timeout_seconds)
        if not readable:
            raise TimeoutError(f"plugin '{self.plugin_name}' timed out waiting for JSON-RPC response")

        line = self._process.stdout.readline()
        if not line:
            raise RuntimeError(f"plugin '{self.plugin_name}' closed stdout unexpectedly")
        return line

    def call(self, *, method: str, params: Dict[str, Any], timeout_ms: int) -> Dict[str, Any]:
        with self._lock:
            self._ensure_alive()
            request_id = self._next_request_id()
            payload = {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "method": method,
                "params": params,
            }

            assert self._process.stdin is not None
            try:
                self._process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
                self._process.stdin.flush()
            except OSError as error:
                raise RuntimeError(f"failed to write JSON-RPC payload to plugin '{self.plugin_name}'") from error

            line = self._readline_with_timeout(timeout_ms)
            try:
                response = json.loads(line)
            except ValueError as error:
                raise RuntimeError(f"plugin '{self.plugin_name}' returned invalid JSON-RPC payload") from error

            if not isinstance(response, dict):
                raise RuntimeError(f"plugin '{self.plugin_name}' returned non-object JSON-RPC payload")
            if response.get("id") != request_id:
                raise RuntimeError(f"plugin '{self.plugin_name}' returned mismatched JSON-RPC id")

            error_payload = response.get("error")
            if isinstance(error_payload, dict):
                message = error_payload.get("message")
                message_text = str(message) if message else "plugin returned JSON-RPC error"
                raise RuntimeError(f"plugin '{self.plugin_name}' JSON-RPC error: {message_text}")

            result = response.get("result")
            if not isinstance(result, dict):
                raise RuntimeError(f"plugin '{self.plugin_name}' JSON-RPC result must be object")
            return result

    def shutdown(self) -> None:
        process = self._process
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()

        if process.stdin is not None:
            try:
                process.stdin.close()
            except Exception:
                pass
        if process.stdout is not None:
            try:
                process.stdout.close()
            except Exception:
                pass
        if process.stderr is not None:
            try:
                process.stderr.close()
            except Exception:
                pass
