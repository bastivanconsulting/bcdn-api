# Bastivan CDN API

Cette API REST permet de déployer et de gérer des noeuds CDN basés sur Nginx.

## Prérequis

- **Python 3.10+** avec les dépendances listées dans `requirements.txt`.
- **Nginx** installé et fonctionnel (accès aux répertoires `sites-available` et `sites-enabled`).
- **Certbot** avec le plugin DNS correspondant (Cloudflare ou Route53).

## Configuration

Modifiez les constantes situées en début de `server.py` pour adapter l'environnement :

- `CERTBOT_EMAIL` : adresse e‑mail utilisée par Certbot.
- `CLOUDFLARE_INI` ou `AWS_INI` : chemins vers les fichiers de credentials pour les plugins Certbot.
- `NGINX_SITES_AVAILABLE` et `NGINX_SITES_ENABLED` : dossiers de configuration Nginx.
- `CACHE_BASE` : répertoire où seront stockés les caches.
- `API_KEY` : clé secrète à fournir dans l'en-tête `X-API-Key`.
- `ALLOWED_IPS` : adresses autorisées à appeler l'API.

Exemple :

```python
CERTBOT_EMAIL = "admin@example.com"
API_KEY = "votre-cle-api"
ALLOWED_IPS = ["203.0.113.42"]
```

## Lancement

Installez les dépendances :

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Exécution directe :

```bash
python server.py
```

Ou via Uvicorn :

```bash
uvicorn server:app --host 0.0.0.0 --port 8443 \
    --ssl-keyfile /srv/api/certs/privkey.pem \
    --ssl-certfile /srv/api/certs/fullchain.pem
```

## Appels d'exemple

Tous les appels doivent inclure l'en-tête `X-API-Key` et provenir d'une IP autorisée.

### Déploiement d'un site

```bash
curl -X POST https://cdn.example.com:8443/deploy \
    -H "X-API-Key: votre-cle-api" \
    -H "Content-Type: application/json" \
    -d '{
        "domains": ["example.com", "www.example.com"],
        "origin_ip": "203.0.113.10",
        "origin_port": 443,
        "origin_proto": "https",
        "dns_provider": "cloudflare"
    }'
```

### Mise à jour de l'origine

```bash
curl -X POST https://cdn.example.com:8443/origin/example.com/update \
    -H "X-API-Key: votre-cle-api" \
    -H "Content-Type: application/json" \
    -d '{"origin_ip": "203.0.113.11", "origin_port": 443, "origin_proto": "https"}'
```

### Activation du cache

```bash
curl -X POST https://cdn.example.com:8443/cache/example.com/enable \
    -H "X-API-Key: votre-cle-api"
```

### Désactivation du cache

```bash
curl -X POST https://cdn.example.com:8443/cache/example.com/disable \
    -H "X-API-Key: votre-cle-api" \
    -H "Content-Type: application/json" \
    -d '{"eol": false}'
```

### Nettoyage du cache

```bash
curl -X POST https://cdn.example.com:8443/cache/example.com/clear \
    -H "X-API-Key: votre-cle-api"
```

### Rechargement de Nginx

```bash
curl -X POST https://cdn.example.com:8443/nginx/reload \
    -H "X-API-Key: votre-cle-api"
```

## Précautions de sécurité

- Conservez la clé API secrète et limitez les IPs autorisées.
- Exécutez l'API avec un certificat TLS valide (voir paramètres `ssl_keyfile` et `ssl_certfile`).
- Restreignez les droits du processus : idéalement, utilisez un utilisateur dédié et un pare-feu pour bloquer l'accès non désiré.

