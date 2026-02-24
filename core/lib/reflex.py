import re

class ReflexEngine:
    """
    Motor de "Sistema 1" (Rápido e Intuitivo) para bypassar o LLM.
    Mapeia padrões de input do usuário diretamente para comandos de ferramentas,
    evitando o custo de processamento do grafo para tarefas simples.
    """
    def __init__(self):
        # Mapeamento de padrões regex para (nome da ferramenta, nome da extensão, opções).
        # Opções é um dicionário que pode conter 'fixed_args' e 'destructive'.
        # A ordem é importante: os mais específicos devem vir primeiro.
        self.rules = [
            # --- Navegação e Sistema (Core) ---
            (r"^(?:ls|dir|listar\s+arquivos|conteudo\s+da\s+pasta)(?:\s+do\s+projeto|\s+daqui)?$", "list_directory", "core", {}),
            (r"^(?:ls|dir)\s+(?P<path>[\w\./-]+)$", "list_directory", "core", {}),
            (r"^(?:cat|leia|ler|mostrar)\s+(?P<path>.+)", "read_file", "core", {}),
            (r"^(?:tree|estrutura|arvore)(?:\s+do\s+projeto|\s+de\s+pastas)?$", "list_directory", "core", {"fixed_args": {"recursive": True}}),
            (r"^(?:doctor|diagnostico|saude\s+do\s+sistema)(?:\s+agora)?$", "check_health", "core", {}),

            # --- Snippets (Reutilização) ---
            (r"^(?:liste|listar|ver|mostrar)\s+snippets(?:\s+de\s+infra)?$", "list_snippets", "snippets", {}),
            (r"^(?:ver|mostrar|ler|usar)\s+snippet\s+(?P<filename>[\w\.-]+)$", "get_snippet", "snippets", {}),

            # --- Operações AWS (Cloud) ---
            (r"^(?:s3\s+ls|list(?:ar|e)?\s+(?:os\s+)?bucket(?:s)?(?:\s+s3)?|meus\s+buckets)(?:\s+na\s+aws)?$", "aws_list_buckets", "aws", {}),
            (r"^(?:ec2\s+ls|list(?:ar|e)?\s+(?:as\s+)?(?:instancias|instâncias|ec2|maquinas|máquinas)(?:\s+ec2)?|minhas\s+vms)(?:\s+na\s+aws)?$", "aws_list_ec2_instances", "aws", {}),

            # Reflexo: Alarmes Ativos (Observabilidade em Tempo Real)
            (r"^(?:liste|listar|ver|checar|quais)\s+(?:os\s+)?(?:alarmes|alertas)(?:\s+ativos|\s+disparados|\s+em\s+erro)?(?:\s+na\s+aws)?$", "aws_list_cloudwatch_alarms", "aws", {"fixed_args": {"state": "ALARM"}}),

            # Reflexo: Status de Segurança (CloudTrail)
            (r"^(?:ver|checar|status|estado)\s+(?:do\s+)?cloudtrail(?:\s+na\s+aws)?$", "aws_check_cloudtrail", "aws", {}),

            # Reflexo Paramétrico: Alarmes com intervalo de datas
            (r"^(?:(?:liste|listar|ver|checar)\s+)?(?:alarmes?)(?:.*?)?\s+(?:entre|de|desde|no)(?:\s+dias?)?\s+(?P<start_time>[\d/-]+)\s+(?:e|a|ate|até)\s+(?P<end_time>[\d/-]+)$", "aws_list_alarm_history", "aws", {}),

            # Reflexo Paramétrico: Logs/Auditoria com intervalo de datas
            (r"^(?:(?:liste|listar|ver|checar)\s+)?(?:logs|eventos|auditoria)(?:.*?)?\s+(?:entre|de|desde|no)(?:\s+dias?)?\s+(?P<start_time>[\d/-]+)\s+(?:e|a|ate|até)\s+(?P<end_time>[\d/-]+)$", "aws_lookup_events", "aws", {}),
            (r"^(?:logs|ver\s+logs|cloudwatch\s+logs)(?:\s+na\s+aws)?$", "aws_lookup_events", "aws", {}),

            (r"^(?:liste|listar|ver)\s+(?:todos\s+os\s+)?recursos(?:\s+na\s+aws)?$", "aws_list_resources", "aws", {}),
            (r"^(?:liste|listar|ver)\s+(?:grupos\s+de\s+)?logs(?:\s+groups?)?(?:\s+na\s+aws)?$", "aws_list_log_groups", "aws", {}),
            (r"^(?:previsao|forecast)\s+de\s+(?:custo|gastos)(?:\s+na\s+aws)?$", "aws_get_cost_forecast", "aws", {}),
            (r"^(?:whoami|quem\s+sou\s+eu|aws\s+identity)(?:\s+na\s+aws)?$", "aws_get_caller_identity", "aws", {}),

            # --- Infraestrutura como Código (Terraform) ---
            (r"^(?:tf\s+plan|planejar|verificar\s+mudanças)(?:\s+no\s+projeto(?:\s+atual)?)?$", "tf_plan", "terraform", {}),
            (r"^(?:tf\s+apply|aplicar|deploy)(?:\s+no\s+projeto(?:\s+atual)?)?$", "tf_apply", "terraform", {"destructive": True}),
            (r"^(?:tf\s+destroy|destruir\s+infra)(?:\s+no\s+projeto(?:\s+atual)?)?$", "tf_destroy", "terraform", {"destructive": True}),
            (r"^(?:tf\s+validate|validar\s+codigo)(?:\s+no\s+projeto(?:\s+atual)?)?$", "tf_validate", "terraform", {}),
            (r"^(?:tf\s+fmt|formatar\s+codigo)(?:\s+no\s+projeto(?:\s+atual)?)?$", "tf_fmt", "terraform", {}),

            # --- Controle de Versão (Git) ---
            (r"^(?:(?:git\s+)?status|o\s+que\s+mudou)(?:\s+no\s+repo|\s+aqui)?$", "git_status", "git", {}),
            (r"^(?:(?:git\s+)?diff|diferencas|alteracoes)(?:\s+no\s+repo|\s+aqui)?$", "git_diff", "git", {}),
            (r"^(?:(?:git\s+)?log|historico|ultimos\s+commits)(?:\s+do\s+repo|\s+aqui)?$", "git_log", "git", {}),
            (r"^(?:(?:git\s+)?push|enviar\s+codigo|subir\s+alteracoes)(?:\s+pro\s+remote|\s+pro\s+git)?$", "git_push", "git", {"destructive": True}),
            (r"^(?:(?:git\s+)?pull|atualizar\s+repo|baixar\s+alteracoes)(?:\s+do\s+remote|\s+do\s+git)?$", "git_pull", "git", {}),

            # --- Segurança e Auditoria (SecOps) ---
            (r"^(?:revisa|revise|verifique|analise|audite)\s+(?:os\s+)?arquivos\s+(?:\.tf|terraform)(?:\s+com\s+checkov)?$", "checkov", "security", {}),
            (r"^(?:execute|rodar|run)\s+checkov(?:\s+no\s+projeto(?:\s+atual)?)?$", "checkov", "security", {}),
            (r"^(?:execute|rodar|run)\s+tfsec(?:\s+no\s+projeto(?:\s+atual)?)?$", "tfsec", "security", {}),
            (r"^(?:execute|rodar|run)\s+tflint(?:\s+no\s+projeto(?:\s+atual)?)?$", "tflint", "security", {}),
            (r"^(?:execute|rodar|run)\s+trivy(?:\s+no\s+projeto(?:\s+atual)?)?$", "trivy", "security", {}),
            (r"^(?:execute|rodar|run)\s+prowler(?:\s+no\s+projeto(?:\s+atual)?)?$", "prowler", "security", {}),
            (r"^(?:audit|auditoria|scan\s+de\s+seguranca|(?:execute|rodar|run)\s+(?:auditoria|auditoria de seguranca|security audit))(?:\s+no\s+projeto(?:\s+atual)?)?$", "run_security_audit", "security", {}),

            # --- FinOps & Operações (Ops) ---
            (r"^(?:quanto\s+custa|estimativa\s+de\s+custo|infracost|preço)(?:\s+do\s+projeto)?$", "estimate_cost", "ops", {}),
            (r"^(?:detectar\s+drift|verificar\s+drift|drift)(?:\s+na\s+infra)?$", "detect_drift", "ops", {}),
            (r"^(?:rodar\s+pipeline|executar\s+pipeline|ci/cd)(?:\s+agora)?$", "run_pipeline", "ops", {}),
            (r"^(?:aprender|ingestar\s+docs|ler\s+documentacao|atualizar\s+conhecimento)$", "ingest_sources", "ops", {}),
            (r"^(?:treinar\s+ia|consolidar\s+conhecimento)$", "train_knowledge_base", "ops", {}),
            (r"^(?:diagnosticar|analisar\s+sistema|debugar)(?:\s+o\s+projeto)?$", "diagnose_system", "ops", {}),
            (r"^(?:limpar|limpe|clean)\s+(?:o\s+)?cache(?:\s+do\s+projeto|\s+geral)?$", "clean_cache", "ops", {"destructive": True}),

            # --- Pesquisa & Desenvolvimento (Research & Dev) ---
            (r"^(?:pesquise\s+(?:na\s+web\s+)?sobre|google|busque\s+na\s+internet)\s+(?P<query>.*)", "web_search", "research", {}),
            (r"^(?:leia|ler|analise|resuma|conteudo\s+de)\s+(?:a\s+)?(?:url|site|pagina|link)\s+(?P<url>https?://\S+)$", "read_url", "research", {}),
            (r"^(?:gere|crie|escreva)\s+(?:um\s+)?(?:codigo|arquivo)\s+(?:terraform|hcl)\s+(?:para|sobre)\s+(?P<description>.*)", "generate_code", "core", {}),

            # --- Conhecimento e Ajuda (RAG) ---
            (r"^(?:o\s+que\s+(?:é|e)|quais\s+s(?:ã|a)o|me\s+fale\s+sobre|explique|adr|decisoes\s+sobre|como\s+(?:criar|fazer)|regras\s+de|o\s+que\s+sao\s+adrs?)\s*(?P<query>.*)", "access_knowledge", "knowledge", {}),
        ]

    def get_command(self, user_input: str) -> tuple[str, str, dict, bool] | None:
        """
        Verifica se o input do usuário corresponde a alguma regra de reflexo.
        Retorna uma tupla (nome da ferramenta, nome da extensão, argumentos, is_destructive) ou None.
        """
        normalized_input = user_input.lower().strip()
        for rule in self.rules:
            pattern, tool_name, extension, options = rule

            match = re.search(pattern, normalized_input)
            if match:
                # Extract arguments from named capture groups
                args = match.groupdict()

                # Add fixed arguments from options
                fixed_args = options.get("fixed_args", {})
                args.update(fixed_args)

                is_destructive = options.get("destructive", False)

                return tool_name, extension, args, is_destructive
        return None