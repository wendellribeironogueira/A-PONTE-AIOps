import os
import shutil
import subprocess  # nosec B404 - Used for safe, reviewed fallbacks and CLI interactions.

from core.lib import utils as common

try:
    import docker  # pyright: ignore [reportMissingModuleSource]
except ImportError:
    docker = None


class ContainerManager:
    """
    Gerencia a interação com containers Docker para execução de ferramentas MCP.
    Prioriza o uso do Docker SDK para verificações de estado e metadados.
    """

    def __init__(self, container_name="mcp-terraform"):
        self.container_name = container_name
        self.client = None
        self._has_sdk = False

        if docker:
            try:
                self.client = docker.from_env()
                self._has_sdk = True
            except Exception as e:
                # Falha silenciosa se o daemon não estiver acessível (fallback para CLI)
                common.log_warning(
                    f"Docker SDK não inicializado ({e}). Usando fallback para CLI."
                )

    def is_available(self):
        """Verifica se o container está rodando e saudável usando SDK."""
        if self._has_sdk and self.client:
            try:
                c = self.client.containers.get(self.container_name)
                return c.status == "running"
            except Exception:
                return False

        # Fallback para CLI se SDK falhar ou não existir
        try:
            docker_path = shutil.which("docker")
            if not docker_path:
                return False
            res = subprocess.run(
                [
                    docker_path,
                    "inspect",
                    "-f",
                    "{{.State.Running}}",
                    self.container_name,
                ],  # nosec B603
                capture_output=True,
                text=True,
            )
            return res.stdout.strip() == "true"
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def get_execution_command(self, script_path):
        """
        Constrói o comando de execução (docker exec) com injeção de variáveis de ambiente.
        Retorna uma lista pronta para subprocess/MCPClient.
        """
        cmd = ["docker", "exec", "-i"]

        # Injeção de Credenciais e Contexto (Pass-through)
        # Lista explícita para evitar vazamento de env vars não relacionadas
        env_vars = [
            "AWS_PROFILE",
            "AWS_REGION",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "TF_VAR_account_id",
            "TF_VAR_security_email",
            "GITHUB_TOKEN",
            "GH_TOKEN",
        ]

        for var in env_vars:
            val = os.environ.get(var)
            if val:
                # Normaliza GITHUB_TOKEN se vier de GH_TOKEN
                target_var = "GITHUB_TOKEN" if var == "GH_TOKEN" else var
                cmd.extend(["-e", f"{target_var}={val}"])

        # Fallback para token do GitHub via CLI se não estiver no env
        if "GITHUB_TOKEN" not in os.environ and "GH_TOKEN" not in os.environ:
            gh_path = shutil.which("gh")
            if gh_path:
                try:
                    token = subprocess.check_output(
                        [gh_path, "auth", "token"], text=True
                    ).strip()  # nosec B603
                    if token:
                        cmd.extend(["-e", f"GITHUB_TOKEN={token}"])
                except (subprocess.SubprocessError, FileNotFoundError) as e:
                    common.log_warning(f"Falha ao obter token do GitHub via CLI: {e}")

        # A lógica de execução, busca de path e diagnóstico foi movida para o entrypoint.sh
        # dentro do container para maior robustez e manutenibilidade.
        cmd.extend([self.container_name, script_path])
        return cmd
