#!/usr/bin/env python3
import sys
from pathlib import Path

# Adiciona raiz do projeto ao path para importar módulos core
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # nosec B404 - Used to delegate to security scanning tools  # noqa: E402
import tempfile  # noqa: E402
from typing import Any, List  # noqa: E402

from core.domain.security import SecurityFinding, Severity, ToolType  # noqa: E402
from core.lib import utils as common  # noqa: E402


class SecurityIngestor:
    """
    Orquestrador de Segurança A-PONTE.
    Executa ferramentas nativas (CLI) e normaliza outputs para o padrão da plataforma.
    """

    def __init__(self, project_name: str):
        self.project_name = project_name

    def _generate_id(self, tool: str, check_id: str, resource: str, region: str = "global") -> str:
        """Gera um ID determinístico para deduplicação."""
        # Inclui região para evitar colisão de recursos com mesmo ID em regiões diferentes (ex: SG default)
        raw = f"{self.project_name}|{tool}|{check_id}|{resource}|{region}"
        return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()

    def _map_severity(self, raw: Any) -> Severity:
        """Normaliza severidade para o Enum do A-PONTE."""
        if not raw:
            return Severity.UNKNOWN

        raw = str(raw).upper()
        mapping = {
            "CRITICAL": Severity.CRITICAL,
            "HIGH": Severity.HIGH,
            "MEDIUM": Severity.MEDIUM,
            "LOW": Severity.LOW,
            "INFO": Severity.INFO,
        }
        return mapping.get(raw, Severity.UNKNOWN)

    def _detect_aws_context(self) -> tuple[str, str]:
        """Usa Boto3 para detectar Região e Account ID automaticamente."""
        region = "sa-east-1"  # Default seguro
        account = "unknown"

        try:
            import boto3  # pyright: ignore [reportMissingImports]

            session = boto3.session.Session()
            region = session.region_name or os.getenv("AWS_REGION", region)
            account = session.client("sts").get_caller_identity()["Account"]
        except (ImportError, Exception) as e:
            # Warn user about fallback, helpful for debugging credential issues
            print(f"⚠️  Falha na detecção de contexto AWS: {e}. Usando defaults ({region}/{account}).")
        return region, account

    def run_checkov(self, target_dir: str = ".") -> List[SecurityFinding]:
        """Executa Checkov (IaC) e normaliza."""
        findings = []
        try:
            # --quiet para reduzir ruído, -o json para parsing
            # CONFIGURAÇÃO: Usa .checkov.yml na raiz para exclusões e regras
            checkov_path = shutil.which("checkov")
            if not checkov_path:
                print("❌ Checkov não encontrado no PATH. Pulando.")
                return []
            cmd = [checkov_path, "-d", target_dir]

            # FIX: Força output JSON para garantir parsing, independente do .checkov.yml
            if "-o" not in cmd and "--output" not in cmd:
                cmd.extend(["-o", "json"])

            if not Path(".checkov.yml").exists():
                # Fallback seguro apenas se o arquivo não existir (evita quebrar em ambientes novos)
                cmd.extend(
                    [
                        "--quiet",
                        "--compact",
                        "--skip-path",
                        "venv",
                        "--skip-path",
                        ".git",
                        "--skip-path",
                        ".terragrunt-cache",
                    ]
                )

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=900
            )  # nosec B603

            try:
                data = json.loads(result.stdout)
                # Checkov retorna lista se houver múltiplos frameworks, ou dict se um só
                if isinstance(data, dict):
                    data = [data]

                for framework in data:
                    results = framework.get("results", {}).get("failed_checks") or []
                    for check in results:
                        finding = SecurityFinding(
                            id=self._generate_id(
                                ToolType.CHECKOV, check["check_id"], check["resource"]
                            ),
                            project_name=self.project_name,
                            tool=ToolType.CHECKOV,
                            check_id=check["check_id"],
                            severity=self._map_severity(
                                check.get("severity", "UNKNOWN")
                            ),
                            title=check["check_name"],
                            description=check.get("guideline", "")
                            or check["check_name"],
                            resource_id=check["resource"],
                            line=(
                                check["file_line_range"][0]
                                if check.get("file_line_range")
                                else 0
                            ),
                            references=[check.get("guideline", "")],
                        )
                        findings.append(finding)
            except json.JSONDecodeError as e:
                print(f"⚠️  [Checkov] Falha ao decodificar saída JSON: {e}")
        except subprocess.TimeoutExpired:
            print("❌ Checkov excedeu o tempo limite (15min).")
            return [
                SecurityFinding(
                    id="checkov-timeout",
                    project_name=self.project_name,
                    tool=ToolType.CHECKOV,
                    check_id="TIMEOUT",
                    severity=Severity.HIGH,
                    title="Checkov Scan Timed Out",
                    description="A varredura de segurança excedeu o limite de 15 minutos.",
                    resource_id="FileSystem",
                    references=[],
                )
            ]
        except Exception as e:
            print(f"❌ Erro ao rodar Checkov: {e}")
        return findings

    def run_bandit(self, target_dir: str = ".") -> List[SecurityFinding]:
        """Executa Bandit (Python SAST) e normaliza."""
        findings = []
        try:
            # FIX: Usa arquivo temporário para separar JSON do log de progresso (stdout)
            # Isso permite usar -v para mostrar ao usuário o que está sendo analisado
            # Windows Fix: delete=False e close() antes de passar para subprocesso
            tmp = tempfile.NamedTemporaryFile(suffix=".json", mode="w+", delete=False)
            tmp.close()
            try:
                # CONFIGURAÇÃO: Usa .bandit na raiz
                bandit_path = shutil.which("bandit")
                if not bandit_path:
                    print("❌ Bandit não encontrado no PATH. Pulando.")
                    return []
                cmd = [
                    bandit_path,
                    "-r",
                    target_dir,
                    "-f",
                    "json",
                    "-o",
                    tmp.name,
                    "-v",
                ]

                if Path(".bandit").exists():
                    cmd.extend(["-c", ".bandit"])
                else:
                    # Fallback mínimo
                    cmd.extend(["-x", "venv,.git,.terragrunt-cache"])

                process = subprocess.Popen(  # nosec B603
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                )

                # Stream de progresso para o usuário não achar que travou
                if process.stdout:
                    for line in process.stdout:
                        line = line.strip()
                        if "checking" in line.lower():
                            # Limita tamanho da linha para não quebrar terminal
                            msg = f"   [Bandit] {line}"
                            if len(msg) > 90:
                                msg = msg[:87] + "..."
                            sys.stdout.write(f"\r{msg:<90}")
                            sys.stdout.flush()

                try:
                    process.wait(timeout=300)
                except subprocess.TimeoutExpired:
                    process.kill()
                    print("\n❌ Bandit excedeu o tempo limite (5min).")
                    # FIX: Retorna finding sintético para evitar falso negativo
                    return [
                        SecurityFinding(
                            id="bandit-timeout",
                            project_name=self.project_name,
                            tool=ToolType.BANDIT,
                            check_id="TIMEOUT",
                            severity=Severity.HIGH,
                            title="Bandit Scan Timed Out",
                            description="A varredura de segurança excedeu o limite de 5 minutos. Resultados incompletos.",
                            resource_id="FileSystem",
                            references=[],
                        )
                    ]

                sys.stdout.write("\r" + " " * 90 + "\r")  # Limpa linha

                try:
                    # Lê o relatório do arquivo
                    with open(tmp.name, "r") as f:
                        content = f.read()
                        if content:
                            data = json.loads(content)
                            for res in data.get("results") or []:
                                finding = SecurityFinding(
                                    id=self._generate_id(
                                        ToolType.BANDIT, res["test_id"], res["filename"]
                                    ),
                                    project_name=self.project_name,
                                    tool=ToolType.BANDIT,
                                    check_id=res["test_id"],
                                    severity=self._map_severity(res["issue_severity"]),
                                    title=res["issue_text"],
                                    description=f"CWE-{res.get('cwe_id', '?')}: {res['issue_text']}",
                                    resource_id=res["filename"],
                                    line=res["line_number"],
                                    references=[res.get("more_info", "")],
                                )
                                findings.append(finding)
                except json.JSONDecodeError as e:
                    print(f"⚠️  [Bandit] Falha ao decodificar saída JSON: {e}")
            finally:
                Path(tmp.name).unlink(missing_ok=True)
        except Exception as e:
            print(f"❌ Erro ao rodar Bandit: {e}")
        return findings

    def run_trivy(self, target_dir: str = ".") -> List[SecurityFinding]:
        """Executa Trivy (Filesystem & Misconfig) e normaliza."""
        findings = []
        try:
            # fs scan, json output, quiet
            # FIX: Usa arquivo temporário para separar JSON do log de progresso (Visual Feedback)
            # Windows Fix: delete=False e close() antes de passar para subprocesso
            tmp = tempfile.NamedTemporaryFile(suffix=".json", mode="w+", delete=False)
            tmp.close()
            try:
                # CONFIGURAÇÃO: Usa trivy.yaml na raiz
                trivy_path = shutil.which("trivy")
                if not trivy_path:
                    print("❌ Trivy não encontrado no PATH. Pulando.")
                    return []
                cmd = [
                    trivy_path,
                    "fs",
                    target_dir,
                    "--output",
                    tmp.name,
                    "--no-progress",
                ]

                if Path("trivy.yaml").exists():
                    cmd.extend(["--config", "trivy.yaml"])
                else:
                    # Fallback para garantir JSON se não houver config
                    cmd.extend(
                        ["--format", "json", "--scanners", "vuln,secret,misconfig", "--skip-dirs", ".terragrunt-cache", "--skip-dirs", ".git"]
                    )

                process = subprocess.Popen(  # nosec B603
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                )

                # Stream de progresso (Download DB, Scanning...)
                if process.stdout:
                    for line in process.stdout:
                        line = line.strip()
                        if line:
                            msg = f"   [Trivy] {line}"
                            if len(msg) > 90:
                                msg = msg[:87] + "..."
                            sys.stdout.write(f"\r{msg:<90}")
                            sys.stdout.flush()

                try:
                    process.wait(
                        timeout=600
                    )  # 10 min timeout (DB Download pode demorar)
                except subprocess.TimeoutExpired:
                    process.kill()
                    print("\n❌ Trivy excedeu o tempo limite (10min).")
                    # FIX: Retorna finding sintético para evitar falso negativo
                    return [
                        SecurityFinding(
                            id="trivy-timeout",
                            project_name=self.project_name,
                            tool=ToolType.TRIVY,
                            check_id="TIMEOUT",
                            severity=Severity.HIGH,
                            title="Trivy Scan Timed Out",
                            description="A varredura de segurança excedeu o limite de 10 minutos. Resultados incompletos.",
                            resource_id="FileSystem",
                            references=[],
                        )
                    ]

                sys.stdout.write("\r" + " " * 90 + "\r")  # Limpa linha

                try:
                    with open(tmp.name, "r") as f:
                        content = f.read()
                        if content:
                            data = json.loads(content)
                            # Trivy JSON structure: { "Results": [ ... ] }
                            for res in data.get("Results") or []:
                                target = res.get("Target", "unknown")

                                # Process Vulnerabilities
                                for vuln in res.get("Vulnerabilities") or []:
                                    finding = SecurityFinding(
                                        id=self._generate_id(
                                            ToolType.TRIVY,
                                            vuln["VulnerabilityID"],
                                            target,
                                        ),
                                        project_name=self.project_name,
                                        tool=ToolType.TRIVY,
                                        check_id=vuln["VulnerabilityID"],
                                        severity=self._map_severity(vuln["Severity"]),
                                        title=vuln.get("Title")
                                        or vuln.get("PkgName", "Unknown Vuln"),
                                        description=vuln.get("Description", ""),
                                        resource_id=target,
                                        references=vuln.get("References", []),
                                    )
                                    findings.append(finding)

                                # Process Misconfigurations
                                for mis in res.get("Misconfigurations") or []:
                                    finding = SecurityFinding(
                                        id=self._generate_id(
                                            ToolType.TRIVY, mis["ID"], target
                                        ),
                                        project_name=self.project_name,
                                        tool=ToolType.TRIVY,
                                        check_id=mis["ID"],
                                        severity=self._map_severity(mis["Severity"]),
                                        title=mis.get("Title", "Misconfig"),
                                        description=mis.get("Description", ""),
                                        resource_id=target,
                                        references=[mis.get("PrimaryURL", "")],
                                    )
                                    findings.append(finding)
                except json.JSONDecodeError as e:
                    print(f"⚠️  [Trivy] Falha ao decodificar saída JSON: {e}")
            finally:
                Path(tmp.name).unlink(missing_ok=True)
        except Exception as e:
            print(f"❌ Erro ao rodar Trivy: {e}")
        return findings

    def run_gitleaks(self, target_dir: str = ".") -> List[SecurityFinding]:
        """Executa Gitleaks (Secrets) e normaliza."""
        findings = []

        try:
            # Windows Fix: delete=False e close() antes de passar para subprocesso
            tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
            tmp.close()
            try:
                # --no-git para escanear arquivos atuais (snapshot), --exit-code 0 para não quebrar
                gitleaks_path = shutil.which("gitleaks")
                if not gitleaks_path:
                    print("❌ Gitleaks não encontrado no PATH. Pulando.")
                    return []
                cmd = [
                    gitleaks_path,
                    "detect",
                    "--source",
                    target_dir,
                    "--report-path",
                    tmp.name,
                    "--no-banner",
                    "--exit-code",
                    "0",
                    "--no-git",
                ]

                # Usa configuração explícita se existir na raiz
                if Path("gitleaks.toml").exists():
                    cmd.extend(["--config", "gitleaks.toml"])

                subprocess.run(
                    cmd, capture_output=True, text=True, timeout=900
                )  # nosec B603

                try:
                    # Gitleaks escreve no arquivo, não stdout
                    with open(tmp.name, "r") as f:
                        content = f.read()
                        if content:
                            data = json.loads(content)
                            for leak in data:
                                finding = SecurityFinding(
                                    id=self._generate_id(
                                        ToolType.GITLEAKS, leak["RuleID"], leak["File"]
                                    ),
                                    project_name=self.project_name,
                                    tool=ToolType.GITLEAKS,
                                    check_id=leak["RuleID"],
                                    severity=Severity.CRITICAL,
                                    title=f"Secret found: {leak.get('Description', 'Potential Secret')}",
                                    description=f"Match: {leak.get('Match', '')[:50]}...",
                                    resource_id=leak["File"],
                                    line=leak["StartLine"],
                                    references=[
                                        f"Commit: {leak.get('Commit', 'local')}"
                                    ],
                                )
                                findings.append(finding)
                except (json.JSONDecodeError, FileNotFoundError) as e:
                    print(f"⚠️  [Gitleaks] Falha ao ler relatório: {e}")
            finally:
                Path(tmp.name).unlink(missing_ok=True)
        except Exception as e:
            print(f"❌ Erro ao rodar Gitleaks: {e}")
        return findings

    def run_tfsec(self, target_dir: str = ".") -> List[SecurityFinding]:
        """Executa TFSec (IaC Security) e normaliza."""
        findings = []
        try:
            # TFSec busca automaticamente .tfsec.yml na raiz
            tfsec_path = shutil.which("tfsec")
            if not tfsec_path:
                print("❌ TFSec não encontrado no PATH. Pulando.")
                return []
            cmd = [tfsec_path, target_dir, "--format", "json", "--soft-fail", "--exclude-path", ".terragrunt-cache"]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300
            )  # nosec B603

            try:
                data = json.loads(result.stdout)
                for res in data.get("results") or []:
                    finding = SecurityFinding(
                        id=self._generate_id(
                            ToolType.TFSEC, res["rule_id"], res["location"]["filename"]
                        ),
                        project_name=self.project_name,
                        tool=ToolType.TFSEC,
                        check_id=res["rule_id"],
                        severity=self._map_severity(res["severity"]),
                        title=res["description"],
                        description=f"{res['description']}\nImpact: {res['impact']}",
                        resource_id=res["resource"],
                        line=res["location"]["start_line"],
                        references=res.get("links", []),
                    )
                    findings.append(finding)
            except json.JSONDecodeError as e:
                print(f"⚠️  [TFSec] Falha ao decodificar saída JSON: {e}")
        except subprocess.TimeoutExpired:
            print("❌ TFSec excedeu o tempo limite (5min).")
            return [
                SecurityFinding(
                    id="tfsec-timeout",
                    project_name=self.project_name,
                    tool=ToolType.TFSEC,
                    check_id="TIMEOUT",
                    severity=Severity.HIGH,
                    title="TFSec Scan Timed Out",
                    description="A varredura de segurança excedeu o limite de 5 minutos.",
                    resource_id="FileSystem",
                    references=[],
                )
            ]
        except Exception as e:
            print(f"❌ Erro ao rodar TFSec: {e}")
        return findings

    def run_tflint(self, target_dir: str = ".") -> List[SecurityFinding]:
        """Executa TFLint (Best Practices) e normaliza."""
        findings = []
        try:
            tflint_path = shutil.which("tflint")
            if not tflint_path:
                print("❌ TFLint não encontrado no PATH. Pulando.")
                return []

            # TFLint precisa de init para baixar plugins definidos no .tflint.hcl
            if Path(".tflint.hcl").exists():
                subprocess.run(
                    [tflint_path, "--init"], capture_output=True, check=False
                )  # nosec B603

            cmd = [tflint_path, "--format", "json"]
            # TFLint roda no diretório onde está o .tflint.hcl ou target
            result = subprocess.run(
                cmd, cwd=target_dir, capture_output=True, text=True, timeout=300
            )  # nosec B603

            try:
                data = json.loads(result.stdout)
                for res in data.get("issues") or []:
                    finding = SecurityFinding(
                        id=self._generate_id(
                            ToolType.TFLINT,
                            res["rule"]["name"],
                            res["range"]["filename"],
                        ),
                        project_name=self.project_name,
                        tool=ToolType.TFLINT,
                        check_id=res["rule"]["name"],
                        severity=self._map_severity(res["rule"]["severity"]),
                        title=res["message"],
                        description=f"Type: {res['rule']['link']}",
                        resource_id=res["range"]["filename"],
                        line=res["range"]["start"]["line"],
                        references=[res["rule"]["link"]],
                    )
                    findings.append(finding)
            except json.JSONDecodeError as e:
                print(f"⚠️  [TFLint] Falha ao decodificar saída JSON: {e}")
        except subprocess.TimeoutExpired:
            print("❌ TFLint excedeu o tempo limite (5min).")
            return [
                SecurityFinding(
                    id="tflint-timeout",
                    project_name=self.project_name,
                    tool=ToolType.TFLINT,
                    check_id="TIMEOUT",
                    severity=Severity.HIGH,
                    title="TFLint Scan Timed Out",
                    description="A varredura de linting excedeu o limite de 5 minutos.",
                    resource_id="FileSystem",
                    references=[],
                )
            ]
        except Exception as e:
            print(f"❌ Erro ao rodar TFLint: {e}")
        return findings

    def run_prowler(self, region: str = None) -> List[SecurityFinding]:
        """Executa Prowler (AWS Cloud Posture) e normaliza."""
        findings = []

        # Auto-detecção via Boto3 se região não for fornecida
        detected_region, account = self._detect_aws_context()
        target_region = region or detected_region

        print("   Running Prowler (AWS Cloud Posture)...")
        print(f"   [Context] Account: {account} | Region: {target_region}")

        try:
            prowler_path = shutil.which("prowler")
            use_docker = False

            if not prowler_path:
                if shutil.which("docker"):
                    # Verifica se o container está rodando
                    check_container = subprocess.run(
                        ["docker", "ps", "-q", "-f", "name=mcp-terraform"],
                        capture_output=True,
                        text=True
                    )
                    if check_container.returncode == 0 and check_container.stdout.strip():
                        use_docker = True
                        print("   [Mode] Docker (mcp-terraform)")
                    else:
                        print("❌ Prowler não encontrado localmente e container 'mcp-terraform' não está rodando.")
                        return []
                else:
                    print("❌ Prowler não encontrado no PATH. Pulando.")
                    return []

            # Lógica para execução
            output_json_content = None

            if use_docker:
                # Executa no container e lê a saída
                # Usamos um diretório temporário dentro do container para garantir escrita
                container_tmp = "/tmp/prowler_scan"
                # Limpa anterior se existir
                subprocess.run(["docker", "exec", "mcp-terraform", "rm", "-rf", container_tmp], check=False)

                cmd = [
                    "docker", "exec", "mcp-terraform",
                    "prowler", "aws",
                    "--region", target_region,
                    "--output-modes", "json",
                    "--output-filename", "prowler-output",
                    "--output-directory", container_tmp,
                    "--quiet"
                ]

                subprocess.run(cmd, capture_output=True, text=True, timeout=900)

                # Lê o arquivo gerado
                read_cmd = ["docker", "exec", "mcp-terraform", "cat", f"{container_tmp}/prowler-output.json"]
                read_result = subprocess.run(read_cmd, capture_output=True, text=True)
                if read_result.returncode == 0:
                    output_json_content = read_result.stdout

            else:
                # Execução Local
                with tempfile.TemporaryDirectory() as tmpdir:
                    cmd = [
                        prowler_path,
                        "aws",
                        "--region",
                        target_region,
                        "--output-modes",
                        "json",
                        "--output-filename",
                        "prowler-output",
                        "--output-directory",
                        tmpdir,
                        "--quiet",
                    ]

                    subprocess.run(
                        cmd, capture_output=True, text=True, timeout=900
                    )  # nosec B603

                    output_file = Path(tmpdir) / "prowler-output.json"
                    if output_file.exists():
                        output_json_content = output_file.read_text()

            # Processamento comum
            if output_json_content:
                try:
                    data = json.loads(output_json_content)
                    for res in data:
                        # Filtra apenas falhas (FAIL) para reduzir ruído
                        if res.get("Status") != "FAIL":
                            continue

                        check_id = res.get("CheckID") or "unknown-check"
                        resource_id = res.get("ResourceId") or "N/A"

                        # Use intermediate variables for clarity and to help static analysis and prevent type errors
                        finding_title = res.get("CheckTitle") or check_id
                        finding_description = (
                            res.get("Description") or res.get("CheckTitle") or ""
                        )
                        finding_region = res.get("Region") or target_region
                        remediation_url = (
                            res.get("Remediation", {})
                            .get("Recommendation", {})
                            .get("Url", "")
                        )

                        finding = SecurityFinding(
                            id=self._generate_id(
                                ToolType.PROWLER, str(check_id), str(resource_id), finding_region
                            ),
                            project_name=self.project_name,
                            tool=ToolType.PROWLER,
                            check_id=check_id,
                            severity=self._map_severity(res.get("Severity")),
                            title=finding_title,
                            description=finding_description,
                            resource_id=resource_id,
                            region=finding_region,
                            references=[remediation_url] if remediation_url else [],
                        )
                        findings.append(finding)
                except json.JSONDecodeError as e:
                    print(f"⚠️  [Prowler] Falha ao decodificar saída JSON: {e}")
        except subprocess.TimeoutExpired:
            print("❌ Prowler excedeu o tempo limite (15min).")
            # Adiciona finding sintético para não gerar falso negativo
            findings.append(
                SecurityFinding(
                    id="prowler-timeout",
                    project_name=self.project_name,
                    tool=ToolType.PROWLER,
                    check_id="TIMEOUT",
                    severity=Severity.HIGH,
                    title="Prowler Scan Timed Out",
                    description="A varredura de segurança excedeu o limite de 15 minutos. Os resultados estão incompletos.",
                    resource_id="AWS Account",
                    references=[],
                )
            )
        except Exception as e:
            print(f"❌ Erro ao rodar Prowler: {e}")
        return findings

    def run_all(self, target_dir: str = ".") -> List[SecurityFinding]:
        """Executa todas as ferramentas disponíveis."""
        all_findings = []
        print("🛡️  Iniciando varredura unificada (A-PONTE Security)...")

        # Checkov
        print("   Running Checkov (IaC)...")
        all_findings.extend(self.run_checkov(target_dir))

        # Bandit
        print("   Running Bandit (SAST)...")
        all_findings.extend(self.run_bandit(target_dir))

        # Trivy
        print("   Running Trivy (Vuln & Misconfig)...")
        all_findings.extend(self.run_trivy(target_dir))

        # Gitleaks
        print("   Running Gitleaks (Secrets)...")
        all_findings.extend(self.run_gitleaks(target_dir))

        # TFSec
        print("   Running TFSec (IaC Security)...")
        all_findings.extend(self.run_tfsec(target_dir))

        # TFLint
        print("   Running TFLint (Best Practices)...")
        all_findings.extend(self.run_tflint(target_dir))

        return all_findings


if __name__ == "__main__":
    # Exemplo de uso CLI
    import argparse

    parser = argparse.ArgumentParser(description="A-PONTE Security Ingestor")
    parser.add_argument("--project", required=True, help="Nome do projeto (Tenant)")
    parser.add_argument("--dir", default=".", help="Diretório alvo")
    parser.add_argument(
        "--tool",
        choices=[
            "checkov",
            "trivy",
            "prowler",
            "tfsec",
            "gitleaks",
            "bandit",
            "tflint",
            "all",
        ],
        default="all",
        help="Ferramenta específica para executar",
    )
    parser.add_argument(
        "--include-prowler",
        action="store_true",
        help="Inclui scan de nuvem (Prowler) ao rodar 'all'",
    )
    parser.add_argument(
        "--region", default=None, help="Região AWS para Prowler (Opcional, auto-detect)"
    )
    parser.add_argument(
        "--output", default=None, help="Arquivo de saída para o relatório JSON"
    )
    args = parser.parse_args()

    ingestor = SecurityIngestor(args.project)
    findings = []

    if args.tool == "all":
        findings = ingestor.run_all(args.dir)
        if args.include_prowler:
            findings.extend(ingestor.run_prowler(args.region))
    else:
        print(f"🛡️  Executando ferramenta individual: {args.tool.upper()}...")
        tool_map = {
            "checkov": lambda: ingestor.run_checkov(args.dir),
            "trivy": lambda: ingestor.run_trivy(args.dir),
            "prowler": lambda: ingestor.run_prowler(args.region),
            "tfsec": lambda: ingestor.run_tfsec(args.dir),
            "gitleaks": lambda: ingestor.run_gitleaks(args.dir),
            "bandit": lambda: ingestor.run_bandit(args.dir),
            "tflint": lambda: ingestor.run_tflint(args.dir),
        }
        if args.tool in tool_map:
            findings = tool_map[args.tool]()

    # PERSISTÊNCIA CENTRALIZADA (SSOT):
    # Salva o relatório estruturado para consumo do Doctor e Dashboards.
    try:
        root = common.get_project_root()
        report_dir = root / "logs" / "security_reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"{args.project}.json"

        data_to_save = [f.model_dump() for f in findings]

        # Se for execução individual, tenta fazer merge com relatório existente
        if args.tool != "all" and report_file.exists():
            try:
                with open(report_file, "r") as f:
                    existing_data = json.load(f)

                # Filtra removendo resultados antigos da ferramenta atual
                merged_data = [
                    item
                    for item in existing_data
                    if str(item.get("tool", "")).lower() != args.tool
                ]
                merged_data.extend(data_to_save)
                data_to_save = merged_data
            except Exception as e:
                print(
                    f"⚠️  Falha ao ler relatório existente para merge: {e}. Sobrescrevendo."
                )

        # Escrita atômica para evitar arquivos corrompidos/parciais
        with tempfile.NamedTemporaryFile(mode="w", dir=report_dir, delete=False) as tf:
            json.dump(data_to_save, tf, indent=2, default=str)
            temp_name = tf.name

        os.replace(temp_name, report_file)
        os.chmod(report_file, 0o644)  # Garante permissão de leitura para grupo/outros

    except Exception as e:
        print(f"❌ ERRO CRÍTICO: Falha ao salvar relatório centralizado: {e}")
        sys.exit(1)

    print(f"\n✅ Varredura concluída. {len(findings)} problemas encontrados.")

    if args.output:
        with open(args.output, "w") as f:
            json.dump([f.model_dump() for f in findings], f, indent=2, default=str)
        print(f"📄 Relatório salvo em: {args.output}")
    else:
        print(json.dumps([f.model_dump() for f in findings], indent=2, default=str))
