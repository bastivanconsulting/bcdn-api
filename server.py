from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import List, Literal
import subprocess
import os
import shutil
import uvicorn
import re
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel

class CacheToggleRequest(BaseModel):
    eol: bool = False


app = FastAPI(title="Bastivan CDN Node API", version="1.4")

# === Configuration ===
CERTBOT_EMAIL = "contact@bastivan.com"
CLOUDFLARE_INI = "/root/.secrets/certbot/cloudflare.ini"
AWS_INI = "/root/.secrets/certbot/aws.ini"
NGINX_SITES_AVAILABLE = "/etc/nginx/sites-available"
NGINX_SITES_ENABLED = "/etc/nginx/sites-enabled"
CACHE_BASE = "/var/bcdn"
API_KEY = ""
ALLOWED_IPS = ["116.203.239.241", "127.0.0.1"]

api_key_header = APIKeyHeader(name="X-API-Key")

class UpdateOriginRequest(BaseModel):
    origin_ip: str
    origin_port: int = 443
    origin_proto: str = "https"


class DeployRequest(BaseModel):
    domains: List[str]
    origin_ip: str
    origin_port: int = 443
    origin_proto: str = "https"
    dns_provider: Literal["cloudflare", "aws"] = "cloudflare"

def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Clé API invalide")

def verify_ip(request: Request):
    client_ip = request.client.host
    if client_ip not in ALLOWED_IPS:
        raise HTTPException(status_code=403, detail=f"IP non autorisée : {client_ip}")

def get_proxy_pass_config(domain: str) -> List[str]:
    conf_path = os.path.join(NGINX_SITES_AVAILABLE, domain)
    if not os.path.isfile(conf_path):
        raise HTTPException(status_code=404, detail="Fichier de configuration introuvable")

    try:
        proxy_lines = []
        with open(conf_path, "r") as f:
            for line in f:
                if "proxy_pass" in line:
                    proxy_lines.append(line.strip())

        if not proxy_lines:
            return ["Aucune directive proxy_pass trouvée"]

        return proxy_lines

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lecture proxy_pass : {str(e)}")


def update_nginx_proxy_pass(domain: str, origin_ip: str, origin_port: int, origin_proto: str):
    conf_path = os.path.join(NGINX_SITES_AVAILABLE, domain)
    if not os.path.isfile(conf_path):
        raise HTTPException(status_code=404, detail="Fichier de configuration introuvable")

    try:
        with open(conf_path, "r") as f:
            lines = f.readlines()

        new_lines = []
        for line in lines:
            if line.strip().startswith("proxy_pass"):
                new_line = f"        proxy_pass {origin_proto}://{origin_ip}:{origin_port};\n"
                new_lines.append(new_line)
            else:
                new_lines.append(line)

        with open(conf_path, "w") as f:
            f.writelines(new_lines)

        test = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
        if test.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Erreur config Nginx :\n{test.stderr}")

        subprocess.run(["systemctl", "reload", "nginx"], check=True)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur modification proxy_pass : {str(e)}")



def update_nginx_cache_directives(domain: str, enable_cache: bool, eol: bool = False):
    conf_path = os.path.join(NGINX_SITES_AVAILABLE, domain)
    if not os.path.isfile(conf_path):
        raise HTTPException(status_code=404, detail="Configuration Nginx introuvable")

    try:
        with open(conf_path, "r") as f:
            lines = f.readlines()

        new_lines = []
        inside_location = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("location /"):
                inside_location = True

            if inside_location:
                # On ignore uniquement les lignes liées au cache
                if any(stripped.startswith(key) for key in [
                    "proxy_cache", "proxy_cache_valid", "proxy_cache_use_stale",
                    "proxy_cache_background_update", "proxy_ignore_headers", "add_header X-Cache"
                ]):
                    continue

                if stripped.startswith("}"):
                    inside_location = False

                    # Injecter le bloc correct ici
                    if enable_cache:
                        new_lines += [
                            f"        proxy_cache {domain}_cache;\n",
                            f"        proxy_cache_valid 200 30d;\n",
                            f"        proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;\n",
                            f"        proxy_cache_background_update on;\n",
                            f"        proxy_ignore_headers Set-Cookie Cache-Control;\n",
                            f"        add_header X-Cache $upstream_cache_status always;\n"
                        ]
                    else:
                        comment = " - Site EOL" if eol else ""
                        new_lines += [
                            f"        proxy_cache off;\n",
                            f"        add_header X-Cache \"BYPASS{comment}\" always;\n"
                        ]

            new_lines.append(line)

        with open(conf_path, "w") as f:
            f.writelines(new_lines)

        subprocess.run(["nginx", "-t"], check=True)
        subprocess.run(["systemctl", "reload", "nginx"], check=True)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur mise à jour des directives cache : {str(e)}")


@app.post("/cache/{domain}/disable", dependencies=[Depends(verify_api_key), Depends(verify_ip)])
def disable_cache(domain: str, req: CacheToggleRequest):
    update_nginx_cache_directives(domain, enable_cache=False, eol=req.eol)
    return {
        "status": "cache disabled",
        "domain": domain,
        "eol": req.eol
    }


@app.post("/cache/{domain}/enable", dependencies=[Depends(verify_api_key), Depends(verify_ip)])
def enable_cache(domain: str):
    update_nginx_cache_directives(domain, enable_cache=True)
    return {
        "status": "cache enabled",
        "domain": domain
    }



@app.get("/cache/{domain}", dependencies=[Depends(verify_api_key), Depends(verify_ip)])
def read_cache(domain: str):
    cache_dir = os.path.join(CACHE_BASE, domain)
    if not os.path.isdir(cache_dir):
        raise HTTPException(status_code=404, detail="Répertoire de cache introuvable")

    try:
        cache_contents = []
        for root, dirs, files in os.walk(cache_dir):
            for name in files:
                full_path = os.path.join(root, name)
                relative_path = os.path.relpath(full_path, cache_dir)
                size = os.path.getsize(full_path)
                cache_contents.append({
                    "file": relative_path,
                    "size_bytes": size
                })

        return {
            "domain": domain,
            "file_count": len(cache_contents),
            "files": cache_contents
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lecture cache : {str(e)}")

@app.post("/cache/{domain}/clear", dependencies=[Depends(verify_api_key), Depends(verify_ip)])
def clear_cache(domain: str):
    cache_dir = os.path.join(CACHE_BASE, domain)
    if not os.path.isdir(cache_dir):
        raise HTTPException(status_code=404, detail="Répertoire de cache introuvable")

    try:
        deleted_files = 0
        for root, dirs, files in os.walk(cache_dir):
            for name in files:
                file_path = os.path.join(root, name)
                os.remove(file_path)
                deleted_files += 1
            for name in dirs:
                shutil.rmtree(os.path.join(root, name), ignore_errors=True)


        return {
            "status": "cache cleared",
            "domain": domain,
            "deleted_files": deleted_files
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur suppression cache : {str(e)}")


@app.post("/nginx/reload", dependencies=[Depends(verify_api_key), Depends(verify_ip)])
def reload_nginx():
    try:
        test_result = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
        if test_result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Erreur dans la configuration Nginx :\n{test_result.stderr}"
            )

        reload_result = subprocess.run(["systemctl", "reload", "nginx"], capture_output=True, text=True)
        if reload_result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Échec du rechargement Nginx :\n{reload_result.stderr}"
            )

        return {
            "status": "nginx reloaded",
            "test_output": test_result.stdout.strip(),
            "reload_output": reload_result.stdout.strip()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur système : {str(e)}")

@app.get("/origin/{domain}", dependencies=[Depends(verify_api_key), Depends(verify_ip)])
def get_origin(domain: str):
    proxy_lines = get_proxy_pass_config(domain)
    return {
        "domain": domain,
        "proxy_pass": proxy_lines
    }

@app.post("/origin/{domain}/update", dependencies=[Depends(verify_api_key), Depends(verify_ip)])
def update_origin(domain: str, req: UpdateOriginRequest):
    update_nginx_proxy_pass(domain, req.origin_ip, req.origin_port, req.origin_proto)
    return {
        "status": "proxy_pass updated",
        "domain": domain,
        "new_origin": f"{req.origin_proto}://{req.origin_ip}:{req.origin_port}"
    }



@app.get("/list", dependencies=[Depends(verify_api_key), Depends(verify_ip)])
def list_cdn_nodes():
    try:
        files = os.listdir(NGINX_SITES_AVAILABLE)
        domains = [f for f in files if os.path.isfile(os.path.join(NGINX_SITES_AVAILABLE, f))]
        return {"sites": domains}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/delete/{domain}", dependencies=[Depends(verify_api_key), Depends(verify_ip)])
def delete_cdn_node(domain: str):
    try:
        available_path = os.path.join(NGINX_SITES_AVAILABLE, domain)
        enabled_path = os.path.join(NGINX_SITES_ENABLED, domain)
        cache_dir = os.path.join(CACHE_BASE, domain)
        ssl_path = f"/etc/letsencrypt/live/{domain}"
        ssl_archive = f"/etc/letsencrypt/archive/{domain}"
        ssl_renewal = f"/etc/letsencrypt/renewal/{domain}.conf"

        for path in [enabled_path, available_path]:
            if os.path.islink(path) or os.path.isfile(path):
                os.remove(path)

        if os.path.isdir(cache_dir):
            shutil.rmtree(cache_dir)
        if os.path.isdir(ssl_path):
            shutil.rmtree(ssl_path)
        if os.path.isdir(ssl_archive):
            shutil.rmtree(ssl_archive)
        if os.path.isfile(ssl_renewal):
            os.remove(ssl_renewal)

        subprocess.run(["nginx", "-t"])
        subprocess.run(["systemctl", "reload", "nginx"])

        return {"status": "deleted", "domain": domain}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur suppression : {str(e)}")

@app.post("/deploy", dependencies=[Depends(verify_api_key), Depends(verify_ip)])
def deploy_cdn_node(req: DeployRequest):
    if not req.domains or not req.origin_ip:
        raise HTTPException(status_code=400, detail="Domain list and origin IP are required")

    primary_domain = req.domains[0]
    domain_str = " ".join(req.domains)
    certbot_args = " ".join([f"-d {d}" for d in req.domains])

    cache_dir = os.path.join(CACHE_BASE, primary_domain)
    os.makedirs(cache_dir, exist_ok=True)
    subprocess.run(["chown", "www-data:www-data", cache_dir])

    if req.dns_provider == "cloudflare":
        credentials_file = CLOUDFLARE_INI
        dns_plugin = "--dns-cloudflare"
        plugin_args = f"--dns-cloudflare-credentials {credentials_file}"
    elif req.dns_provider == "aws":
        credentials_file = AWS_INI
        dns_plugin = "--dns-route53"
        plugin_args = ""
    else:
        raise HTTPException(status_code=400, detail="Fournisseur DNS non supporté")

    if not os.path.isfile(credentials_file) and req.dns_provider != "aws":
        raise HTTPException(status_code=500, detail=f"Fichier credentials manquant : {credentials_file}")

    certbot_cmd = f"certbot certonly {dns_plugin} {plugin_args} {certbot_args} " \
                  f"--agree-tos --no-eff-email --email {CERTBOT_EMAIL} --dns-cloudflare-propagation-seconds 30 --non-interactive"

    result = subprocess.run(certbot_cmd, shell=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="Échec de Certbot")

    cert_path = f"/etc/letsencrypt/live/{primary_domain}/fullchain.pem"
    if not os.path.isfile(cert_path):
        raise HTTPException(status_code=500, detail="Certificat SSL introuvable")

    nginx_conf = os.path.join(NGINX_SITES_AVAILABLE, primary_domain)
    nginx_enabled = os.path.join(NGINX_SITES_ENABLED, primary_domain)

    with open(nginx_conf, "w") as f:
        f.write(f"""
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
        proxy_pass {req.origin_proto}://{req.origin_ip}:{req.origin_port};
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
""")

    subprocess.run(["ln", "-sf", nginx_conf, nginx_enabled])
    nginx_result = subprocess.run(["nginx", "-t"])
    if nginx_result.returncode != 0:
        raise HTTPException(status_code=500, detail="Nginx config test failed")

    subprocess.run(["systemctl", "reload", "nginx"])

    return {
        "status": "success",
        "domains": req.domains,
        "origin": f"{req.origin_proto}://{req.origin_ip}:{req.origin_port}",
        "dns_provider": req.dns_provider,
        "cache_dir": cache_dir
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8443,
        ssl_keyfile="/srv/api/certs/key.pem",
        ssl_certfile="/srv/api/certs/cert.pem")

#if __name__ == "__main__":
#    uvicorn.run("main:app", host="0.0.0.0", port=8443, ssl_keyfile="./certs/key.pem", ssl_certfile="./certs/cert.pem")
