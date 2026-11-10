import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from app import app as flask_app


class PrefixMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        # Try multiple headers Vercel may set for original path
        real_path = None

        for header in [
            "HTTP_X_FORWARDED_URI",
            "HTTP_X_NOW_ROUTE_MATCHES",
            "HTTP_X_MATCHED_PATH",
            "HTTP_X_ORIGINAL_URL",
            "HTTP_X_REWRITE_URL",
        ]:
            val = environ.get(header, "")
            if val and val.startswith("/") and not val.startswith("/api/index"):
                real_path = val.split("?")[0]
                break

        if real_path:
            environ["PATH_INFO"] = real_path
        else:
            # Strip /api/index prefix if present (local fallback)
            path = environ.get("PATH_INFO", "")
            if path.startswith("/api/index"):
                environ["PATH_INFO"] = path[len("/api/index"):] or "/"

        # Also fix REQUEST_METHOD — Vercel sometimes passes wrong method
        # via header when rewriting
        method_override = environ.get("HTTP_X_HTTP_METHOD_OVERRIDE", "")
        if method_override:
            environ["REQUEST_METHOD"] = method_override.upper()

        return self.wsgi_app(environ, start_response)


app = PrefixMiddleware(flask_app)
