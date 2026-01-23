## Project Restructuring Plan

### Phase 1: Directory Restructure
1. Create `backend/` directory and move:
   - `monitor_module/` → `backend/modules/monitor/`
   - `agent/` → `backend/modules/agent/`
   - `config/` → `backend/modules/config/`
   - `data/`, `logs/` → `backend/data/`, `backend/logs/`
   - `config.yaml`, `pyproject.toml`, `.env` → `backend/`

2. Create `frontend/` directory with React + Vite + TypeScript

3. Update all Python import paths to reflect new structure

### Phase 2: FastAPI Backend
1. Create `backend/app/` with FastAPI application:
   - `main.py` - Entry point with lifespan management
   - `api/routes/` - REST endpoints for monitor, agent, workflow, positions, alerts
   - `api/websocket.py` - WebSocket handler for real-time events
   - `services/process_manager.py` - Subprocess lifecycle management
   - `core/events.py` - Event bus for internal communication

2. Key API endpoints:
   - `GET/POST /api/monitor/{start|stop|status}`
   - `GET/POST /api/agent/{start|stop|status}`
   - `GET/POST /api/workflow/{start|stop|status}`
   - `GET /api/alerts` - Alert history
   - `GET /api/positions` - Current positions
   - `GET/PUT /api/config` - Configuration management
   - `WS /ws/events` - Real-time event stream

3. Add dependencies to `pyproject.toml`:
   - `fastapi`, `uvicorn`, `python-multipart`

### Phase 3: React Frontend
1. Initialize with: `npm create vite@latest frontend -- --template react-ts`

2. Install dependencies:
   - `@tanstack/react-query` - Data fetching
   - `zustand` - State management
   - `tailwindcss` - Styling
   - `recharts` - Charts
   - `lucide-react` - Icons

3. Create components:
   - Dashboard (system status, quick actions)
   - Alerts (alert history table, filters)
   - Positions (current positions, P&L)
   - Settings (config editor)
   - Real-time log viewer

### Phase 4: Integration
1. Create `Makefile` with unified commands:
   - `make dev` - Start both backend and frontend
   - `make backend` - Start backend only
   - `make frontend` - Start frontend only
   - `make build` - Build for production

2. Update `README.md` with new setup instructions

3. Optional: Add `docker-compose.yml` for containerized deployment

### Files to Delete After Migration
- `run_agent.sh`, `run_monitor.sh`, `run_workflow.sh`, `run_dashboard.sh`
- `stop_python.sh`
- `web_dashboard/` (replaced by new frontend)
- `faas/` (if no longer needed)