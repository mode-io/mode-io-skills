.PHONY: prompt-gateway-setup prompt-gateway-uninstall prompt-gateway-tests precommit-scan-setup precommit-scan-uninstall precommit-scan-tests

PYTHON ?= python3

prompt-gateway-setup:
	$(PYTHON) modeio-redact/scripts/setup_prompt_gateway.py --client both

prompt-gateway-uninstall:
	$(PYTHON) modeio-redact/scripts/setup_prompt_gateway.py --client both --uninstall --apply-opencode --cleanup-maps

prompt-gateway-tests:
	$(PYTHON) -m unittest modeio-redact.tests.test_setup_prompt_gateway
	$(PYTHON) -m unittest discover modeio-redact/tests -p "test_prompt_gateway*.py"

precommit-scan-setup:
	$(PYTHON) modeio-redact/scripts/setup_precommit_scan.py

precommit-scan-uninstall:
	$(PYTHON) modeio-redact/scripts/setup_precommit_scan.py --uninstall

precommit-scan-tests:
	$(PYTHON) -m unittest modeio-redact.tests.test_precommit_scan
	$(PYTHON) -m unittest modeio-redact.tests.test_setup_precommit_scan
	$(PYTHON) -m unittest modeio-redact.tests.test_precommit_cli_integration
