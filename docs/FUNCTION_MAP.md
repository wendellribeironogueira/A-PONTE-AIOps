# 🗺️ Mapa de Funcionalidades (Menu A-PONTE)

Este documento serve como referência rápida para todas as opções disponíveis no menu interativo da CLI `aponte`.

## 📦 Projetos (Gestão de Contexto)

> **Nota:** Para detalhes técnicos das ferramentas internas usadas pela IA (FastMCP, Boto3), consulte [🛠️ Catálogo de Ferramentas (TOOLS.md)](TOOLS.md).

| Opção | Comando CLI      | Descrição                                             |
| ----- | ---------------- | ----------------------------------------------------- |
| **1** | `project create` | Cria um novo projeto (via CLI Go).                    |
| **2** | `project switch` | Alterna o contexto atual (`.current_project`).        |
| **3** | `repo add`       | Vincula um repositório Git ao projeto.                |
| **4** | `repo remove`    | Remove o vínculo de um repositório.                   |

## 🚀 Operações (Terraform/OpenTofu)

| Opção  | Comando CLI     | Descrição                                              |
| ------ | --------------- | ------------------------------------------------------ |
| **8**  | `tf plan`       | Executa o `plan` no container MCP (Sandbox).           |
| **9**  | `cost estimate` | Gera estimativa de custos via Infracost.               |
| **10** | `deploy project`| Executa o deploy seguro (Terragrunt Apply).            |
| **11** | `tf destroy`    | Destrói todos os recursos do projeto.                  |
| **0**  | -               | Sai do menu.                                           |

## 🐳 Infraestrutura (Docker Management)

| Opção | Comando CLI         | Descrição                                             |
| ----- | ------------------- | ----------------------------------------------------- |
| **I** | `infra up`          | Inicia a stack local (Ollama, MCP, Banco de Dados).   |
| **-** | `infra down`        | Desliga a stack e libera recursos.                    |
| **-** | `infra logs`        | Visualiza logs dos containers de suporte.             |

## 🧠 IA & Desenvolvimento (DevSecOps)

| Opção | Comando CLI           | Descrição                       | Cenário de Uso (Quando usar?)                                                             |
| :---: | --------------------- | ------------------------------- | ----------------------------------------------------------------------------------------- |
| **W** | `ops pipeline`        | **Workflow Pipeline (Full)**    | **O Guardião.** Rode antes de qualquer PR/Merge. Valida integridade, segurança e padrões. |
| **L** | `tf validate`         | **Local Validate**              | **Desenvolvimento.** Valida sintaxe e estrutura local.                                    |
| **G** | `audit --git`         | **Git Audit (O Auditor)**       | **Integração.** Valida repositórios remotos e **injeta padrões (SSM)** automaticamente.   |
| **S** | `audit`               | **Security Advisor (CISO)**     | **Estratégia.** Análise profunda de riscos e plano de ação de segurança.                  |
| **D** | `ai doc`              | **Doc Bot**                     | Quando você termina uma feature e precisa atualizar o README.                             |
| **A** | `architect`           | **Architect Agent**             | **Chat.** Converse com a IA para desenhar infra, gerar policies ou tirar dúvidas.         |
| **V** | `security history`    | **Security History**            | Visualiza histórico de auditoria e vulnerabilidades (DynamoDB).                           |
| **K** | `knowledge`           | **Knowledge Engineer**          | **Ensino.** Menu interativo para criar ADRs, snippets e gerenciar o cérebro da IA.        |

## 🩺 Saúde & Monitoramento (SRE)

| Opção  | Comando CLI    | Descrição            | Cenário de Uso (Quando usar?)                                                        |
| :----: | -------------- | -------------------- | ------------------------------------------------------------------------------------ |
| **12** | `sentinel`     | **Sentinel Daemon**  | **Vigilância.** Monitora Drift, Ameaças (CloudTrail) e Segurança em background.      |
| **5**  | `doctor`       | **AI Doctor**        | **Diagnóstico.** A IA analisa logs e erros de execução recentes.                     |
| **M**  | `observer`     | **Live Monitor**     | **SRE/FinOps.** Acompanha logs, alarmes e custos em tempo real.                      |
| **F**  | `system heal`  | **Fix Tools**        | Se o Checkov/Prowler começar a dar erro de Python/Venv.                              |
| **6**  | `break-glass`  | **Break Glass**      | **Emergência.** Habilita acesso Admin temporário (MFA obrigatório).                  |
| **T**  | `ai train`     | **Train Brain**      | **RAG.** Compila a base de conhecimento e atualiza o modelo da IA.                   |

## 🛠️ Comandos de Apoio (CLI Only)

| Comando CLI             | Descrição                                                                 |
| ----------------------- | ------------------------------------------------------------------------- |
| `aponte project scaffold` | Gera estrutura de arquivos para novos projetos (usado pelo Arquiteto).    |
| `aponte tools sanitize`   | Organiza artefatos gerados pela IA (`req_*.tf`) e backups em pastas limpas.|
| `aponte tools refactor`   | Aplica formatação e linting determinístico antes de chamar a IA.          |
