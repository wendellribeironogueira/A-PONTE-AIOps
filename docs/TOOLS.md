# 🛠️ Catálogo de Ferramentas (FastMCP & Boto3)

Este documento detalha todas as ferramentas ("Tools") disponíveis para os Agentes de IA (Gemini/Ollama) dentro da plataforma A-PONTE.
Estas ferramentas são expostas via **FastMCP** e utilizam **Boto3** para interagir diretamente com a AWS.

>Veja o [Guia de Onboarding](ONBOARDING.md) para uma visão geral de "Quem faz o quê".

## 🧠 Para o Gemini (System Instruction)
> **Como usar este mapa:**
> *   Se o usuário pedir "Liste meus buckets", use `aws_list_buckets`.
> *   Se o usuário pedir "Crie uma infra", use `generate_code`.
> *   Se o usuário pedir "Verifique logs", use `aws_filter_log_events`.
> *   **Nunca** alucine comandos. Use apenas os listados abaixo.

---

## 0. Meta-Ferramentas (Gestão de Extensões)
Ferramentas administrativas para carregar capacidades dinamicamente.

| Ferramenta | Descrição | Quando usar? |
| :--- | :--- | :--- |
| `load_extension` | Carrega um conjunto de ferramentas (ex: `extension='aws'`, `extension='git'`). | **CRÍTICO:** Se você não vir a ferramenta que precisa (ex: `aws_list_buckets`), use isso primeiro. |
| `lookup_tools` | Busca no registro global (Fallback). | **Último Recurso.** Use APENAS se não encontrar a ferramenta no Catálogo Global. |

### ⚡ Estratégia de Lazy Loading (Carregamento sob Demanda)

Para manter o sistema leve e rápido, o A-PONTE não carrega todas as ferramentas na memória inicial. Elas são organizadas em **Extensões** que podem ser carregadas automaticamente pela IA ou solicitadas manualmente pelo analista.

**Dica para o Analista:**
Se você vai iniciar uma sessão de trabalho focada (ex: Auditoria AWS), você pode "aquecer" o ambiente solicitando o carregamento prévio:
> *"Carregue as ferramentas de AWS e Segurança, por favor."*

**Extensões Disponíveis:**
| Extensão | Conteúdo |
| :--- | :--- |
| `aws` | Ferramentas Boto3 (S3, EC2, CloudWatch, Logs, IAM). |
| `git` | Operações de controle de versão (Clone, Status, Diff, Push). |
| `security` | Scanners de segurança (TFSec, Checkov, Prowler). |
| `ops` | Ferramentas de SRE, FinOps e Diagnóstico. |
| `research` | Navegação Web e Ingestão de Conhecimento. |
| `terraform` | Comandos de IaC (Plan, Apply, State). |

---

## 1. ☁️ AWS Operations (Boto3)
**Arquivo Fonte:** `core/services/mcp_aws_reader.py`

Ferramentas de leitura e diagnóstico em tempo real. Projetadas para serem **Read-Only** (seguras) na maioria dos casos.

| Ferramenta | Descrição | Quando usar? |
| :--- | :--- | :--- |
| `aws_list_resources` | Lista recursos AWS (ARNs e Tags) usando Resource Groups Tagging API. | Quando precisar descobrir o que existe na conta sem saber o serviço exato. |
| `aws_list_buckets` | Lista todos os buckets S3. | Para ver armazenamento disponível ou localizar buckets de logs/state. |
| `aws_list_ec2_instances` | Lista instâncias EC2, IPs e status (running/stopped). | Para inventário de servidores ou verificar se uma máquina subiu. |
| `aws_check_cloudtrail` | Verifica se o CloudTrail está ativo e logando. | Auditoria de segurança básica. "Os logs estão ligados?" |
| `aws_list_cloudwatch_alarms` | Lista alarmes em estado `ALARM`. | Para diagnóstico de incidentes. "O que está quebrado agora?" |
| `aws_list_alarm_history` | Busca histórico de mudança de estado de alarmes. | Para post-mortem. "O alarme disparou ontem?" |
| `aws_list_log_groups` | Lista grupos de logs do CloudWatch. | Para encontrar onde os logs da aplicação estão. |
| `aws_filter_log_events` | Busca logs recentes com filtro de texto. | Para investigar erros específicos (ex: "Exception", "Error"). |
| `aws_simulate_principal_policy` | Simula permissões IAM (Policy Simulator). | Troubleshooting de acesso. "Por que o usuário X não consegue acessar Y?" |
| `aws_get_cost_forecast` | Previsão de custos para o próximo mês (Cost Explorer). | Perguntas de FinOps. "Quanto vou gastar?" |

### 📦 Recursos MCP (Resources)
Dados passivos que podem ser lidos como arquivos (URI).
*   `aws://identity`: Quem sou eu? (Account ID, ARN, User).
*   `aws://region`: Em qual região estou operando?
*   `aws://cloudwatch/alarms`: Lista rápida de alarmes ativos em texto.

---

## 2. 🐙 Git Operations
**Arquivo Fonte:** `core/services/mcp_git.py`

Ferramentas para manipulação de código fonte e versionamento.

| Ferramenta | Descrição | Quando usar? |
| :--- | :--- | :--- |
| `git_status` | Mostra arquivos modificados/staged. | Antes de commitar ou para ver o que mudou. |
| `git_diff` | Mostra as diferenças no código. | Para entender o contexto das mudanças atuais. |
| `git_log` | Histórico recente de commits. | "O que foi feito recentemente?" |
| `git_clone` | Clona um repositório remoto. | Setup inicial de projetos. |
| `git_pull` | Atualiza o repositório local. | Sincronizar com o time. |
| `git_commit_push` | Adiciona, commita e envia mudanças (Sync). | Persistir trabalho finalizado. |
| `git_checkout` | Troca de branch ou reverte arquivos. | Navegação entre versões. |

---

## 3. 🏗️ Engineering Engine (Local Coder)
**Arquivo:** `core/tools/local_coder.py`

O motor de geração de código com "Self-Healing".

| Ferramenta | Descrição | Quando usar? |
| :--- | :--- | :--- |
| `generate_code` | Gera ou modifica arquivos (Terraform, Python, Dockerfile). | **Sempre** que precisar criar ou alterar infraestrutura. |
| `fix_code` | Aplica correções em arquivos existentes. | Usado pelo Agente Auditor para corrigir vulnerabilidades. |

**Fluxo de Segurança (O que acontece por trás):**
1.  **Geração:** O LLM cria o rascunho.
2.  **Sandbox:** Salvo em `.aponte-versions/tmp`.
3.  **Validação:** Executa `terraform fmt`, `tflint`, `tfsec`, `checkov`.
4.  **Self-Healing:** Se falhar, a IA corrige (até 3x).
5.  **Entrega:** Só retorna se estiver seguro.

---

## 4. 🧠 Knowledge & System
**Arquivo Fonte:** `core/tools/knowledge_cli.py` e `core/agents/architect.py`

| Ferramenta | Descrição | Quando usar? |
| :--- | :--- | :--- |
| `access_knowledge` | Busca em ADRs, Manifesto e Manuais internos. | Para tirar dúvidas conceituais sobre a plataforma. |
| `web_search` | Busca no Google/DuckDuckGo. | Quando o conhecimento interno não for suficiente (ex: erro novo da AWS). |
| `read_file` | Lê conteúdo de arquivos locais. | Para entender o código existente antes de editar. |
| `list_directory` | Lista arquivos em uma pasta. | Para explorar a estrutura do projeto. |
| `save_file` | Salva conteúdo em disco (bypass do Local Coder). | Para arquivos simples (txt, md, json) que não requerem validação Terraform. |

---

## 5. Infraestrutura de Suporte (Docker)

A execução das ferramentas pesadas ocorre dentro de containers para garantir reprodutibilidade e segurança.

| Container | Função |
| :--- | :--- |
| `mcp-terraform` | Contém binários do Terraform, TFLint, TFSec, Checkov. Garante que a versão das ferramentas seja idêntica para todos os devs. |
| `ollama` | Servidor de inferência local para privacidade de dados. |

---

## 6. 📝 Templates de Raciocínio (Prompts)
Templates pré-definidos que guiam a IA em tarefas complexas.

| Prompt | Descrição |
| :--- | :--- |
| `sre_incident_triage` | Guia de investigação de incidentes (SRE). Coleta identidade, alarmes e logs automaticamente. |