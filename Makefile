.PHONY: help install dev backend frontend build clean

BACKEND_DIR = backend
FRONTEND_DIR = frontend

help:
	@echo "Crypto Monitor - Development Commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  install     Install all dependencies (backend + frontend)"
	@echo "  dev         Start both backend and frontend in development mode"
	@echo "  backend     Start backend server only"
	@echo "  frontend    Start frontend dev server only"
	@echo "  build       Build frontend for production"
	@echo "  clean       Clean build artifacts"
	@echo ""

install: install-backend install-frontend

install-backend:
	@echo "Installing backend dependencies..."
	cd $(BACKEND_DIR) && uv sync

install-frontend:
	@echo "Installing frontend dependencies..."
	cd $(FRONTEND_DIR) && npm install

dev:
	@echo "Starting development servers..."
	@make -j2 backend frontend

backend:
	@echo "Starting backend server on http://localhost:8000"
	cd $(BACKEND_DIR) && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	@echo "Starting frontend dev server on http://localhost:3000"
	cd $(FRONTEND_DIR) && npm run dev

build:
	@echo "Building frontend for production..."
	cd $(FRONTEND_DIR) && npm run build

clean:
	@echo "Cleaning build artifacts..."
	rm -rf $(FRONTEND_DIR)/dist
	rm -rf $(BACKEND_DIR)/__pycache__
	find $(BACKEND_DIR) -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find $(BACKEND_DIR) -type f -name "*.pyc" -delete 2>/dev/null || true

lint-backend:
	@echo "Linting backend code..."
	cd $(BACKEND_DIR) && uv run ruff check .

lint-frontend:
	@echo "Linting frontend code..."
	cd $(FRONTEND_DIR) && npm run lint

format-backend:
	@echo "Formatting backend code..."
	cd $(BACKEND_DIR) && uv run ruff format .

typecheck-frontend:
	@echo "Type checking frontend..."
	cd $(FRONTEND_DIR) && npm run build
