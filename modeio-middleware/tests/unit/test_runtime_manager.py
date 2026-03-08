#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "modeio-middleware"
sys.path.insert(0, str(PACKAGE_ROOT))

from modeio_middleware.registry.resolver import PluginRuntimeSpec  # noqa: E402
from modeio_middleware.runtime.base import PluginRuntime  # noqa: E402
from modeio_middleware.runtime.manager import PluginRuntimeManager  # noqa: E402


class _FakeRuntime(PluginRuntime):
    def __init__(self, name: str):
        self.name = name
        self.healthy = True
        self.shutdown_calls = 0

    def is_healthy(self) -> bool:
        return self.healthy

    def shutdown(self) -> None:
        self.shutdown_calls += 1


def _spec(*, pool_size: int = 1) -> PluginRuntimeSpec:
    return PluginRuntimeSpec(
        name="external_policy",
        runtime="stdio_jsonrpc",
        mode="observe",
        module_path=None,
        command=["python3", "plugin.py"],
        manifest=None,
        capabilities={"can_patch": False, "can_block": False},
        timeout_ms={},
        pool_size=pool_size,
        hook_config={},
        supported_hooks=["pre_request"],
    )


class TestRuntimeManager(unittest.TestCase):
    def test_acquire_scales_up_to_pool_size_before_reusing_runtime(self):
        runtimes = [_FakeRuntime("one"), _FakeRuntime("two")]
        with patch("modeio_middleware.runtime.manager.create_plugin_runtime", side_effect=runtimes):
            manager = PluginRuntimeManager()
            lease_one = manager.acquire(_spec(pool_size=2))
            lease_two = manager.acquire(_spec(pool_size=2))
            lease_three = manager.acquire(_spec(pool_size=2))

        self.assertIsNot(lease_one.runtime, lease_two.runtime)
        self.assertTrue(
            lease_three.runtime is lease_one.runtime or lease_three.runtime is lease_two.runtime
        )

        lease_one.release()
        lease_two.release()
        lease_three.release()

    def test_release_makes_idle_runtime_available_for_reuse(self):
        runtime = _FakeRuntime("one")
        with patch("modeio_middleware.runtime.manager.create_plugin_runtime", return_value=runtime):
            manager = PluginRuntimeManager()
            lease_one = manager.acquire(_spec(pool_size=1))
            lease_one.release()
            lease_two = manager.acquire(_spec(pool_size=1))

        self.assertIs(lease_one.runtime, lease_two.runtime)
        lease_two.release()

    def test_unhealthy_runtime_is_replaced(self):
        runtime_one = _FakeRuntime("one")
        runtime_two = _FakeRuntime("two")
        with patch("modeio_middleware.runtime.manager.create_plugin_runtime", side_effect=[runtime_one, runtime_two]):
            manager = PluginRuntimeManager()
            lease_one = manager.acquire(_spec(pool_size=1))
            lease_one.release()
            runtime_one.healthy = False
            lease_two = manager.acquire(_spec(pool_size=1))

        self.assertIsNot(lease_one.runtime, lease_two.runtime)
        self.assertEqual(runtime_one.shutdown_calls, 1)
        lease_two.release()


if __name__ == "__main__":
    unittest.main()
