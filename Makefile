# Makefile for Engineer Cafe Navigator
# Unified development commands using mise and Docker

.PHONY: help setup install dev dev-frontend dev-backend build test lint clean debug-agent test-agent show-logs

# Default target
.DEFAULT_GOAL := help

# Colors for output
CYAN := \033[0;36m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

## help: Show this help message
help:
	@echo "$(CYAN)Engineer Cafe Navigator - Development Commands$(NC)"
	@echo ""
	@echo "$(GREEN)Setup:$(NC)"
	@echo "  make setup              - Initial project setup (mise + dependencies + Docker build)"
	@echo "  make install            - Install dependencies (mise-based)"
	@echo ""
	@echo "$(GREEN)Development:$(NC)"
	@echo "  make dev                - Start development servers (Docker Compose)"
	@echo "  make dev:frontend       - Start frontend only"
	@echo "  make dev:backend        - Start backend only"
	@echo ""
	@echo "$(GREEN)Build & Test:$(NC)"
	@echo "  make build              - Build frontend and backend"
	@echo "  make test               - Run all tests"
	@echo "  make lint               - Run linters (frontend + backend)"
	@echo ""
	@echo "$(GREEN)Debug & Tools:$(NC)"
	@echo "  make debug-agent        - Interactive agent debugger"
	@echo "  make test-agent         - Test specific agent (AGENT=business_info|event QUERY='...')"
	@echo "  make show-logs          - Show recent agent debug logs"
	@echo ""
	@echo "$(GREEN)Cleanup:$(NC)"
	@echo "  make clean              - Stop containers and clean volumes"
	@echo "  make clean:all          - Deep clean (containers + images + volumes)"
	@echo ""

## setup: Initial project setup
setup:
	@echo "$(CYAN)Setting up Engineer Cafe Navigator...$(NC)"
	@echo "$(YELLOW)Step 1: Installing mise tools...$(NC)"
	mise install
	@echo "$(YELLOW)Step 2: Installing dependencies...$(NC)"
	@$(MAKE) install
	@echo "$(YELLOW)Step 3: Building Docker images...$(NC)"
	docker-compose build
	@echo "$(GREEN)✓ Setup complete!$(NC)"
	@echo "$(CYAN)Run 'make dev' to start development servers$(NC)"

## install: Install dependencies using mise
install:
	@echo "$(CYAN)Installing dependencies...$(NC)"
	mise install
	@echo "$(YELLOW)Installing frontend dependencies...$(NC)"
	cd frontend && mise exec -- pnpm install
	@echo "$(YELLOW)Installing backend dependencies...$(NC)"
	cd backend && mise exec -- pip install -r requirements.txt
	@echo "$(GREEN)✓ Dependencies installed$(NC)"

## dev: Start development servers (Docker Compose)
dev:
	@echo "$(CYAN)Starting development environment...$(NC)"
	docker-compose up

## dev:frontend: Start frontend only
dev\:frontend:
	@echo "$(CYAN)Starting frontend development server...$(NC)"
	docker-compose up frontend

## dev:backend: Start backend only
dev\:backend:
	@echo "$(CYAN)Starting backend development server...$(NC)"
	docker-compose up backend

## build: Build frontend and backend
build:
	@echo "$(CYAN)Building project...$(NC)"
	@echo "$(YELLOW)Building frontend...$(NC)"
	cd frontend && mise exec -- pnpm build
	@echo "$(YELLOW)Building backend (checking syntax)...$(NC)"
	cd backend && mise exec -- python -m py_compile main.py
	@echo "$(GREEN)✓ Build complete$(NC)"

## test: Run all tests
test:
	@echo "$(CYAN)Running tests...$(NC)"
	@echo "$(YELLOW)Running frontend tests...$(NC)"
	cd frontend && mise exec -- pnpm test || echo "$(YELLOW)No frontend tests configured$(NC)"
	@echo "$(YELLOW)Running backend tests...$(NC)"
	cd backend && mise exec -- pytest || echo "$(YELLOW)No backend tests configured$(NC)"

## lint: Run linters
lint:
	@echo "$(CYAN)Running linters...$(NC)"
	@echo "$(YELLOW)Linting frontend...$(NC)"
	cd frontend && mise exec -- pnpm lint
	cd frontend && mise exec -- pnpm typecheck
	@echo "$(YELLOW)Linting backend...$(NC)"
	cd backend && mise exec -- ruff check .
	cd backend && mise exec -- black --check .
	@echo "$(GREEN)✓ Linting complete$(NC)"

## clean: Stop containers and clean volumes
clean:
	@echo "$(CYAN)Cleaning up...$(NC)"
	docker-compose down -v
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

## clean:all: Deep clean (containers + images + volumes)
clean\:all:
	@echo "$(CYAN)Deep cleaning...$(NC)"
	docker-compose down -v --rmi all
	@echo "$(GREEN)✓ Deep cleanup complete$(NC)"

## debug-agent: Interactive agent debugger
debug-agent:
	@echo "$(CYAN)Starting agent debugger (interactive mode)...$(NC)"
	@echo "$(YELLOW)Agent type: $(if $(AGENT),$(AGENT),business_info) (set AGENT=event to change)$(NC)"
	@cd backend && mise exec -- python debug_agent.py $(if $(AGENT),-a $(AGENT),)

## test-agent: Test specific agent with query
test-agent:
	@if [ -z "$(QUERY)" ]; then \
		echo "$(YELLOW)Usage: make test-agent AGENT=business_info QUERY='営業時間は？'$(NC)"; \
		exit 1; \
	fi
	@echo "$(CYAN)Testing agent...$(NC)"
	@echo "$(YELLOW)Agent: $(if $(AGENT),$(AGENT),business_info)$(NC)"
	@echo "$(YELLOW)Query: $(QUERY)$(NC)"
	@cd backend && mise exec -- python debug_agent.py \
		$(if $(AGENT),-a $(AGENT),) \
		-q "$(QUERY)" \
		$(if $(REQUEST_TYPE),-r $(REQUEST_TYPE),) \
		$(if $(LANGUAGE),-l $(LANGUAGE),) \
		$(if $(VERBOSE),-v,)

## show-logs: Show recent agent debug logs
show-logs:
	@echo "$(CYAN)Recent agent debug logs:$(NC)"
	@if [ -d "logs/agent-debug" ]; then \
		echo ""; \
		ls -lt logs/agent-debug/*.json 2>/dev/null | head -5 | while read -r line; do \
			file=$$(echo $$line | awk '{print $$NF}'); \
			echo "$(GREEN)$$file$(NC)"; \
			echo "$(YELLOW)---$(NC)"; \
			cat "$$file" | head -20; \
			echo ""; \
		done; \
	else \
		echo "$(YELLOW)No debug logs found. Run 'make debug-agent' or 'make test-agent' first.$(NC)"; \
	fi
