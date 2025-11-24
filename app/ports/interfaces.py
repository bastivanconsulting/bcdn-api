from abc import ABC, abstractmethod
from typing import List, Optional

class NginxPort(ABC):
    @abstractmethod
    def reload(self) -> None:
        pass

    @abstractmethod
    def test_config(self) -> None:
        pass

    @abstractmethod
    def get_proxy_pass_lines(self, domain: str) -> List[str]:
        pass

    @abstractmethod
    def update_proxy_pass(self, domain: str, origin_proto: str, origin_ip: str, origin_port: int) -> None:
        pass

    @abstractmethod
    def update_cache_directives(self, domain: str, enable_cache: bool, eol: bool = False) -> None:
        pass

    @abstractmethod
    def create_site_config(self, domain: str, content: str) -> None:
        pass

    @abstractmethod
    def delete_site_config(self, domain: str) -> None:
        pass

    @abstractmethod
    def list_sites(self) -> List[str]:
        pass

class CertbotPort(ABC):
    @abstractmethod
    def generate_cert(self, domains: List[str], dns_provider: str) -> None:
        pass

    @abstractmethod
    def delete_cert(self, domain: str) -> None:
        pass

class FileSystemPort(ABC):
    @abstractmethod
    def create_dir(self, path: str, owner: str = None) -> None:
        pass

    @abstractmethod
    def remove_dir(self, path: str) -> None:
        pass

    @abstractmethod
    def list_files_recursive(self, path: str) -> List[tuple[str, int]]:
        pass

    @abstractmethod
    def clear_dir(self, path: str) -> int:
        pass
