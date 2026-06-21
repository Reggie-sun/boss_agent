SHELL := /bin/bash

CDP_HOST ?= 127.0.0.1
CDP_PORT ?= 9229
CDP_PROFILE ?= $(HOME)/.boss-agent/chrome-cdp-agent
CDP_URL := http://$(CDP_HOST):$(CDP_PORT)
CDP_START_URL ?= https://www.zhipin.com/web/geek/chat
CDP_UNIT ?= boss-agent-cdp-$(CDP_PORT)
CHROME ?= $(shell if [ -x /opt/google/chrome/chrome ]; then echo /opt/google/chrome/chrome; else command -v google-chrome 2>/dev/null || command -v google-chrome-stable 2>/dev/null || command -v chromium 2>/dev/null || command -v chromium-browser 2>/dev/null; fi)
PYTHON ?= python
BOSS_DATA_DIR ?= $(HOME)/.boss-agent
RESUME_ATTACHMENT_PATH ?= $(CURDIR)/孙瑞杰的简历.pdf
AGENT_PROACTIVE_RESUME ?= true
AGENT_READ_NO_REPLY_LIMIT ?= 1
BOSS_CLI ?= $(PYTHON) -c 'from boss_agent_cli.main import cli; import sys; cli.main(args=sys.argv[1:])'

.PHONY: help cdp cdp-check cdp-url agent-auto-reply

help:
	@echo "Targets:"
	@echo "  make cdp               Start a real Chrome with CDP on $(CDP_URL)"
	@echo "  make cdp-check         Check whether $(CDP_URL) exposes DevTools"
	@echo "  make cdp-url           Print the CDP URL"
	@echo "  make agent-auto-reply  Start live Boss Agent auto replies"
	@echo ""
	@echo "Variables:"
	@echo "  CHROME=/path/to/chrome CDP_PORT=9229 CDP_PROFILE=$(CDP_PROFILE)"
	@echo "  PYTHON=python BOSS_DATA_DIR=$(BOSS_DATA_DIR)"
	@echo "  RESUME_ATTACHMENT_PATH=$(RESUME_ATTACHMENT_PATH)"
	@echo "  AGENT_PROACTIVE_RESUME=$(AGENT_PROACTIVE_RESUME)"
	@echo "  AGENT_READ_NO_REPLY_LIMIT=$(AGENT_READ_NO_REPLY_LIMIT)"

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

agent-auto-reply: cdp-check
	@echo "Starting live Boss Agent auto replies on $(CDP_URL)"
	@echo "Data dir: $(BOSS_DATA_DIR)"
	@echo "Resume attachment: $(RESUME_ATTACHMENT_PATH)"
	PYTHONPATH="$(CURDIR)/src$${PYTHONPATH:+:$$PYTHONPATH}" \
	BOSS_RAG_ALLOW_MESSAGE_READ=true \
	BOSS_RAG_SEND_ENABLED=true \
	BOSS_RAG_WATCHER_ENABLED=true \
	BOSS_RAG_WATCHER_DRY_RUN=false \
	BOSS_RAG_WATCHER_LIVE_SYNC=true \
	BOSS_RAG_PROACTIVE_RESUME_ENABLED=$(AGENT_PROACTIVE_RESUME) \
	BOSS_RAG_READ_NO_REPLY_FOLLOWUP_LIMIT_PER_CYCLE=$(AGENT_READ_NO_REPLY_LIMIT) \
	BOSS_RAG_RESUME_ATTACHMENT_PATH="$(RESUME_ATTACHMENT_PATH)" \
	$(BOSS_CLI) --data-dir "$(BOSS_DATA_DIR)" --cdp-url "$(CDP_URL)" agent watcher-run --loop --live-sync --ensure-chat-page
