#!/usr/bin/env python3
import re
import sys
import os
import tempfile
import shutil
import subprocess
from pathlib import Path

# Setup paths
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import toolbelt as tools  # noqa: E402
from core.lib import utils as common  # noqa: E402
from core.services import llm_gateway  # noqa: E402


def _find_nearest_config(start_path: Path, config_name: str, root_limit: Path) -> Path | None:
    """Busca arquivo de configuração subindo na árvore de diretórios até o root_limit."""
    current = start_path
    while True:
        candidate = current / config_name
        if candidate.exists():
            return candidate
        if current.resolve() == root_limit.resolve() or current.parent == current:
            break
        current = current.parent
    return None

def _is_likely_terraform(content):
    """Heurística simples para detectar se o conteúdo parece Terraform HCL."""
    keywords = [
        r'resource\s+"', r'module\s+"', r'variable\s+"', r'output\s+"',
        r'terraform\s+\{', r'provider\s+"', r'data\s+"', r'locals\s+\{'
    ]
    return any(re.search(k, content) for k in keywords)

def _validate_and_fix(current_code, provider="ollama", file_path=None, context_dir=None):
    """
    Ciclo interno de validação e auto-correção (Self-Healing).
    Executa linters e pede para a IA corrigir apenas os erros encontrados.
    """
    # SAFETY: Skip validation loop for non-Terraform files to avoid linter errors and hallucinated fixes
    if file_path and not file_path.name.endswith((".tf", ".tfvars")):
        return current_code

    # FIX: Se o arquivo é desconhecido (None), verifica se o conteúdo parece Terraform antes de validar
    if not file_path and not _is_likely_terraform(current_code):
        common.console.print("[dim]ℹ️  Conteúdo não parece Terraform. Pulando validação HCL.[/dim]")
        return current_code

    # Cria diretório temporário único para evitar colisão e permitir contexto
    base_temp = common.get_project_root() / ".aponte-versions" / "tmp"
    base_temp.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=base_temp) as tmp_dir_str:
        temp_dir = Path(tmp_dir_str)

        # 1. Copia Contexto (Irmãos .tf) para validação correta de variáveis/providers
        src_dir = context_dir
        if file_path:
            src_dir = file_path.parent

        has_context = False
        if src_dir and src_dir.exists():
            for tf in src_dir.glob("*.tf"):
                # Copia tudo exceto o arquivo que estamos corrigindo (que será injetado via current_code)
                if not file_path or tf.name != file_path.name:
                    shutil.copy(tf, temp_dir / tf.name)
                    has_context = True

            # Copia variáveis de ambiente (.tfvars) para garantir que testes funcionem com valores reais
            for tfvars in src_dir.glob("*.tfvars"):
                shutil.copy(tfvars, temp_dir / tfvars.name)

            # Copia arquivos de teste nativos (Terraform Test)
            for tftest in src_dir.glob("*.tftest.hcl"):
                shutil.copy(tftest, temp_dir / tftest.name)

            # Otimização: Copia cache do Terraform (.terraform) para evitar init demorado
            dot_terraform = src_dir / ".terraform"
            if dot_terraform.exists():
                # FIX: Usa symlinks=True para evitar erro ao copiar links quebrados ou internos do provider
                shutil.copytree(dot_terraform, temp_dir / ".terraform", dirs_exist_ok=True, symlinks=True, ignore_dangling_symlinks=True)

        # 2. Copia Configurações de Linters
        root = common.get_project_root()
        for config_file in [".tflint.hcl", ".tfsec.yml", ".tfsec.yaml", ".checkov.yml", ".checkov.yaml"]:
            # 1. Global (A-PONTE)
            src = root / config_file
            if src.exists():
                shutil.copy(src, temp_dir / config_file)

            # 2. Local Override (Contexto do Projeto)
            # Busca recursivamente a partir do arquivo alvo até a raiz do projeto
            local_config = None
            if file_path:
                local_config = _find_nearest_config(file_path.parent, config_file, root)
            elif context_dir:
                local_config = _find_nearest_config(context_dir, config_file, root)

            if local_config:
                shutil.copy(local_config, temp_dir / config_file)

        # 3. Injeta Variáveis Padrão (Mock) se variables.tf não estiver no contexto
        # Evita erro de "Undeclared variable" em projetos parciais (Scaffolding)
        vars_file = temp_dir / "variables.tf"
        is_creating_vars = file_path and file_path.name == "variables.tf"

        if not vars_file.exists() and not is_creating_vars:
            mock_vars = ""
            for var in ["project_name", "environment", "app_name", "resource_name", "aws_region", "account_id", "security_email"]:
                mock_vars += f'variable "{var}" {{ type = string default = "mock" }}\n'
            (temp_dir / "_aponte_mock_vars.tf").write_text(mock_vars, encoding="utf-8")

        # FIX: Inicializa TFLint se configuração existir (Plugins)
        # Necessário para carregar plugins (ex: aws) definidos no .tflint.hcl
        if (temp_dir / ".tflint.hcl").exists() and shutil.which("tflint"):
            # OTIMIZAÇÃO: Copia cache de plugins do projeto para evitar download repetitivo (Rate Limit/Performance)
            plugin_cache = root / ".tflint.d"
            if plugin_cache.exists():
                try:
                    shutil.copytree(plugin_cache, temp_dir / ".tflint.d", dirs_exist_ok=True)
                except Exception as e:
                    common.console.print(f"[dim yellow]⚠️  Aviso: Falha ao copiar cache de plugins TFLint: {e}[/dim yellow]")

            try:
                subprocess.run(["tflint", "--init"], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            except Exception as e:
                common.console.print(f"[dim yellow]⚠️  Aviso: Falha ao inicializar plugins TFLint: {e}[/dim yellow]")

        max_retries = 3
        for attempt in range(max_retries + 1):
            # Define nome do arquivo alvo
            target_name = file_path.name if file_path else "generated.tf"
            tmp_path = temp_dir / target_name
            tmp_path.write_text(current_code, encoding="utf-8")

            try:
                common.console.print(
                    f"[dim]🕵️  Validando código (Tentativa {attempt+1}/{max_retries+1})...[/dim]"
                )
                errors = []
                tool_failures = []

                # TFLint (Sintaxe e Regras AWS)
                try:
                    tflint_out = tools.get_tflint_report(tmp_path)
                    if tflint_out:
                        # FIX: Filtra erros de módulo causados pelo isolamento do diretório temporário
                        # Evita que a IA tente corrigir caminhos relativos válidos (../../modules/vpc)
                        filtered_lines = [
                            line for line in tflint_out.splitlines()
                            if "Failed to load module" not in line
                            and "Module source" not in line
                            and "unreadable module directory" not in line.lower()
                        ]
                        filtered_out = "\n".join(filtered_lines)
                        if filtered_out.strip():
                            errors.append(f"--- TFLint Issues ---\n{filtered_out}")
                except Exception as e:
                    msg = f"Falha ao executar TFLint: {e}"
                    common.console.print(f"[dim yellow]⚠️  {msg}[/dim yellow]")
                    tool_failures.append(msg)

                # TFSec (Segurança)
                try:
                    tfsec_out = tools.get_tfsec_report(tmp_path)
                    if tfsec_out:
                        errors.append(f"--- TFSec Issues ---\n{tfsec_out}")
                except Exception as e:
                    msg = f"Falha ao executar TFSec: {e}"
                    common.console.print(f"[dim yellow]⚠️  {msg}[/dim yellow]")
                    tool_failures.append(msg)

                # Checkov (Compliance) - Adicionado para robustez total
                try:
                    # Checkov pode ser lento, usamos apenas se não houver erros de sintaxe (TFLint)
                    if not errors:
                        checkov_out = tools.get_checkov_report(tmp_path)
                        if checkov_out:
                            errors.append(f"--- Checkov Issues ---\n{checkov_out}")
                except Exception as e:
                    msg = f"Falha ao executar Checkov: {e}"
                    common.console.print(f"[dim yellow]⚠️  {msg}[/dim yellow]")
                    tool_failures.append(msg)

                # Terraform Test (Validação Funcional)
                # Executa apenas se houver arquivos de teste no contexto
                if list(temp_dir.glob("*.tftest.hcl")):
                    try:
                        # Init leve (backend=false para não travar state remoto)
                        subprocess.run(["terraform", "init", "-backend=false"], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

                        common.console.print(f"[dim]🧪 Executando testes funcionais (terraform test)...[/dim]")
                        test_res = subprocess.run(["terraform", "test"], cwd=temp_dir, capture_output=True, text=True, check=False)

                        if test_res.returncode != 0:
                            errors.append(f"--- Terraform Test Failures ---\n{test_res.stdout}\n{test_res.stderr}")
                            common.console.print("[red]❌ Falha nos testes funcionais.[/red]")
                    except Exception as e:
                        common.console.print(f"[dim yellow]⚠️  Erro ao executar testes: {e}[/dim yellow]")

                # Se não houver erros, sucesso!
                if not errors:
                    if tool_failures:
                        common.console.print("[bold red]⛔ Validação Incompleta: Ferramentas de segurança falharam ao executar. Código não pode ser certificado.[/bold red]")
                        return None
                    else:
                        common.console.print("[green]✅ Código validado e seguro.[/green]")
                    return current_code

                # Se atingiu o limite, desiste
                if attempt == max_retries:
                    common.console.print(
                        "[red]❌ Limite de auto-correção atingido. Retornando melhor esforço.[/red]"
                    )
                    return current_code

                # Se houver erros, tenta corrigir
                common.console.print(
                    "[bold yellow]🔧 Problemas detectados. Iniciando auto-correção...[/bold yellow]"
                )
                error_report = "\n".join(errors)

                fix_prompt = f"""
                Você é um especialista em correção de código Terraform.
                O código gerado anteriormente apresentou os seguintes problemas de validação:

                {error_report}

                CÓDIGO ORIGINAL:
                ```hcl
                {current_code}
                ```

                TAREFA:
                Corrija o código para resolver os problemas apontados.
                Mantenha a lógica original, apenas ajuste a sintaxe ou segurança.
                REGRAS:
                1. Não aninhe recursos (ex: bucket_policy dentro de aws_s3_bucket). Use recursos separados.
                2. Responda APENAS com o código corrigido dentro de blocos ```hcl ... ```.
                """

                fixed_code = llm_gateway.generate(
                    fix_prompt, provider=provider, verbose=True
                )

                if not fixed_code:
                    common.console.print("[red]❌ Falha na geração da correção. Mantendo versão anterior.[/red]")
                    return current_code

                current_code = _extract_code(fixed_code)
                common.console.print(f"[green]✅ Código corrigido (Iteração {attempt+1}).[/green]")

            except Exception as e:
                common.console.print(f"[red]❌ Erro durante validação: {e}[/red]")
                return current_code

    return current_code


def generate_code(instruction, context="", project_dir=None, filename=None):
    """
    Gera código usando o modelo local (Ollama) com ciclo de auto-correção (Self-Healing).
    Integra TFLint, TFSec e Checkov para garantir robustez antes de entregar o resultado.
    """
    # Lógica de Leitura de Arquivo Existente (Append/Modify Mode)
    existing_code = ""
    if project_dir and filename:
        target_file = project_dir / filename
        if target_file.exists():
            try:
                existing_code = target_file.read_text(encoding="utf-8")
            except Exception as e:
                common.console.print(f"[red]❌ Erro de Segurança: Falha ao ler arquivo existente '{filename}' para modificação: {e}. Abortando para evitar sobrescrita acidental.[/red]")
                return None

    is_tf = not filename or filename.endswith((".tf", ".tfvars"))

    # 1. Geração Inicial
    if existing_code and is_tf:
        prompt = f"""
        Você é um especialista em Terraform e AWS (Operário de Código).
        Sua tarefa é MODIFICAR o código Terraform existente no arquivo '{filename}' baseado na instrução abaixo.

        IMPORTANTE:
        - Mantenha a lógica existente e apenas adicione ou altere o que foi pedido.
        - Não remova recursos existentes a menos que explicitamente solicitado.
        - Utilize seu conhecimento treinado (ADRs, Padrões de Segurança) para gerar código compatível.

        CONTEXTO DO PROJETO:
        {context}

        CÓDIGO EXISTENTE:
        ```hcl
        {existing_code}
        ```

        INSTRUÇÃO DO ARQUITETO:
        {instruction}

        REGRAS:
        1. Responda com o código Terraform COMPLETO (Existente + Modificações) dentro de blocos ```hcl ... ```.
        2. Não explique nada. Apenas gere o código.
        3. Use variáveis onde apropriado (var.project_name, var.environment).
        4. NÃO aninhe blocos como 'policy', 'versioning' dentro de 'aws_s3_bucket'. Use recursos separados.
        """
    elif is_tf:
        prompt = f"""
        Você é um especialista em Terraform e AWS (Operário de Código).
        Sua tarefa é gerar código Terraform (HCL) baseado na instrução abaixo.

        IMPORTANTE: Utilize seu conhecimento treinado (ADRs, Padrões de Segurança e Estrutura do Projeto) para gerar código compatível com a plataforma A-PONTE.

        CONTEXTO DO PROJETO:
        {context}

        INSTRUÇÃO DO ARQUITETO:
        {instruction}

        REGRAS:
        1. Responda APENAS com o código Terraform dentro de blocos ```hcl ... ```.
        2. Não explique nada. Apenas gere o código.
        3. Use variáveis onde apropriado (var.project_name, var.environment).
        4. NÃO aninhe blocos como 'policy', 'versioning', 'server_side_encryption_configuration' dentro de 'aws_s3_bucket'. Use recursos separados (ex: aws_s3_bucket_policy, aws_s3_bucket_versioning).
        """
    else:
        # INFRASTRUCTURE SUPPORT PROMPT
        prompt = f"""
        Você é um Especialista em DevOps e Automação.
        Sua tarefa é gerar ou modificar o arquivo de suporte '{filename}' (ex: Dockerfile, Script, Config) para a infraestrutura.

        CONTEXTO DO PROJETO:
        {context}

        INSTRUÇÃO:
        {instruction}

        {f"CÓDIGO EXISTENTE:\n```{existing_code}```" if existing_code else ""}

        REGRAS:
        1. Responda APENAS com o código do arquivo dentro de blocos de código markdown (ex: ```python ... ```).
        2. Não adicione explicações.
        3. Mantenha o foco em infraestrutura. Não gere lógica de negócio de aplicação.
        """

    common.console.print("[dim]🔨 Gerando código inicial...[/dim]")
    provider = os.getenv("APONTE_LOCAL_CODER_PROVIDER", "ollama")
    current_code = llm_gateway.generate(prompt, provider=provider, verbose=True)
    current_code = _extract_code(current_code, filename)

    # SAFETY NET: Validação de Integridade (Evita perda de código em modificações)
    if existing_code:
        # 1. Detecta marcadores de preguiça da IA
        lazy_markers = ["// ...", "# ...", "/* ... */", "existing code", "rest of the code", "unchanged"]
        if any(m in current_code for m in lazy_markers):
            common.console.print("[red]❌ Erro de Segurança: A IA retornou código truncado (Lazy). Operação abortada para evitar perda de dados.[/red]")
            return None

        # 2. Heurística de Tamanho: Se o novo código for < 50% do original, é suspeito
        # (A menos que a instrução fosse explícita para remover/refatorar)
        is_deletion_request = False
        if instruction:
            is_deletion_request = any(kw in instruction.lower() for kw in ["remove", "delete", "destroy", "drop", "limpar"])

        if len(current_code) < len(existing_code) * 0.5 and not is_deletion_request:
             common.console.print(f"[red]❌ Erro de Segurança: O código gerado é muito menor que o original ({len(current_code)} vs {len(existing_code)} chars). Possível perda de dados.[/red]")
             return None

    # Sanity Check: Se a geração falhou ou retornou fallback de erro
    if not current_code or current_code.strip() == "...":
        common.console.print("[red]❌ Falha na geração do código inicial. Abortando.[/red]")
        return None

    # Constrói file_path se filename for fornecido, para permitir exclusão correta do contexto
    file_path = None
    if project_dir and filename:
        file_path = project_dir / filename

    # 2. Delega para o ciclo de validação
    return _validate_and_fix(current_code, provider, context_dir=project_dir, file_path=file_path)


def fix_code(content, instruction=None, context="", file_path=None):
    """
    Ponto de entrada para corrigir código existente (usado pelo Auditor).
    Se 'instruction' for fornecida, usa a IA para aplicar a correção antes da validação.
    """
    provider = os.getenv("APONTE_LOCAL_CODER_PROVIDER", "ollama")
    common.console.print("[dim]🔧 Local Coder: Iniciando ciclo de reparo...[/dim]")

    if instruction:
        common.console.print("[dim]🧠 Aplicando correções sugeridas pela Auditoria...[/dim]")

        # Detecta tipo de arquivo para Prompt Poliglota
        is_tf = not file_path or file_path.name.endswith((".tf", ".tfvars"))
        filename = file_path.name if file_path else "code"

        if is_tf:
            prompt = f"""
            Você é um Engenheiro de Software (Operário).
            Sua tarefa é corrigir o código Terraform abaixo seguindo ESTRITAMENTE as instruções de auditoria.

            CÓDIGO ORIGINAL:
            ```hcl
            {content}
            ```

            INSTRUÇÕES DE CORREÇÃO (AUDITORIA):
            {instruction}

            REGRAS:
            1. Retorne APENAS o código HCL corrigido dentro de blocos ```hcl ... ```.
            2. Mantenha o restante do código que não precisa de alteração.
            3. Não adicione explicações.
            """
        else:
            # Prompt para arquivos de suporte (Dockerfile, Python, etc)
            prompt = f"""
            Você é um Especialista em DevOps e Automação.
            Sua tarefa é corrigir o código no arquivo de suporte '{filename}' seguindo as instruções.

            CÓDIGO ORIGINAL:
            ```{filename.split('.')[-1] if '.' in filename else ''}
            {content}
            ```

            INSTRUÇÕES:
            {instruction}

            REGRAS:
            1. Retorne APENAS o código corrigido dentro de blocos de código markdown.
            2. Mantenha o restante do código que não precisa de alteração.
            3. Não adicione explicações.
            """

        generated = llm_gateway.generate(prompt, provider=provider, verbose=True)
        if not generated:
            return None

        fixed_content = _extract_code(generated, filename=filename)

        if not fixed_content:
            common.console.print("[red]❌ Erro: A IA não retornou um bloco de código válido (Markdown). Operação abortada.[/red]")
            return None

        # SAFETY NET: Validação de Integridade (Sincronizado com generate_code)
        lazy_markers = ["// ...", "# ...", "/* ... */", "existing code", "rest of the code"]
        if any(m in fixed_content for m in lazy_markers):
            common.console.print("[red]❌ Erro de Segurança: A IA retornou código truncado (Lazy). Operação abortada.[/red]")
            return None

        # Heurística de Tamanho
        is_deletion_request = any(kw in instruction.lower() for kw in ["remove", "delete", "destroy", "drop"])
        if len(fixed_content) < len(content) * 0.5 and not is_deletion_request:
             common.console.print(f"[red]❌ Erro de Segurança: O código corrigido é muito menor que o original. Possível perda de dados.[/red]")
             return None

        content = fixed_content

    return _validate_and_fix(content, provider, file_path=file_path)


def _extract_code(text, filename=None):
    if not text:
        return None

    is_tf = not filename or filename.endswith((".tf", ".tfvars"))

    if is_tf:
        # 1. Prioridade: Blocos explicitamente marcados como HCL/Terraform
        matches = re.findall(r"```(?:hcl|terraform)\s+(.*?)```", text, re.DOTALL)
        if matches:
            return max(matches, key=len).strip()

    # 2. Fallback: Qualquer bloco de código (se a IA esqueceu a tag)
    matches = re.findall(r"```(?:\w+)?\s+(.*?)```", text, re.DOTALL)
    if matches:
        return max(matches, key=len).strip()

    # STRICT MODE: Retorna None se não encontrar blocos de código
    # Evita salvar explicações da IA como código (ex: "Aqui está o arquivo: ...")
    return None
