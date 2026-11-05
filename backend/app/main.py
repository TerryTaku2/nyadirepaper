"""Nyadire College Past Papers Portal - FastAPI application.

Run from the backend/ folder:   uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import admin, auth, config, content
from .db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Nyadire Past Papers Portal API", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(content.router)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # CSRF defence in depth (cookies are already SameSite=Strict): refuse cross-origin writes.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin.split("://", 1)[-1] != request.headers.get("host"):
            return JSONResponse({"detail": "Cross-origin request blocked."}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/api/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------------------- front-end
# Only the page, its script and the image assets are served. Uploaded PDFs live outside
# these folders and can only be fetched through the authenticated /api routes.
app.mount("/assets", StaticFiles(directory=config.STATIC_DIR / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(config.STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/app.js", include_in_schema=False)
def app_js():
    return FileResponse(config.STATIC_DIR / "app.js", media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})
