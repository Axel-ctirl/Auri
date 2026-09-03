# FastAPI Project

Routers, Pydantic schemas, dependencies, background work and testing.

You are helping with a **FastAPI** project.

Structure it so it survives growing past one file:

```
app/
  main.py        # create_app, middleware, router wiring
  config.py      # pydantic-settings, read once
  db.py          # engine and session dependency
  models.py      # ORM tables
  schemas.py     # Pydantic request/response models
  routers/       # one module per resource
  services/      # business logic, no FastAPI imports
```

Conventions to follow:

- Separate ORM models from Pydantic schemas. Returning an ORM object directly
  leaks columns you did not mean to expose.
- Declare `response_model` on every route. It documents the contract and strips
  anything extra.
- Get dependencies through `Depends`. A session dependency that yields and
  closes is the standard shape; do not open sessions inside route bodies.
- Async routes must be async all the way down. One blocking call inside an
  `async def` stalls the whole event loop. If the library is sync, use a normal
  `def` route and let FastAPI run it in a threadpool.
- Register exception handlers so every error returns the same JSON shape,
  including validation errors.
- Configure CORS explicitly. `allow_origins=["*"]` together with
  `allow_credentials=True` is rejected by browsers and is a mistake anyway.
- Test with `TestClient` (or `httpx.AsyncClient`) against a temporary database,
  overriding the session dependency.

For streaming, use `StreamingResponse` with Server-Sent Events unless the client
genuinely needs to send data mid-stream, which is when a WebSocket earns its
complexity.
