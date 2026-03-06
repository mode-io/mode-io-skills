.PHONY: bootstrap doctor setup-tests smoke-redact-lite guardrail-tests redact-tests middleware-gateway-setup middleware-gateway-uninstall middleware-gateway-tests

PYTHON ?= python3

bootstrap:
	$(PYTHON) scripts/bootstrap_env.py

doctor:
	$(PYTHON) scripts/doctor_env.py

setup-tests:
	$(PYTHON) -m unittest discover tests -p "test_*.py"

smoke-redact-lite:
	$(PYTHON) modeio-redact/scripts/anonymize.py --input "Email: alice@example.com" --level lite --json

guardrail-tests:
	$(PYTHON) -m unittest modeio-guardrail.tests.test_safety_contract

redact-tests:
	$(PYTHON) -m unittest discover modeio-redact/tests -p "test_*.py"
	$(PYTHON) -m unittest discover modeio-redact/tests -p "test_smoke_matrix_extensive.py"

middleware-gateway-setup:
	$(PYTHON) modeio-middleware/scripts/setup_middleware_gateway.py --apply-opencode --apply-openclaw --create-opencode-config --create-openclaw-config

middleware-gateway-uninstall:
	$(PYTHON) modeio-middleware/scripts/setup_middleware_gateway.py --uninstall --apply-opencode --apply-openclaw

middleware-gateway-tests:
	$(PYTHON) -m unittest discover modeio-middleware/tests -p "test_*.py"
