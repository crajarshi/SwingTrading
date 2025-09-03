SHELL := /bin/bash

# Config
PY ?= venv/bin/python
PID_FILE ?= .server.pid
LOG_FILE ?= server.log
PORT ?= 8002

.PHONY: help deps ui-start ui-stop ui-restart ui-logs ui-status

help:
	@echo "Targets:"
	@echo "  deps        - Create venv (if needed) and install NumPy/SciPy"
	@echo "  ui-start    - Start v2 server in background (nohup)"
	@echo "  ui-stop     - Stop background server"
	@echo "  ui-restart  - Restart background server"
	@echo "  ui-logs     - Tail server.log"
	@echo "  ui-status   - Show server status"

deps:
	@# Ensure virtualenv exists
	@if [ ! -x "$(PY)" ]; then \
		echo "Creating virtualenv in ./venv"; \
		python3 -m venv venv; \
	fi
	@$(PY) -m pip install --upgrade pip
	@$(PY) -m pip install numpy scipy

ui-start:
	@# Create venv if missing
	@if [ ! -x "$(PY)" ]; then \
		echo "Creating virtualenv in ./venv"; \
		python3 -m venv venv; \
	fi
	@# Start server if not already running
	@if [ -f "$(PID_FILE)" ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "Server already running (PID $$(cat $(PID_FILE)))."; \
	else \
		echo "Starting server on port $(PORT)..."; \
		nohup $(PY) working_server_v2.py > $(LOG_FILE) 2>&1 & echo $$! > $(PID_FILE); \
		sleep 1; \
		echo "Logs: $(LOG_FILE). PID: $$(cat $(PID_FILE))."; \
		echo "Open http://localhost:$(PORT)/working.html"; \
	fi

ui-stop:
	@if [ -f "$(PID_FILE)" ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "Stopping PID $$(cat $(PID_FILE))..."; \
		kill $$(cat $(PID_FILE)) || true; \
		rm -f $(PID_FILE); \
	else \
		echo "No PID file or server not running; attempting pkill..."; \
		pkill -f working_server_v2.py || true; \
		rm -f $(PID_FILE); \
	fi

ui-restart: ui-stop ui-start

ui-logs:
	@if [ -f "$(LOG_FILE)" ]; then \
		tail -f $(LOG_FILE); \
	else \
		echo "No $(LOG_FILE) yet. Start the server first (make ui-start)."; \
	fi

ui-status:
	@if [ -f "$(PID_FILE)" ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "Server running (PID $$(cat $(PID_FILE))). Open http://localhost:$(PORT)/working.html"; \
	else \
		echo "Server not running."; \
	fi

