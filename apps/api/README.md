# API integration boundary

FastAPI routes, PostgreSQL persistence and Celery workers are the next implementation phase.
They must import contracts from `visora_engine.schemas` and orchestrate the engine, not duplicate it.
The current local harness has no HTTP server, credentials, Redis or external provider clients.
