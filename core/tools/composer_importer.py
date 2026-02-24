#!/usr/bin/env python3
import sys
import re
import argparse
from pathlib import Path

# Setup paths
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common
from core.services import llm_gateway

def main():
    parser = argparse.ArgumentParser(description="Importador de Templates AWS Application Composer")
    parser.add_argument("--file", type=str, help="Caminho para o arquivo template.yaml ou design.yaml")
    args = parser.parse_args()

    common.console.rule("[bold magenta]🎨 AWS Application Composer Importer[/]")

    # Procura por templates na raiz ou pasta design
    root = common.get_project_root()

    target = None
    if args.file:
        target = Path(args.file).resolve()
        if not target.exists():
            common.log_error(f"Arquivo não encontrado: {target}")
            return
    else:
        candidates = list(root.glob("template.y*ml")) + list(root.glob("design/*.y*ml"))

        if not candidates:
            common.log_warning("Nenhum arquivo 'template.yaml' (CloudFormation/SAM) encontrado.")
            common.console.print("👉 Exporte seu design do AWS Application Composer e salve na raiz do projeto.")
            return

        if len(candidates) == 1:
            target = candidates[0]
        else:
            common.console.print("[yellow]⚠️  Múltiplos templates encontrados:[/]")
            for i, p in enumerate(candidates):
                common.console.print(f"   [bold]{i+1}.[/] {p.relative_to(root)}")

            try:
                choice = input("\n👉 Qual arquivo deseja converter? (Digite o número): ")
                idx = int(choice) - 1
                if 0 <= idx < len(candidates):
                    target = candidates[idx]
                else:
                    common.log_error("Seleção inválida.")
                    return
            except (ValueError, EOFError, KeyboardInterrupt):
                common.log_error("Entrada inválida ou cancelada.")
                return

    common.console.print(f"📄 Template encontrado: [cyan]{target}[/]")

    content = target.read_text()

    prompt = f"""
    Atue como um Engenheiro de Migração Cloud.
    Converta o seguinte template AWS SAM/CloudFormation (YAML) para Terraform (HCL).

    REGRAS:
    1. Use recursos nativos `aws_...`.
    2. Mantenha a lógica de conexão entre recursos.
    3. Adicione tags padrão A-PONTE (Project, Environment).

    TEMPLATE SAM:
    ```yaml
    {content[:5000]}
    ```

    Responda apenas com o código Terraform dentro de um bloco de código.
    """

    common.console.print("[dim]🤖 Convertendo via IA...[/dim]")
    tf_code = llm_gateway.generate(prompt, verbose=True)

    if tf_code:
        out_file = target.with_suffix(".tf")

        # Extração robusta de bloco de código usando Regex
        # Procura por ```hcl ou ```terraform ou apenas ``` e captura o conteúdo
        # Permite espaços opcionais antes da quebra de linha
        match = re.search(r"```(?:hcl|terraform)?.*?\n(.*?)```", tf_code, re.DOTALL)
        if match:
            tf_code = match.group(1)
        else:
            # Fallback: tenta limpar tags se o regex falhar (caso o modelo não feche o bloco corretamente)
            tf_code = tf_code.replace("```hcl", "").replace("```terraform", "").replace("```", "")

        out_file.write_text(tf_code.strip())
        common.log_success(f"Conversão concluída: {out_file}")
        common.console.print("[dim]Revise o código gerado antes de aplicar.[/dim]")

if __name__ == "__main__":
    main()
