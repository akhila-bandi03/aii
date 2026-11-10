import sys
import os
from urllib.parse import parse_qs, urlencode

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from app import app as flask_app


class PrefixMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        # 1. Check if Vercel passed the real path via rewrite query param ?__url=...
        qs = environ.get("QUERY_STRING", "")
        if "__url=" in qs:
            params = parse_qs(qs, keep_blank_values=True)
            if "__url" in params:
                real_path = params["__url"][0]
                if real_path:
                    while real_path.startswith("//"):
                        real_path = real_path[1:]
                    environ["PATH_INFO"] = real_path if real_path.startswith("/") else "/" + real_path
                del params["__url"]
                environ["QUERY_STRING"] = urlencode(params, doseq=True)
                return self.wsgi_app(environ, start_response)

        # 2. Check headers that Vercel or proxies might set
        for h in [
            "HTTP_X_FORWARDED_URI",
            "HTTP_X_VERCEL_FORWARDED_URI",
            "HTTP_X_MATCHED_PATH",
            "HTTP_X_ORIGINAL_URL",
            "HTTP_X_REWRITE_URL",
        ]:
            val = environ.get(h, "")
            if val and val.startswith("/") and not val.startswith("/api"):
                environ["PATH_INFO"] = val.split("?")[0]
                return self.wsgi_app(environ, start_response)

        # 3. Fallback: strip /api/index prefix
        path = environ.get("PATH_INFO", "")
        if path.startswith("/api/index"):
            path = path[len("/api/index"):] or "/"
            environ["PATH_INFO"] = path

        return self.wsgi_app(environ, start_response)


app = PrefixMiddleware(flask_app)
