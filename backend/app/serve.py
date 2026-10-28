"""One server for the KidNee demo: the built screens and the API, on loopback only.

The browser calls `/api/...` in every mode. In dev, Vite proxies `/api` to the
backend and strips the prefix. Here the unchanged API app is mounted at `/api`, so
the mount strips it the same way, and `frontend/dist` is served at `/`. The screens
use hash routes (`#/months`), so no history fallback is needed. The API's own routes
stay at the root for tests, curl and `app.main:app` (Session 15A, L73).

Run it with `uv run python -m demo.kidnee serve`, which binds 127.0.0.1 only: there
is no end-user auth (L60 1).
"""

from pathlib import Path

from fastapi import FastAPI
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.routing import BaseRoute, Mount
from starlette.staticfiles import StaticFiles

from app.main import ALLOWED_HOSTS

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_serving_app(api: FastAPI, dist: Path | None = FRONTEND_DIST) -> Starlette:
    """`api` at /api, and `dist` at / when it holds a build (index.html). Without a
    build only /api is served, so the API works before `npm run build`."""
    routes: list[BaseRoute] = [Mount("/api", app=api)]
    if dist is not None and (dist / "index.html").is_file():
        # follow_symlink stays False: nothing outside dist is ever served.
        routes.append(Mount("/", app=StaticFiles(directory=dist, html=True)))
    return Starlette(
        routes=routes,
        # S8 on the outer app too: a DNS-rebinding Host gets 400 before any route.
        middleware=[Middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)],
    )
