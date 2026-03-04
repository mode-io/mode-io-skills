.PHONY: redact-tests middleware-gateway-setup middleware-gateway-uninstall middleware-gateway-tests

PYTHON ?= python3

redact-tests:
	$(PYTHON) -m unittest discover modeio-redact/tests -p "test_*.py"
	$(PYTHON) -m unittest discover modeio-redact/tests -p "test_smoke_matrix_extensive.py"

middleware-gateway-setup:
	$(PYTHON) modeio-middleware/scripts/setup_middleware_gateway.py --client both

middleware-gateway-uninstall:
	$(PYTHON) modeio-middleware/scripts/setup_middleware_gateway.py --client both --uninstall --apply-opencode

middleware-gateway-tests:
	$(PYTHON) -m unittest discover modeio-middleware/tests -p "test_*.py"
