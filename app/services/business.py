import os
from app.ports.interfaces import NginxPort, CertbotPort, FileSystemPort
from app.models.domain import DeployRequest, CacheInfo
from app.core.config import settings

class NodeService:
    def __init__(self, nginx: NginxPort, certbot: CertbotPort, fs: FileSystemPort):
        self.nginx = nginx
        self.certbot = certbot
        self.fs = fs

    def deploy_node(self, req: DeployRequest) -> dict:
        primary_domain = req.domains[0]
        domain_str = " ".join(req.domains)
        cache_dir = os.path.join(settings.CACHE_BASE, primary_domain)

        # 1. Create Cache Directory
        self.fs.create_dir(cache_dir, owner="www-data:www-data")

        # 2. Generate Certs
        # Check if cert already exists to avoid rate limits?
        # For now we assume strict idempotent behavior as per original script logic (it blindly runs certbot)
        # But `certbot certonly` handles renewal if close to expiry, or skips if valid.
        try:
            self.certbot.generate_cert(req.domains, req.dns_provider)
        except Exception as e:
            raise RuntimeError(f"Cert generation failed: {e}")

        # 3. Create Nginx Config
        config_content = self._generate_nginx_config(
            primary_domain=primary_domain,
            domain_str=domain_str,
            origin_proto=req.origin_proto,
            origin_ip=req.origin_ip,
            origin_port=req.origin_port,
            cache_dir=cache_dir
        )

        self.nginx.create_site_config(primary_domain, config_content)

        return {
            "status": "success",
            "domains": req.domains,
            "origin": f"{req.origin_proto}://{req.origin_ip}:{req.origin_port}",
            "dns_provider": req.dns_provider,
            "cache_dir": cache_dir
        }

    def delete_node(self, domain: str) -> None:
        cache_dir = os.path.join(settings.CACHE_BASE, domain)

        self.nginx.delete_site_config(domain)
        self.fs.remove_dir(cache_dir)
        self.certbot.delete_cert(domain)
        # Nginx reload is handled by delete_site_config

    def get_nodes(self) -> list[str]:
        return self.nginx.list_sites()

    def get_origin(self, domain: str) -> list[str]:
        return self.nginx.get_proxy_pass_lines(domain)

    def update_origin(self, domain: str, ip: str, port: int, proto: str) -> None:
        self.nginx.update_proxy_pass(domain, proto, ip, port)

    def _generate_nginx_config(self, primary_domain, domain_str, origin_proto, origin_ip, origin_port, cache_dir):
        # This template should ideally be loaded from a file or a template engine like Jinja2
        return f"""
proxy_cache_path {cache_dir} levels=1:2 keys_zone={primary_domain}_cache:100m inactive=30d max_size=2g;

server {{
    listen 443 ssl http2;
    server_name {domain_str};

    ssl_certificate /etc/letsencrypt/live/{primary_domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{primary_domain}/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/{primary_domain}/chain.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_stapling on;
    ssl_stapling_verify on;

    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header Referrer-Policy no-referrer;
    add_header Permissions-Policy "geolocation=(), microphone=()";
    add_header X-CDN "Bastivan";
    add_header Server "cdn-x-eu";

    location / {{
        proxy_pass {origin_proto}://{origin_ip}:{origin_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        proxy_cache {primary_domain}_cache;
        proxy_cache_valid 200 30d;
        proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
        proxy_cache_background_update on;
        proxy_ignore_headers Set-Cookie Cache-Control;

        add_header X-Cache $upstream_cache_status always;
        add_header X-CDN "Bastivan";
    }}

    access_log /var/log/nginx/{primary_domain}_access.log;
    error_log /var/log/nginx/{primary_domain}_error.log;
}}

server {{
    listen 80;
    server_name {domain_str};
    return 301 https://$host$request_uri;
}}
"""

class CacheService:
    def __init__(self, nginx: NginxPort, fs: FileSystemPort):
        self.nginx = nginx
        self.fs = fs

    def enable_cache(self, domain: str) -> None:
        self.nginx.update_cache_directives(domain, enable_cache=True)

    def disable_cache(self, domain: str, eol: bool) -> None:
        self.nginx.update_cache_directives(domain, enable_cache=False, eol=eol)

    def get_cache_info(self, domain: str) -> CacheInfo:
        cache_dir = os.path.join(settings.CACHE_BASE, domain)
        if not os.path.isdir(cache_dir):
            raise FileNotFoundError("Cache directory not found")

        files = self.fs.list_files_recursive(cache_dir)
        return CacheInfo(
            domain=domain,
            file_count=len(files),
            files=[{"file": f[0], "size_bytes": f[1]} for f in files]
        )

    def clear_cache(self, domain: str) -> int:
        cache_dir = os.path.join(settings.CACHE_BASE, domain)
        return self.fs.clear_dir(cache_dir)

class SystemService:
    def __init__(self, nginx: NginxPort):
        self.nginx = nginx

    def reload_nginx(self):
        self.nginx.test_config()
        self.nginx.reload()
