# Bastivan CDN Node API

Cette API REST permet de déployer et de gérer des nœuds CDN basés sur Nginx. Elle suit une architecture propre ("Clean Architecture" / "ISA") pour une meilleure maintenabilité et modularité.

## Prérequis

- **Python 3.10+**
- **Nginx** installé et fonctionnel (accès aux répertoires `sites-available` et `sites-enabled`).
- **Certbot** avec le plugin DNS correspondant (Cloudflare ou Route53).
- **Droits root** (pour interagir avec Nginx, Certbot et le système de fichiers).

## Installation

1. Clonez ce dépôt.
2. Créez un environnement virtuel et installez les dépendances :

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

La configuration se fait via des **variables d'environnement**. Vous pouvez créer un fichier `.env` à la racine du projet pour surcharger les valeurs par défaut.

| Variable | Description | Valeur par défaut |
|---|---|---|
| `API_KEY` | Clé secrète pour authentifier les requêtes (Header `X-API-Key`) | `changeme` |
| `ALLOWED_IPS` | Liste des IPs autorisées (séparées par des virgules) | `127.0.0.1,116.203.239.241` |
| `SSL_KEYFILE` | Chemin vers la clé privée SSL pour l'API | `/srv/api/certs/privkey.pem` |
| `SSL_CERTFILE` | Chemin vers le certificat SSL pour l'API | `/srv/api/certs/fullchain.pem` |
| `CERTBOT_EMAIL` | Email utilisé pour l'enregistrement Certbot | `contact@bastivan.com` |
| `CLOUDFLARE_INI` | Chemin vers les credentials Cloudflare | `/root/.secrets/certbot/cloudflare.ini` |
| `AWS_INI` | Chemin vers les credentials AWS Route53 | `/root/.secrets/certbot/aws.ini` |

**Exemple de fichier `.env` :**

```env
API_KEY=ma-super-cle-secrete-production
ALLOWED_IPS=127.0.0.1,203.0.113.42
CERTBOT_EMAIL=admin@example.com
```

## Lancement

### Développement / Test (sans SSL par défaut si fichiers absents)

```bash
python -m app.main
```

Le serveur écoutera sur le port **8443**. Si les fichiers SSL configurés sont présents, il utilisera HTTPS. Sinon, il démarrera en HTTP.

### Production

Il est recommandé d'utiliser un gestionnaire de processus (systemd, supervisord).

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8443 --ssl-keyfile /srv/api/certs/privkey.pem --ssl-certfile /srv/api/certs/fullchain.pem
```

## Documentation de l'API

L'API a été refondue pour suivre les standards REST.

> **Authentification** : Toutes les requêtes doivent inclure l'en-tête `X-API-Key`.

### 1. Gestion des Nœuds (Sites)

#### Lister les nœuds
```bash
curl -X GET https://cdn.example.com:8443/nodes \
    -H "X-API-Key: votre-cle"
```

#### Déployer un nouveau nœud
```bash
curl -X POST https://cdn.example.com:8443/nodes \
    -H "X-API-Key: votre-cle" \
    -H "Content-Type: application/json" \
    -d '{
        "domains": ["example.com", "www.example.com"],
        "origin_ip": "203.0.113.10",
        "origin_port": 443,
        "origin_proto": "https",
        "dns_provider": "cloudflare"
    }'
```

#### Supprimer un nœud
```bash
curl -X DELETE https://cdn.example.com:8443/nodes/example.com \
    -H "X-API-Key: votre-cle"
```

### 2. Gestion de l'Origine

#### Voir l'origine actuelle
```bash
curl -X GET https://cdn.example.com:8443/nodes/example.com/origin \
    -H "X-API-Key: votre-cle"
```

#### Mettre à jour l'origine
```bash
curl -X PUT https://cdn.example.com:8443/nodes/example.com/origin \
    -H "X-API-Key: votre-cle" \
    -H "Content-Type: application/json" \
    -d '{
        "origin_ip": "203.0.113.11",
        "origin_port": 443,
        "origin_proto": "https"
    }'
```

### 3. Gestion du Cache

#### Activer le cache
```bash
curl -X POST https://cdn.example.com:8443/nodes/example.com/cache/enable \
    -H "X-API-Key: votre-cle"
```

#### Désactiver le cache
```bash
curl -X POST https://cdn.example.com:8443/nodes/example.com/cache/disable \
    -H "X-API-Key: votre-cle" \
    -H "Content-Type: application/json" \
    -d '{"eol": false}'
```

#### Vider le cache
```bash
curl -X DELETE https://cdn.example.com:8443/nodes/example.com/cache \
    -H "X-API-Key: votre-cle"
```

#### Informations sur le cache
```bash
curl -X GET https://cdn.example.com:8443/nodes/example.com/cache \
    -H "X-API-Key: votre-cle"
```

### 4. Système

#### Recharger Nginx
```bash
curl -X POST https://cdn.example.com:8443/system/nginx/reload \
    -H "X-API-Key: votre-cle"
```

## Architecture

Le projet suit une architecture hexagonale (Ports & Adapters) :

- **`app/api`** : Points d'entrée REST.
- **`app/services`** : Logique métier (Orchestration Nginx/Certbot).
- **`app/ports`** : Interfaces abstraites (ISA) définissant les contrats.
- **`app/adapters`** : Implémentations concrètes (Shell, FileSystem).
- **`app/models`** : Objets de domaine (Pydantic).
- **`app/core`** : Configuration.

Pour lancer les tests unitaires :
```bash
python -m unittest discover tests
```
