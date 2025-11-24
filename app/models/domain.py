from pydantic import BaseModel
from typing import List, Literal, Optional

class CacheToggleRequest(BaseModel):
    eol: bool = False

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

class CacheFile(BaseModel):
    file: str
    size_bytes: int

class CacheInfo(BaseModel):
    domain: str
    file_count: int
    files: List[CacheFile]

class OperationResult(BaseModel):
    status: str
    domain: Optional[str] = None
    details: Optional[dict] = None
