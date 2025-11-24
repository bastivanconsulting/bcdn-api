import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    API_KEY: str = os.getenv("API_KEY", "changeme")
    # Restore original default allowed IPs
    ALLOWED_IPS: list[str] = os.getenv("ALLOWED_IPS", "127.0.0.1,116.203.239.241").split(",")

    # Paths
    NGINX_SITES_AVAILABLE: str = os.getenv("NGINX_SITES_AVAILABLE", "/etc/nginx/sites-available")
    NGINX_SITES_ENABLED: str = os.getenv("NGINX_SITES_ENABLED", "/etc/nginx/sites-enabled")
    CACHE_BASE: str = os.getenv("CACHE_BASE", "/var/bcdn")

    # Certbot
    CERTBOT_EMAIL: str = os.getenv("CERTBOT_EMAIL", "contact@bastivan.com")
    CLOUDFLARE_INI: str = os.getenv("CLOUDFLARE_INI", "/root/.secrets/certbot/cloudflare.ini")
    AWS_INI: str = os.getenv("AWS_INI", "/root/.secrets/certbot/aws.ini")

    # SSL (for the API itself)
    SSL_KEYFILE: str = os.getenv("SSL_KEYFILE", "/srv/api/certs/privkey.pem")
    SSL_CERTFILE: str = os.getenv("SSL_CERTFILE", "/srv/api/certs/fullchain.pem")

    # App
    PROJECT_NAME: str = "Bastivan CDN Node API"
    VERSION: str = "2.0.0"

settings = Settings()
