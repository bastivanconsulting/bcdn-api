import unittest
from unittest.mock import MagicMock
from app.services.business import NodeService
from app.models.domain import DeployRequest

class TestNodeService(unittest.TestCase):
    def setUp(self):
        self.nginx = MagicMock()
        self.certbot = MagicMock()
        self.fs = MagicMock()
        self.service = NodeService(self.nginx, self.certbot, self.fs)

    def test_deploy_node(self):
        req = DeployRequest(
            domains=["example.com"],
            origin_ip="1.2.3.4",
            dns_provider="cloudflare"
        )

        self.service.deploy_node(req)

        # Verify interactions
        self.fs.create_dir.assert_called_once()
        self.certbot.generate_cert.assert_called_once_with(["example.com"], "cloudflare")
        self.nginx.create_site_config.assert_called_once()

    def test_delete_node(self):
        self.service.delete_node("example.com")

        self.nginx.delete_site_config.assert_called_once_with("example.com")
        self.fs.remove_dir.assert_called_once()
        self.certbot.delete_cert.assert_called_once_with("example.com")

if __name__ == "__main__":
    unittest.main()
