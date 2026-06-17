SHELL := /bin/bash

CDP_HOST ?= 127.0.0.1
CDP_PORT ?= 9222
CDP_PROFILE ?= $(HOME)/.boss-agent/chrome-cdp-agent
CDP_URL := http://$(CDP_HOST):$(CDP_PORT)
CDP_START_URL ?= https://www.zhipin.com/web/geek/chat
CDP_UNIT ?= boss-agent-cdp-$(CDP_PORT)
CHROME ?= $(shell if [ -x /opt/google/chrome/chrome ]; then echo /opt/google/chrome/chrome; else command -v google-chrome 2>/dev/null || command -v google-chrome-stable 2>/dev/null || command -v chromium 2>/dev/null || command -v chromium-browser 2>/dev/null; fi)

.PHONY: help cdp cdp-check cdp-url

help:
	@echo "Targets:"
	@echo "  make cdp        Start a real Chrome with CDP on $(CDP_URL)"
	@echo "  make cdp-check  Check whether $(CDP_URL) exposes DevTools"
	@echo "  make cdp-url    Print the CDP URL"
	@echo ""
	@echo "Variables:"
	@echo "  CHROME=/path/to/chrome CDP_PORT=9222 CDP_PROFILE=$(CDP_PROFILE)"

cdp:
	@if [ -z "$(CHROME)" ]; then \
		echo "Chrome executable not found. Set CHROME=/path/to/chrome and retry."; \
		exit 1; \
	fi
	@mkdir -p "$(CDP_PROFILE)"
	@echo "Starting Chrome CDP: $(CDP_URL)"
	@echo "Profile: $(CDP_PROFILE)"
	@rm -f /tmp/boss-agent-cdp.log /tmp/boss-agent-cdp.pid
	@if command -v systemd-run >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then \
		systemctl --user stop "$(CDP_UNIT)" >/dev/null 2>&1 || true; \
		systemd-run --user --unit="$(CDP_UNIT)" --collect \
			env DISPLAY="$${DISPLAY:-}" WAYLAND_DISPLAY="$${WAYLAND_DISPLAY:-}" XDG_RUNTIME_DIR="$${XDG_RUNTIME_DIR:-}" DBUS_SESSION_BUS_ADDRESS="$${DBUS_SESSION_BUS_ADDRESS:-}" \
			"$(CHROME)" \
			--remote-debugging-address="$(CDP_HOST)" \
			--remote-debugging-port="$(CDP_PORT)" \
			--user-data-dir="$(CDP_PROFILE)" \
			--no-first-run \
			--no-default-browser-check \
			"$(CDP_START_URL)" >/tmp/boss-agent-cdp.log 2>&1; \
	else \
		setsid -f "$(CHROME)" \
			--remote-debugging-address="$(CDP_HOST)" \
			--remote-debugging-port="$(CDP_PORT)" \
			--user-data-dir="$(CDP_PROFILE)" \
			--no-first-run \
			--no-default-browser-check \
			"$(CDP_START_URL)" >/tmp/boss-agent-cdp.log 2>&1; \
	fi
	@for i in $$(seq 1 20); do \
		if $(MAKE) --no-print-directory cdp-check >/tmp/boss-agent-cdp-check.out 2>&1; then \
			cat /tmp/boss-agent-cdp-check.out; \
			pgrep -f -- "--remote-debugging-port=$(CDP_PORT).*--user-data-dir=$(CDP_PROFILE)" | head -n 1 >/tmp/boss-agent-cdp.pid || true; \
			exit 0; \
		fi; \
		if [ "$$i" -eq 20 ]; then \
			cat /tmp/boss-agent-cdp-check.out; \
			cat /tmp/boss-agent-cdp.log 2>/dev/null || true; \
			systemctl --user status "$(CDP_UNIT)" --no-pager 2>/dev/null || true; \
			exit 1; \
		fi; \
		sleep 0.5; \
	done

cdp-check:
	@python -c 'import json, urllib.request; payload=json.load(urllib.request.urlopen("$(CDP_URL)/json/version", timeout=3)); ws=payload.get("webSocketDebuggerUrl"); assert ws, "missing webSocketDebuggerUrl"; print("CDP ready: $(CDP_URL)"); print(ws)'

cdp-url:
	@echo "$(CDP_URL)"
