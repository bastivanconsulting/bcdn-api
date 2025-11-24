import os
import subprocess
import shutil
from typing import List
from app.ports.interfaces import NginxPort, FileSystemPort, CertbotPort
from app.core.config import settings

class ShellNginxAdapter(NginxPort):
    def reload(self) -> None:
        subprocess.run(["systemctl", "reload", "nginx"], check=True)

    def test_config(self) -> None:
        result = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Nginx config test failed: {result.stderr}")

    def get_proxy_pass_lines(self, domain: str) -> List[str]:
        conf_path = os.path.join(settings.NGINX_SITES_AVAILABLE, domain)
        if not os.path.isfile(conf_path):
            raise FileNotFoundError("Configuration file not found")

        proxy_lines = []
        with open(conf_path, "r") as f:
            for line in f:
                if "proxy_pass" in line:
                    proxy_lines.append(line.strip())
        return proxy_lines

    def update_proxy_pass(self, domain: str, origin_proto: str, origin_ip: str, origin_port: int) -> None:
        conf_path = os.path.join(settings.NGINX_SITES_AVAILABLE, domain)
        if not os.path.isfile(conf_path):
            raise FileNotFoundError("Configuration file not found")

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

        self.test_config()
        self.reload()

    def update_cache_directives(self, domain: str, enable_cache: bool, eol: bool = False) -> None:
        conf_path = os.path.join(settings.NGINX_SITES_AVAILABLE, domain)
        if not os.path.isfile(conf_path):
            raise FileNotFoundError("Configuration file not found")

        with open(conf_path, "r") as f:
            lines = f.readlines()

        new_lines = []
        inside_location = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("location /"):
                inside_location = True

            if inside_location:
                if any(stripped.startswith(key) for key in [
                    "proxy_cache", "proxy_cache_valid", "proxy_cache_use_stale",
                    "proxy_cache_background_update", "proxy_ignore_headers", "add_header X-Cache"
                ]):
                    continue

                if stripped.startswith("}"):
                    inside_location = False
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

        self.test_config()
        self.reload()

    def create_site_config(self, domain: str, content: str) -> None:
        available_path = os.path.join(settings.NGINX_SITES_AVAILABLE, domain)
        enabled_path = os.path.join(settings.NGINX_SITES_ENABLED, domain)

        with open(available_path, "w") as f:
            f.write(content)

        # Link
        subprocess.run(["ln", "-sf", available_path, enabled_path], check=True)
        self.test_config()
        self.reload()

    def delete_site_config(self, domain: str) -> None:
        available_path = os.path.join(settings.NGINX_SITES_AVAILABLE, domain)
        enabled_path = os.path.join(settings.NGINX_SITES_ENABLED, domain)

        if os.path.exists(enabled_path):
            os.remove(enabled_path)
        if os.path.exists(available_path):
            os.remove(available_path)

        self.test_config()
        self.reload()

    def list_sites(self) -> List[str]:
        if not os.path.exists(settings.NGINX_SITES_AVAILABLE):
            return []
        files = os.listdir(settings.NGINX_SITES_AVAILABLE)
        return [f for f in files if os.path.isfile(os.path.join(settings.NGINX_SITES_AVAILABLE, f))]


class ShellCertbotAdapter(CertbotPort):
    def generate_cert(self, domains: List[str], dns_provider: str) -> None:
        domain_args = " ".join([f"-d {d}" for d in domains])

        if dns_provider == "cloudflare":
            credentials_file = settings.CLOUDFLARE_INI
            dns_plugin = "--dns-cloudflare"
            plugin_args = f"--dns-cloudflare-credentials {credentials_file}"
            propagation_arg = "--dns-cloudflare-propagation-seconds 30"
        elif dns_provider == "aws":
            credentials_file = settings.AWS_INI
            dns_plugin = "--dns-route53"
            plugin_args = ""
            propagation_arg = "--dns-route53-propagation-seconds 30"
        else:
            raise ValueError("Unsupported DNS provider")

        if dns_provider != "aws" and not os.path.isfile(credentials_file):
            raise FileNotFoundError(f"Credentials file missing: {credentials_file}")

        cmd = (
            f"certbot certonly {dns_plugin} {plugin_args} {domain_args} "
            f"--agree-tos --no-eff-email --email {settings.CERTBOT_EMAIL} {propagation_arg} --non-interactive"
        )

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Certbot failed: {result.stderr}")

    def delete_cert(self, domain: str) -> None:
        ssl_path = f"/etc/letsencrypt/live/{domain}"
        ssl_archive = f"/etc/letsencrypt/archive/{domain}"
        ssl_renewal = f"/etc/letsencrypt/renewal/{domain}.conf"

        if os.path.isdir(ssl_path):
            shutil.rmtree(ssl_path)
        if os.path.isdir(ssl_archive):
            shutil.rmtree(ssl_archive)
        if os.path.isfile(ssl_renewal):
            os.remove(ssl_renewal)


class LocalFileSystemAdapter(FileSystemPort):
    def create_dir(self, path: str, owner: str = None) -> None:
        os.makedirs(path, exist_ok=True)
        if owner:
            # Assuming 'owner' is in format 'user:group' or just 'user'
            # shutil.chown is safer than subprocess
            user, group = owner.split(":") if ":" in owner else (owner, owner)
            shutil.chown(path, user=user, group=group)

    def remove_dir(self, path: str) -> None:
        if os.path.isdir(path):
            shutil.rmtree(path)

    def list_files_recursive(self, path: str) -> List[tuple[str, int]]:
        files_list = []
        if not os.path.isdir(path):
            return files_list

        for root, dirs, files in os.walk(path):
            for name in files:
                full_path = os.path.join(root, name)
                relative_path = os.path.relpath(full_path, path)
                size = os.path.getsize(full_path)
                files_list.append((relative_path, size))
        return files_list

    def clear_dir(self, path: str) -> int:
        if not os.path.isdir(path):
            return 0

        deleted_count = 0
        for root, dirs, files in os.walk(path):
            for name in files:
                os.remove(os.path.join(root, name))
                deleted_count += 1
            for name in dirs:
                shutil.rmtree(os.path.join(root, name), ignore_errors=True)
        return deleted_count
