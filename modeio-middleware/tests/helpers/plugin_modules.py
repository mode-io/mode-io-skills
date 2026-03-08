#!/usr/bin/env python3

import sys
import types


def register_plugin_module(module_name: str, plugin_cls) -> None:
    module = types.ModuleType(module_name)
    module.Plugin = plugin_cls
    sys.modules[module_name] = module
