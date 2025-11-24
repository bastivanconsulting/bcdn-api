from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import APIKeyHeader
from app.core.config import settings
from app.services.business import NodeService, CacheService, SystemService
from app.adapters.impl import ShellNginxAdapter, ShellCertbotAdapter, LocalFileSystemAdapter
from app.models.domain import DeployRequest, UpdateOriginRequest, CacheToggleRequest

# Dependency Injection Setup
def get_node_service():
    return NodeService(ShellNginxAdapter(), ShellCertbotAdapter(), LocalFileSystemAdapter())

def get_cache_service():
    return CacheService(ShellNginxAdapter(), LocalFileSystemAdapter())

def get_system_service():
    return SystemService(ShellNginxAdapter())

# Auth
api_key_header = APIKeyHeader(name="X-API-Key")

def verify_auth(request: Request, api_key: str = Depends(api_key_header)):
    if api_key != settings.API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")

    client_ip = request.client.host
    if client_ip not in settings.ALLOWED_IPS:
        raise HTTPException(status_code=403, detail=f"Unauthorized IP: {client_ip}")

router = APIRouter(dependencies=[Depends(verify_auth)])

# --- Nodes ---
@router.get("/nodes", tags=["Nodes"])
def list_nodes(service: NodeService = Depends(get_node_service)):
    return {"sites": service.get_nodes()}

@router.post("/nodes", tags=["Nodes"])
def deploy_node(req: DeployRequest, service: NodeService = Depends(get_node_service)):
    try:
        return service.deploy_node(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/nodes/{domain}", tags=["Nodes"])
def delete_node(domain: str, service: NodeService = Depends(get_node_service)):
    try:
        service.delete_node(domain)
        return {"status": "deleted", "domain": domain}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/nodes/{domain}/origin", tags=["Nodes"])
def get_origin(domain: str, service: NodeService = Depends(get_node_service)):
    try:
        lines = service.get_origin(domain)
        return {"domain": domain, "proxy_pass": lines}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.put("/nodes/{domain}/origin", tags=["Nodes"])
def update_origin(domain: str, req: UpdateOriginRequest, service: NodeService = Depends(get_node_service)):
    try:
        service.update_origin(domain, req.origin_ip, req.origin_port, req.origin_proto)
        return {
            "status": "proxy_pass updated",
            "domain": domain,
            "new_origin": f"{req.origin_proto}://{req.origin_ip}:{req.origin_port}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Cache ---
@router.get("/nodes/{domain}/cache", tags=["Cache"])
def get_cache_info(domain: str, service: CacheService = Depends(get_cache_service)):
    try:
        return service.get_cache_info(domain)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.delete("/nodes/{domain}/cache", tags=["Cache"])
def clear_cache(domain: str, service: CacheService = Depends(get_cache_service)):
    try:
        count = service.clear_cache(domain)
        return {"status": "cache cleared", "domain": domain, "deleted_files": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/nodes/{domain}/cache/enable", tags=["Cache"])
def enable_cache(domain: str, service: CacheService = Depends(get_cache_service)):
    try:
        service.enable_cache(domain)
        return {"status": "cache enabled", "domain": domain}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/nodes/{domain}/cache/disable", tags=["Cache"])
def disable_cache(domain: str, req: CacheToggleRequest, service: CacheService = Depends(get_cache_service)):
    try:
        service.disable_cache(domain, req.eol)
        return {"status": "cache disabled", "domain": domain, "eol": req.eol}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- System ---
@router.post("/system/nginx/reload", tags=["System"])
def reload_nginx(service: SystemService = Depends(get_system_service)):
    try:
        service.reload_nginx()
        return {"status": "nginx reloaded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
