import subprocess
import asyncio
import os
import urllib.parse
from typing import Dict, List, Union, Optional

# Cache para tokens de sanitização (evita re-encoding a cada chamada)
_SANITIZATION_CACHE = {}

# Lista de variáveis de ambiente que devem ser redigidas dos logs
SENSITIVE_ENV_VARS = ["GITHUB_TOKEN", "GH_TOKEN"]

def _sanitize_output(stdout: str, stderr: str) -> tuple[str, str]:
    """Remove tokens sensíveis dos outputs."""
    # Atualiza cache se necessário (Lazy Loading com verificação de mudança)
    current_tokens = {
        k: os.getenv(k) for k in SENSITIVE_ENV_VARS if os.getenv(k)
    }
    
    global _SANITIZATION_CACHE
    if current_tokens != _SANITIZATION_CACHE.get("source"):
        replacements = []
        for token in current_tokens.values():
            replacements.append((token, "******"))
            encoded = urllib.parse.quote(token, safe="")
            if encoded != token:
                replacements.append((encoded, "******"))
        _SANITIZATION_CACHE = {"source": current_tokens, "replacements": replacements}

    for target, replacement in _SANITIZATION_CACHE["replacements"]:
        stdout = stdout.replace(target, replacement)
        stderr = stderr.replace(target, replacement)
        
    return stdout, stderr

def run_command(
    cmd: List[str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    check: bool = False
) -> Dict[str, Union[str, int]]:
    """
    Executa comandos de shell de forma segura, padronizada e sanitizada.
    Centraliza a lógica de subprocessos para evitar duplicação e falhas de segurança.
    """
    try:
        # Mescla env fornecido com os.environ para garantir que PATH e outras vars persistam
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=run_env,
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        stdout, stderr = _sanitize_output(stdout, stderr)

        # Lógica de Output Unificado
        output = stdout
        if stderr:
            # Se houver stderr, anexa (útil para ferramentas que escrevem logs no stderr)
            output += f"\n{stderr}" if output else stderr

        status = "success" if result.returncode == 0 else "error"
        
        return {
            "status": status,
            "output": output.strip(),
            "returncode": result.returncode,
            "stdout": stdout,
            "stderr": stderr
        }

    except subprocess.TimeoutExpired:
        return {"status": "error", "output": f"Timeout excedido ({timeout}s)", "returncode": -1}
    except Exception as e:
        return {"status": "error", "output": str(e), "returncode": -1}

async def run_command_async(
    cmd: List[str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    check: bool = False
) -> Dict[str, Union[str, int]]:
    """
    Versão assíncrona de run_command usando asyncio.
    Permite que o servidor MCP continue responsivo durante operações de I/O.
    """
    try:
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env=run_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return {"status": "error", "output": f"Timeout excedido ({timeout}s)", "returncode": -1}

        stdout = stdout_bytes.decode().strip()
        stderr = stderr_bytes.decode().strip()
        returncode = proc.returncode

        stdout, stderr = _sanitize_output(stdout, stderr)

        output = stdout
        if stderr:
            output += f"\n{stderr}" if output else stderr

        status = "success" if returncode == 0 else "error"
        return {"status": status, "output": output.strip(), "returncode": returncode, "stdout": stdout, "stderr": stderr}

    except Exception as e:
        return {"status": "error", "output": str(e), "returncode": -1}