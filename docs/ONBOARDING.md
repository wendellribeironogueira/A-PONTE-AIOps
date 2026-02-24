# 🚀 Guia de Onboarding: O Ecossistema A-PONTE

Bem-vindo ao time! Este documento é o seu mapa para navegar na plataforma. Aqui listamos cada componente do código, explicando sua função e momento de uso.

---

## 🤖 1. A Squad de Agentes (Quem faz o trabalho?)

Estes são os "robôs" com quem você interage via CLI.

| Nome (Arquivo) | O que é? | Pra que serve? | Quando usar? |
| :--- | :--- | :--- | :--- |
| **Architect**<br>`core/agents/architect.py` | O Chatbot Principal e Orquestrador. | É a interface humana do sistema. Ele entende o que você quer, desenha a arquitetura e delega tarefas para ferramentas. | **Sempre.** É o seu ponto de entrada (`aponte architect`) para criar infra, tirar dúvidas ou operar o sistema. |
| **Auditor**<br>`core/agents/auditor.py` | O Inspetor de Segurança (SAST). | Analisa arquivos Terraform (`.tf`) em busca de vulnerabilidades e violações de regras (ex: portas abertas). Possui capacidade de **Auto-Fix**. | Use `aponte audit` antes de abrir um Pull Request ou quando quiser garantir que seu código está seguro. |
| **Sentinel**<br>`core/agents/sentinel.py` | O Vigia (Daemon). | Roda em background monitorando ameaças no CloudTrail e "Drift" (diferença entre código e nuvem). | Use `aponte sentinel` em uma aba separada do terminal para monitoramento contínuo enquanto trabalha. |
| **Observer**<br>`core/agents/cloud_watcher.py` | O Engenheiro de SRE/FinOps. | Monitora logs, alarmes e custos em tempo real. Cruza dados para diagnosticar a saúde do sistema. | Use `aponte observer` (ou `aponte ops`) quando houver um incidente ou para verificar custos. |

---

## 🛠️ 2. Ferramentas MCP (As "Mãos" da IA)

Estas são as ferramentas que os Agentes usam para interagir com o mundo (AWS, Git, Disco). Elas rodam via *Model Context Protocol*.

| Nome (Arquivo) | O que é? | Pra que serve? | Quando usar? |
| :--- | :--- | :--- | :--- |
| **Local Coder**<br>`core/tools/local_coder.py` | Motor de Engenharia (Terraform). | Gera, valida e corrige código Terraform. Roda linters (`tflint`, `tfsec`) automaticamente antes de entregar o código. | **Nunca chame diretamente.** O Agente Architect chama isso quando você pede "Crie um bucket". |
| **AWS Reader**<br>`core/services/mcp_aws_reader.py` | Interface de Leitura AWS (Boto3). | Permite que a IA "veja" a nuvem (listar buckets, ler logs, ver instâncias) sem risco de alterar nada. | Usado pela IA para diagnósticos. Você pode invocar via Architect: "Liste minhas instâncias". |
| **Git Tools**<br>`core/services/mcp_git.py` | Interface Git. | Permite que a IA faça commits, push, pull e leia o histórico do repositório. | Usado pela IA para automação de versionamento ou auditoria de repositório. |
| **Filesystem**<br>`core/services/mcp_filesystem.py` | Interface de Arquivos. | Permite ler (`read_file`) e salvar (`save_file`) arquivos no disco local com segurança. | Usado internamente pela IA para manipular arquivos do projeto. |

---

## ⚙️ 3. Scripts Core & Serviços (O Motor)

Estes são os scripts de "bastidores" que fazem a plataforma funcionar.

| Nome (Arquivo) | O que é? | Pra que serve? | Quando usar? |
| :--- | :--- | :--- | :--- |
| **LLM Gateway**<br>`core/services/llm_gateway.py` | Cliente HTTP de IA. | Conecta o A-PONTE aos provedores de IA (Ollama local ou Google Gemini). Gerencia fallback e retries. | **Automático.** É usado por todos os agentes para "pensar". |
| **Versioning**<br>`core/services/versioning.py` | Sistema de Backup (`.aponte-versions`). | Cria cópias de segurança de qualquer arquivo ANTES que a IA o modifique. Permite rollback. | **Automático.** Sempre que a IA usa `save_file` ou `fix_code`. Você pode usar manualmente via script se necessário. |
| **Knowledge CLI**<br>`core/tools/knowledge_cli.py` | Gestor de Conhecimento (RAG). | Interface para criar ADRs, ingerir documentação da web e treinar o cérebro da IA. | Use `aponte knowledge` para ensinar algo novo à IA ou registrar uma decisão arquitetural. |
| **Docker Wrapper**<br>`cli/internal/utils/docker.go` | Orquestrador de Containers. | Garante que ferramentas pesadas (Terraform, Checkov) rodem isoladas em Docker, não na sua máquina. | **Automático.** A CLI `aponte` usa isso para rodar comandos de infra. |

---

## 📂 4. Estrutura de Pastas (Onde as coisas moram?)

| Diretório | O que tem dentro? |
| :--- | :--- |
| `bin/` | O binário compilado da CLI `aponte` (Go). |
| `cli/` | Código fonte da CLI em Go (Interface do usuário). |
| `core/` | O "cérebro" em Python (Agentes, Ferramentas, Serviços). |
| `core/agents/` | Onde vivem as personas (Architect, Auditor, etc). |
| `core/tools/` | Ferramentas de execução (Local Coder, Knowledge). |
| `core/services/` | Integrações de baixo nível (AWS, Git, LLM). |
| `docs/` | Documentação, ADRs e Base de Conhecimento da IA. |
| `projects/` | Onde ficam os seus projetos Terraform (Tenants). |
| `.aponte-versions/` | Backups automáticos e logs locais. |

---

## 🚦 5. Fluxo de Trabalho Típico (Dia a Dia)

1.  **Start:** `aponte infra up` (Sobe o Docker).
2.  **Trabalho:** `aponte architect` (Pede para criar infra).
3.  **Monitoramento:** `aponte sentinel` (Deixa rodando para segurança).
4.  **Commit:** `aponte audit` (Verifica antes de enviar).
5.  **Deploy:** `aponte ops pipeline` (Validação final e apply).

---

## ⚡ 6. Dicas de Performance (Lazy Loading)

O A-PONTE usa uma estratégia de **Carregamento sob Demanda** para economizar memória e tokens.
*   **O que isso significa?** As ferramentas de AWS, Git e Segurança não estão carregadas quando você abre o chat.
*   **O que acontece?** Na primeira vez que você pede "Liste buckets", a IA vai pausar por 1-2 segundos para carregar a extensão `aws`.
*   **Pro Tip:** Você pode preparar o terreno logo no início: *"Olá, carregue as ferramentas de AWS e Git para mim."*