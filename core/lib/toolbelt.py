#!/usr/bin/env python3
"""
A-PONTE Toolbelt (Cinto de Utilidades)
--------------------------------------
Centraliza a execução de ferramentas externas (CLI) para garantir
padronização de chamadas, tratamento de erros e parsing de output.
"""

import json
import functools
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core import prompts

# Registro Centralizado de Ferramentas (Allowlist)
TOOLS_REGISTRY = {
    "aponte audit": "Auditoria de Código/Git (Alinhamento App/Infra)",
    "aponte security scan": "Auditoria de Segurança (Terraform/Checkov)",
    "aponte doctor": "Diagnóstico de Erros/Logs (AI Doctor)",
    "aponte test gen": "Gerar Testes (Terraform Test / Moto)",
    "aponte doc": "Gerar Documentação Técnica (README.md)",
    "aponte pipeline": "Executar Pipeline Completo (Validação)",
    "aponte drift": "Caça Órfãos e Drift (Infra não gerenciada)",
    "aponte cost": "Estimativa de Custo de Infraestrutura (Infracost)",
    "aponte chaos": "Teste de Caos (Chaos Monkey)",
    "aponte ai ingest": "Ingestão de Conhecimento (Auto-Learn)",
}


@functools.lru_cache(maxsize=None)
def is_installed(tool_name: str) -> bool:
    """Verifica se uma ferramenta está no PATH."""
    return shutil.which(tool_name) is not None


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    """Wrapper seguro para subprocess.run."""
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


# --- Funções de Auditoria (Pass/Fail) para Agentes Autônomos ---


def audit_tfsec(target: Path) -> Tuple[bool, str]:
    """Roda tfsec e retorna (Passou?, Output Formatado)."""
    if not is_installed("tfsec"):
        return False, "tfsec not installed"
    cmd = ["tfsec", str(target), "--format", "compact", "--soft-fail"]
    res = _run(cmd)
    passed = "No problems detected" in res.stdout
    return passed, res.stdout.strip()


def audit_checkov(target: Path) -> Tuple[bool, str]:
    """Roda checkov e retorna status."""
    if not is_installed("checkov"):
        return False, "checkov not installed"
    cmd = [
        "checkov",
        "-d" if target.is_dir() else "-f",
        str(target),
        "--quiet",
        "--compact",
        "--soft-fail",
    ]
    res = _run(cmd)
    passed = ("Failed: 0" in res.stdout) or (len(res.stdout.strip()) == 0)
    return passed, res.stdout.strip()


def audit_tflint(target: Path) -> Tuple[bool, str]:
    """Roda tflint e retorna status."""
    if not is_installed("tflint"):
        return False, "tflint not installed"
    scan_dir = target if target.is_dir() else target.parent
    cmd = ["tflint", "--chdir", str(scan_dir), "--format", "compact"]
    res = _run(cmd)
    passed = len(res.stdout.strip()) == 0
    return passed, res.stdout.strip()


def audit_trivy(target: Path) -> Tuple[bool, str]:
    """Roda trivy config e retorna status."""
    if not is_installed("trivy"):
        return False, "trivy not installed"
    cmd = ["trivy", "config", str(target), "--format", "json", "--quiet"]
    res = _run(cmd)
    try:
        data = json.loads(res.stdout)
        passed = True
        if data.get("Results"):
            for result in data["Results"]:
                if result.get("Misconfigurations"):
                    passed = False
                    break
        return passed, "Misconfigurations found" if not passed else "Clean"
    except:
        return False, "JSON Error"


# --- Funções de Relatório Detalhado (Para LLM Context) ---


def get_checkov_report(target: Path) -> str:
    if not is_installed("checkov"):
        return "AVISO: Checkov não instalado.\n"
    cmd = ["checkov", "-f", str(target), "--output", "json", "--quiet", "--soft-fail"]
    res = _run(cmd)
    try:
        data = json.loads(res.stdout)
        if isinstance(data, list):
            data = data[0]
        failed = data.get("results", {}).get("failed_checks", [])
        if not failed:
            return ""
        report = "\n".join(
            [
                f"- {c['check_id']}: {c['check_name']} (Lines: {c['file_line_range']})"
                for c in failed
            ]
        )
        return f"RELATÓRIO SAST (CHECKOV):\n{report}\n"
    except:
        return ""


def get_tfsec_report(target: Path) -> str:
    if not is_installed("tfsec"):
        return ""
    cmd = ["tfsec", str(target.parent), "--format", "json", "--soft-fail"]
    res = _run(cmd)
    try:
        data = json.loads(res.stdout)
        results = data.get("results", [])
        relevant = [
            r
            for r in results
            if r.get("location", {}).get("filename", "").endswith(target.name)
        ]
        if relevant:
            report = "\n".join(
                [
                    f"- {r['rule_id']}: {r['description']} (Line: {r['location']['start_line']})"
                    for r in relevant
                ]
            )
            return f"RELATÓRIO TFSEC:\n{report}\n"
    except:
        pass
    return ""


def get_tflint_report(target: Path) -> str:
    if not is_installed("tflint"):
        return ""
    cmd = ["tflint", "--chdir", str(target.parent), "--format", "compact"]
    res = _run(cmd)
    if res.stdout.strip():
        return f"RELATÓRIO TFLINT (QUALITY):\n{res.stdout.strip()}\n"
    return ""


def get_trivy_report(target: Path) -> str:
    if not is_installed("trivy"):
        return ""
    cmd = ["trivy", "config", str(target), "--format", "json", "--quiet"]
    res = _run(cmd)
    try:
        data = json.loads(res.stdout)
        if data.get("Results"):
            misconfs = data["Results"][0].get("Misconfigurations", [])
            if misconfs:
                report = "\n".join(
                    [
                        f"- {m['ID']}: {m['Title']} (Severity: {m['Severity']})"
                        for m in misconfs
                    ]
                )
                return f"RELATÓRIO TRIVY:\n{report}\n"
    except:
        pass
    return ""


def get_hadolint_report(target: Path) -> str:
    """Roda Hadolint (Docker Linter)."""
    if not is_installed("hadolint"):
        return ""
    cmd = ["hadolint", str(target), "--no-fail"]
    res = _run(cmd)
    if res.stdout.strip():
        return f"RELATÓRIO HADOLINT (Boas Práticas Docker):\n{res.stdout.strip()}\n"
    return ""


def get_infracost_report(target: Path) -> str:
    """Roda Infracost (FinOps)."""
    if not is_installed("infracost"):
        return ""
    # Verifica se tem arquivos .tf no alvo
    if target.is_dir() and not list(target.glob("*.tf")):
        return ""

    cmd = [
        "infracost",
        "breakdown",
        "--path",
        str(target),
        "--format",
        "table",
        "--no-color",
    ]
    # Timeout curto (15s) para não travar se pedir login/API Key
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if res.stdout and "OVERALL TOTAL" in res.stdout:
            return f"RELATÓRIO FINOPS (Estimativa de Custos):\n{res.stdout[-500:]}\n"  # Pega o resumo final
    except:
        pass
    return ""


def audit_gitleaks(target: Path) -> bool:
    """Roda Gitleaks para detecção de segredos. Retorna True se limpo."""
    if not is_installed("gitleaks"):
        return True  # Assume limpo se não tiver a ferramenta (Fail Open)
    # --no-git permite escanear diretórios normais sem histórico .git
    cmd = [
        "gitleaks",
        "detect",
        "--source",
        str(target),
        "--no-git",
        "--verbose",
        "--redact",
    ]
    res = _run(cmd)
    return res.returncode == 0  # Gitleaks retorna 1 se achar segredos


# --- Utilitários de Manipulação de Código (HCL/Terraform) ---


def sanitize_hcl(code: str) -> str:
    """Limpa alucinações de sintaxe comuns em modelos menores."""
    lines = code.split("\n")
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()
        # Ignora linhas com atributos inventados conhecidos
        # Usa a lista centralizada em prompts.py
        if any(h in stripped for h in prompts.HCL_HALLUCINATIONS) or stripped == "...":
            continue
        # Substitui aspas simples por duplas (exceto em comentários)
        if not stripped.startswith(("#", "//")):
            line = line.replace("'", '"')
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def validate_hcl_syntax(code: str) -> bool:
    """Valida a sintaxe HCL usando 'terraform fmt' em sandbox."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".tf", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        res = _run(["terraform", "fmt", tmp_path])
        return res.returncode == 0
    except Exception:
        return False
    finally:
        Path(tmp_path).unlink(missing_ok=True)
