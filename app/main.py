import os
from fastapi import FastAPI
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.core.config import settings
from app.api.router import router

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

# Middleware
# app.add_middleware(HTTPSRedirectMiddleware) # Optional, depends on deployment
# app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_IPS) # TrustedHost checks Host header, not IP.

app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    # Check if SSL files exist
    ssl_key = settings.SSL_KEYFILE if os.path.exists(settings.SSL_KEYFILE) else None
    ssl_cert = settings.SSL_CERTFILE if os.path.exists(settings.SSL_CERTFILE) else None

    print(f"Starting server on port 8443 (SSL: {'Enabled' if ssl_key and ssl_cert else 'Disabled'})")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8443,
        reload=False,
        ssl_keyfile=ssl_key,
        ssl_certfile=ssl_cert
    )
