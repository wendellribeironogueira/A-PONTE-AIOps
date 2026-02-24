# Architecture Decision Records (ADR) - A-PONTE Governance Platform

Este documento registra as decisões arquiteturais significativas tomadas no desenvolvimento do projeto **A-PONTE Governance Platform**. O objetivo é fornecer contexto e justificativa para as escolhas técnicas, servindo como guia para contribuidores e usuários, garantindo que o projeto mantenha seus padrões de segurança e governança.

## Índice

1. [ADR-001: Federação de Identidade via OIDC](#adr-001-federação-de-identidade-via-oidc)
2. [ADR-002: Governança via IAM Permissions Boundary](#adr-002-governança-via-iam-permissions-boundary)
3. [ADR-003: Orquestração No-Code (Terragrunt + CLI)](#adr-003-orquestração-no-code-terragrunt-cli)
4. [ADR-004: Deploy Seguro via AWS Systems Manager (No-SSH)](#adr-004-deploy-seguro-via-aws-systems-manager-no-ssh)
5. [ADR-006: Monitoramento Ativo de Segurança](#adr-006-monitoramento-ativo-de-segurança)
6. [ADR-007: Acesso de Suporte Emergencial (Break Glass)](#adr-007-acesso-de-suporte-emergencial-break-glass)
7. [ADR-008: Registro Centralizado de Projetos (DynamoDB)](#adr-008-registro-centralizado-de-projetos-dynamodb)
8. [ADR-009: Estado Terraform Centralizado (Shared Bucket)](#adr-009-estado-terraform-centralizado-shared-bucket)
9. [ADR-010: Execução Remota (GitOps via GitHub Actions)](#adr-010-execução-remota-gitops-via-github-actions)
10. [ADR-011: CLI Global (Wrapper de Sistema)](#adr-011-cli-global-wrapper-de-sistema)
11. [ADR-012: Migração para CLI Estruturada (Go)](#adr-012-migração-para-cli-estruturada-go)
12. [ADR-013: Controle de Concorrência no Cliente (Client-Side Rate Limiting)](#adr-013-controle-de-concorrência-no-cliente-client-side-rate-limiting)
13. [ADR-014: Estratégia de Ferramental Híbrido (Go + Python)](#adr-014-estratégia-de-ferramental-híbrido-go--python)
14. [ADR-015: Service Discovery e Configuração (SSM Parameter Store)](#adr-015-service-discovery-e-configuração-ssm-parameter-store)
15. [ADR-016: Integração de AI Ops (Ollama + DynamoDB)](#adr-016-integração-de-ai-ops-ollama--dynamodb)
16. [ADR-017: Pipeline de Validação Unificado (Pragmatismo com IA)](#adr-017-pipeline-de-validação-unificado-pragmatismo-com-ia)
17. [ADR-018: Mantra de Versionamento e Persistência (Safety Nets)](#adr-018-mantra-de-versionamento-e-persistência-safety-nets)
18. [ADR-019: Hardening de Dependências (Strict Pinning)](#adr-019-hardening-de-dependências-strict-pinning)
19. [ADR-020: Engenharia de Conhecimento Local (RAG Offline)](#adr-020-engenharia-de-conhecimento-local-rag-offline)
20. [ADR-021: Gerenciamento de Recursos Just-in-Time (Lifecycle AI)](#adr-021-gerenciamento-de-recursos-just-in-time-lifecycle-ai)
21. [ADR-022: Auditoria Contextual (App vs Infra)](#adr-022-auditoria-contextual-app-vs-infra)
22. [ADR-023: Observabilidade via TUI (Textual)](#adr-023-observabilidade-via-tui-textual)
23. [ADR-024: Interface de Linguagem Natural para AWS CLI (Cloud Watcher)](#adr-024-interface-de-linguagem-natural-para-aws-cli-cloud-watcher)
24. [ADR-025: Dashboards de Observabilidade Nativos (CloudWatch)](#adr-025-dashboards-de-observabilidade-nativos-cloudwatch)
25. [ADR-026: Evolução Cognitiva dos Agentes (Few-Shot & Memória)](#adr-026-evolução-cognitiva-dos-agentes-few-shot--memória)
27. [ADR-027: Isolamento de Contexto via Override de Memória](#adr-027-isolamento-de-contexto-via-override-de-memória)
28. [ADR-028: Adoção do Model Context Protocol (MCP)](#adr-028-adoção-do-model-context-protocol-mcp)

---

## ADR-001: Federação de Identidade via OIDC

### Status

Aceito

### Contexto

Para que o GitHub Actions possa provisionar infraestrutura na AWS, ele precisa de credenciais. A abordagem tradicional envolve criar um Usuário IAM, gerar Access Keys de longa duração e armazená-las nos Secrets do GitHub. Isso apresenta riscos de segurança significativos (vazamento de chaves, dificuldade de rotação).

### Decisão

Utilizar **OpenID Connect (OIDC)** para federar a identidade do GitHub Actions diretamente com a AWS.

### Consequências

- **Positivas:** Elimina a necessidade de chaves de acesso de longa duração. A AWS emite tokens temporários apenas para a execução do workflow. Aumenta drasticamente a segurança e simplifica a gestão de credenciais.
- **Negativas:** Requer configuração inicial de um Identity Provider na AWS (automatizado pela CLI/Terragrunt).

---

## ADR-002: Governança via IAM Permissions Boundary

### Status

Aceito

### Contexto

A Role utilizada pelo CI/CD precisa de permissões amplas para criar recursos (EC2, S3, VPC). No entanto, se essa Role for comprometida ou mal configurada, ela poderia ser usada para criar um usuário "Admin" e tomar controle total da conta (Escalação de Privilégio).

### Decisão

Anexar uma **Permissions Boundary** a todas as Roles criadas pelo sistema, incluindo a Role do próprio CI/CD. A política deve impor **Boundary Propagation**, garantindo que `iam:CreateRole` e `iam:PutRolePermissionsBoundary` só sejam permitidos se o novo recurso também tiver o Boundary anexado.
**Nota Técnica:** A implementação deve utilizar a Condition Key `iam:PermissionsBoundary` com `StringEquals` nas políticas de IAM para forçar esta restrição no momento da criação da Role.

### Consequências

- **Positivas:** Define um "teto máximo" de permissões. Mesmo que a Role tenha `AdministratorAccess`, ela não pode realizar ações bloqueadas pelo Boundary (ex: criar usuários IAM, remover logs de auditoria, alterar o próprio Boundary).
- **Negativas:** Aumenta a complexidade das políticas de IAM. Requer que toda criação de Role inclua explicitamente o Boundary.

---

## ADR-003: Orquestração No-Code (Terragrunt + CLI)

### Status

Atualizado (Substitui "Bootstrap Híbrido")

### Contexto

A versão anterior utilizava um script Python customizado (`the_bridge.py`) para gerenciar o bootstrap e a orquestração. Isso gerava dívida técnica, duplicação de lógica de validação e dependência de runtime Python.

### Decisão

Adotar **Terragrunt** para gerenciamento nativo de backend/estado e **CLI A-PONTE** para orquestração de comandos. O Terragrunt gerencia automaticamente a criação do Bucket S3 e DynamoDB Lock Table se não existirem, eliminando a necessidade de scripts de bootstrap imperativos.

**Nota de Imutabilidade:** A infraestrutura de Backend (S3 + DynamoDB) é agnóstica ao tipo de carga de trabalho (`infra_cloud`). O mesmo backend suporta projetos `web_server`, `web_file` ou `monitoramento` sem necessidade de reconfiguração, garantindo que a camada de persistência de estado seja estável e desacoplada da aplicação.

### Consequências

- **Positivas:** Redução drástica de código (Zero Python). Validação nativa via HCL. Menor superfície de manutenção. Uso de ferramentas padrão de mercado.
- **Negativas:** Curva de aprendizado inicial do Terragrunt para novos membros.

---

## ADR-004: Deploy Seguro via AWS Systems Manager (No-SSH)

### Status

Aceito

### Contexto

O acesso a servidores EC2 para deploy de aplicações geralmente é feito via SSH (Porta 22). Isso exige gerenciamento de chaves SSH (`.pem`), exposição de portas para a internet (ou uso de Bastion Hosts) e rotação de chaves.

### Decisão

Utilizar o **AWS Systems Manager (SSM) Run Command** para orquestrar deploys e o **Session Manager** para acesso interativo.

### Consequências

- **Positivas:** A porta 22 pode permanecer fechada no Security Group. Não há chaves SSH para gerenciar ou vazar. Todas as sessões e comandos são auditados no CloudTrail e S3.
- **Negativas:** Exige que o Agente SSM esteja instalado e rodando nas instâncias (padrão na Amazon Linux 2/2023).

---

## ADR-006: Monitoramento Ativo de Segurança

### Status

Aceito

### Contexto

Apenas registrar logs (CloudTrail) não é suficiente; é necessário reagir a eventos críticos em tempo real para evitar danos maiores.

### Decisão

Implementar **AWS Config** para conformidade contínua e **CloudWatch Alarms** integrados ao **SNS** para notificação imediata de atividades suspeitas (ex: chamadas de API não autorizadas).

### Consequências

- **Positivas:** Reduz o tempo de resposta a incidentes (MTTR). Garante que desvios de configuração (ex: bucket público) sejam detectados.
- **Negativas:** Pode gerar ruído (alert fatigue) se os limiares de alarme não forem bem ajustados.

---

## ADR-007: Acesso de Suporte Emergencial (Break Glass)

### Status

Aceito

### Contexto

Embora a automação via CI/CD seja o padrão, existem cenários de "situações adversas" (ex: deadlock no Terraform, falha no OIDC, incidente de segurança) que exigem intervenção humana direta. É necessário um mecanismo de acesso administrativo que não comprometa a estrutura de governança (Permissions Boundary).

### Decisão

Implementar uma Role de IAM dedicada para **Suporte/Break-Glass** com as seguintes características:

1.  **Isolamento por Projeto:** A Role deve ser nomeada dinamicamente (ex: `${project_name}-SupportBreakGlassRole`) para evitar conflitos globais na conta e garantir que o acesso emergencial seja restrito ao escopo do projeto específico.
2.  **MFA Obrigatório:** A política de confiança (Trust Relationship) deve exigir `aws:MultiFactorAuthPresent: true`.
3.  **Conformidade com Boundary:** A Role **deve** ter o Permissions Boundary anexado (ADR-002). O suporte deve operar _dentro_ do teto de vidro.
4.  **Auditoria Ativa:** O uso desta Role deve ser monitorado com alertas de alta prioridade (SNS).

### Consequências

- **Positivas:** Garante recuperabilidade do ambiente sem abrir mão da segurança. Mantém o princípio de "Nenhum Humano tem acesso direto" exceto em emergências auditadas.
- **Negativas:** Adiciona um vetor de ataque que precisa ser protegido com MFA e monitoramento rigoroso.

### Atualização (v2.0): Server-Side Expiration

Para mitigar o risco de sessões de emergência esquecidas (caso a máquina do operador seja desligada), o agendamento de revogação foi migrado para o **AWS EventBridge Scheduler**.
- Ao ativar o Break Glass, a CLI cria um agendamento único (One-Time) na AWS.
- O Scheduler invoca uma Lambda de limpeza (`break_glass_cleanup`) que marca a sessão como expirada no DynamoDB e registra o evento.

### Break Glass Local (CLI Overrides)

Além da Role IAM, a CLI possui guardrails lógicos implementados em Python (`scripts/guardrails.py`). Em casos extremos onde a automação falha, estes podem ser contornados via variáveis de ambiente explícitas:

- `ALLOW_PRODUCTION_DESTROY=true`: Permite destruir projetos marcados como produção.
- `ALLOW_APONTE_MODIFICATIONS=true`: Permite alterar o projeto core `a-ponte`.
- `FORCE_NON_INTERACTIVE=true`: Permite operações destrutivas sem confirmação de TTY (uso em CI/CD).
  **Risco Crítico:** O uso dessas variáveis deve ser restrito e monitorado. Recomenda-se configurar alertas no CloudWatch Logs para detectar a injeção destas variáveis em tempo de execução, pois elas anulam proteções de segurança padrão.

---

## ADR-008: Registro Centralizado de Projetos (DynamoDB)

### Status

Implementado (Módulo Identity)

### Contexto

Atualmente, a lista de projetos e repositórios vinculados é mantida em arquivos planos locais (`.repos`, `.project.yml`) versionados no Git. Em equipes grandes, a criação simultânea de projetos ou adição de repositórios gera conflitos de merge frequentes no arquivo de controle, prejudicando a experiência do desenvolvedor (DX).

### Decisão

Migrar o armazenamento de metadados de projetos (existência, configuração, repositórios vinculados) para uma tabela **DynamoDB Global** (`a-ponte-registry`).

**Atualização (Refatoração):** A tabela é provisionada pelo módulo `@terraform/modules/identity` e serve como fonte da verdade para sessões e locks, garantindo que nenhum estado permaneça na máquina local do analista. O isolamento é garantido via `project_name` (Multi-tenant).

### Padrão de Acesso Híbrido (Cache Local)

Embora o DynamoDB seja a autoridade, os scripts de orquestração em Python (`scripts/*.py`) utilizam arquivos locais (`.project.yml`) gerados no momento da criação/sincronização como um **Cache de Leitura**.

- **Motivo:** Performance (evita latência de rede em verificações rápidas de guardrails) e resiliência (permite validações básicas offline).
- **Sincronia:** O comando `aponte project sync` é responsável por manter o arquivo local alinhado com o DynamoDB.

### Consequências

- **Positivas:**
  - **Single Source of Truth:** O estado dos projetos é global e imediato.
  - **Zero Conflitos:** Operações atômicas no banco de dados eliminam conflitos de git merge para metadados.
  - **Escalabilidade:** Suporta centenas de analistas operando simultaneamente.
- **Negativas:**
  - **Dependência Online:** Requer acesso à AWS para listar ou criar projetos (não funciona offline).

---

## ADR-009: Estado Terraform Centralizado (Shared Bucket)

### Status

Aceito (Estratégia de Consolidação)

### Contexto

A criação de um Bucket S3 e uma Tabela DynamoDB para cada projeto (`<project>-tfstate`) gera proliferação de recursos, atingindo rapidamente os limites da conta AWS (Soft Limit de 100 buckets) e dificultando a auditoria centralizada. O bootstrap inicial estava criando buckets com nome `home-tfstate` devido à falta de contexto explícito.

### Decisão

Utilizar um **Bucket S3 Compartilhado** (`a-ponte-tfstate-core`) para armazenar o estado de todos os projetos, segregados por chaves (Prefixos).

- **Estrutura de Chaves:** `s3://a-ponte-tfstate-core/{project_name}/terraform.tfstate`
- **Lock Table:** Uma única tabela DynamoDB (`a-ponte-lock-table`) com Partition Key baseada no `LockID` (que contém o caminho do estado).

### Consequências

- **Positivas:** Redução drástica de recursos (1 Bucket vs N Buckets). Centralização de logs de acesso e políticas de criptografia. Elimina o problema de "buckets órfãos" ou nomes incorretos como `home-`.
- **Negativas:** Requer políticas de IAM rigorosas (Condition Keys) para garantir que o Projeto A não possa ler/escrever no estado do Projeto B dentro do mesmo bucket.

---

## ADR-011: CLI Global (Wrapper de Sistema)

### Status

Aceito ✅ (Atualizado - Migrado para CLI Go)

### Contexto

Para utilizar a plataforma, o engenheiro precisa navegar até o diretório do projeto e executar comandos via scripts. Isso cria fricção no fluxo de trabalho, especialmente quando se está trabalhando em múltiplos diretórios ou apenas consultando o estado do sistema. Ferramentas de plataforma devem parecer nativas do sistema operacional.

### Decisão

Implementar um comando de instalação (`aponte install`) na CLI Go que instala o binário `aponte` globalmente no sistema (via `$PATH`). O binário compilado pode ser executado de qualquer diretório, permitindo acesso onipresente à ferramenta.

### Consequências

- **Positivas:**
  - **DX (Developer Experience):** Acesso onipresente à ferramenta (ex: `aponte project list` de qualquer pasta).
  - **Abstração:** O usuário deixa de pensar em "rodar scripts" e passa a usar uma "CLI nativa".
  - **Performance:** Binário compilado oferece startup instantâneo.
- **Negativas:**
  - **Instalação:** Requer um passo de instalação manual (`aponte install`) na máquina do desenvolvedor.
  - **Compilação:** Requer Go instalado para compilar o binário (`go build`).

---

## ADR-012: Migração para CLI Estruturada (Go)

### Status

Aceito ✅ (Concluído - 2024)

### Contexto

O crescimento da plataforma resultou em uma coleção complexa de scripts Bash (`scripts/*.sh`). A manutenção tornou-se difícil, o tratamento de erros é frágil e a dependência de ferramentas de sistema (`jq`, `sed`, `aws-cli`) cria inconsistências entre ambientes de desenvolvedores.

### Decisão

Desenvolver uma nova CLI compilada utilizando a linguagem **Go**. A CLI substituirá gradualmente os scripts Bash. Utilizaremos a biblioteca `Cobra` para estrutura de comandos e o `AWS SDK for Go v2` para interações com a nuvem.

### Implementação

A migração foi concluída com sucesso em 2024. Todos os 18 comandos principais foram migrados para a CLI Go (`aponte`), localizada em `cli/`. Scripts Python (`scripts/`) foram mantidos para orquestração e menu interativo, seguindo a estratégia híbrida definida no ADR-014.

### Consequências

- **Positivas:** Binário único estático (fácil distribuição), tipagem forte, performance superior, melhor tratamento de erros, facilidade de testes unitários. Migração completa realizada sem impacto operacional.
- **Negativas:** Necessidade de conhecimento em Go pela equipe de manutenção. Requer compilação do binário (`go build`) antes do uso.

---

## ADR-013: Controle de Concorrência no Cliente (Client-Side Rate Limiting)

### Status

Aceito

### Contexto

A tabela central de registro de projetos (`a-ponte-registry`) no DynamoDB é um recurso compartilhado crítico. Em cenários de migração em massa ou operações em lote via CLI, existe o risco de atingir os limites de escrita (WCU) do modo _On-Demand_ (1000 WCU iniciais) ou causar _throttling_, impactando outros usuários. Aumentar a capacidade provisionada seria custoso e desnecessário para picos esporádicos.

### Decisão

Adotar uma abordagem de **Pragmatismo Arquitetural** implementando o controle de fluxo no lado do cliente:

1.  **CLI Go (`aponte`):** Utilizaremos o padrão **Worker Pool** em Go para limitar explicitamente o número de goroutines simultâneas (ex: 20 workers) que realizam escritas no banco.
2.  **Scripts Python (`ia_ops`):** Utilizaremos o modo de retry **`adaptive`** do `boto3` (AWS SDK). Este modo implementa **Exponential Backoff com Jitter** automaticamente ao receber erros de _Throttling_ ou _ProvisionedThroughputExceeded_, garantindo que scripts de auditoria e IA operem suavemente mesmo no Free Tier.

### Consequências

- **Positivas:**
  - **Resiliência:** Garante que a aplicação nunca exceda os limites físicos da tabela, independentemente do volume de dados.
  - **Custo-Eficiência:** Permite manter o DynamoDB em modo `PAY_PER_REQUEST` sem desperdício financeiro.
  - **Estabilidade:** Scripts de IA não falham silenciosamente sob carga.
- **Negativas:**
  - **Latência:** Operações podem demorar mais para completar durante picos de carga devido às esperas de retry.

---

## ADR-014: Estratégia de Ferramental Híbrido (Go + Python)

### Status

Aceito

### Contexto

A migração completa para Go (ADR-012) é um esforço de longo prazo. Scripts de orquestração, validação e menus (`menu.sh`, `guardrails.sh`) ainda estão em Bash, com problemas de manutenibilidade, testabilidade e robustez. A CLI Go é ideal para comandos de núcleo e operações de alta performance, mas Python oferece maior agilidade e um ecossistema de bibliotecas mais rico para scripts de "cola" e lógica de negócios complexa que não pertence ao binário principal.

### Decisão

Adotar uma estratégia de ferramental híbrida:

1.  **CLI Go (`aponte`):** Focada em comandos de núcleo, interações com a API e operações de alta performance (ex: `migrate-registry`).
2.  **Scripts Python:** Substituir os scripts Bash (`*.sh`) por scripts Python para lógica de orquestração, validações (guardrails), menus interativos e tarefas de automação. Python oferece bibliotecas robustas (`rich`, `typer`, `boto3`) e melhor manutenibilidade que Bash.

### Filosofia: O Cérebro e o Construtor

A arquitetura segue o padrão "Mestre de Obras (Python) e Construtor (Terraform)":

- **O Cérebro (Python):** Agentes de IA (`architect.py`, `doctor.py`) e scripts de orquestração decidem _o que_ deve ser feito, validam pré-condições, injetam variáveis de contexto e tratam erros complexos.
- **O Construtor (Terraform/HCL):** Executa a mudança de estado de forma determinística e segura.

### Consequências

- **Positivas:** Acelera a modernização do ferramental, aproveitando a força de cada linguagem. Python é mais legível e testável que Bash. Permite a criação de interfaces de usuário mais ricas (TUI com `rich` ou `textual`).
- **Negativas:** Introduz Python como uma dependência de desenvolvimento, ao lado de Go. Requer uma fronteira clara entre o que vai para a CLI Go e o que fica em scripts Python.

---

## ADR-015: Service Discovery e Configuração (SSM Parameter Store)

### Status

Aceito

### Contexto

Aplicações modernas precisam descobrir onde estão seus recursos (Banco de Dados, Redis, APIs) dinamicamente. Hardcodar endpoints no código ou passar via variáveis de ambiente estáticas no CI/CD cria acoplamento forte e riscos de segurança.

### Decisão

Utilizar o **AWS Systems Manager (SSM) Parameter Store** como a "Fonte da Verdade" para configuração e descoberta de serviço.

1.  **Taxonomia Obrigatória:** Todos os parâmetros devem seguir o padrão:
    `/{project_name}/{environment}/{service_name}/{key}`
    - Ex: `/ecommerce-prod/production/database/master_password`
    - Ex: `/ecommerce-prod/production/backend/db_host`

2.  **Contrato Infra-App:**
    - **Infra (Produtor):** Módulos Terraform DEVEM criar recursos `aws_ssm_parameter` para exportar endpoints, ARNs e credenciais geradas.
    - **App (Consumidor):** Aplicações DEVEM ler esses parâmetros em tempo de execução (via SDK ou injeção no container), nunca esperando valores hardcoded.

### Consequências

- **Positivas:** Criptografia em repouso (AWS Managed), auditoria de acesso, rotação facilitada e custo reduzido comparado ao Secrets Manager.
- **Negativas:** Requer que a Role IAM da aplicação (Instance Profile) tenha permissão explícita `ssm:GetParameter` para o path do projeto.

---

## ADR-016: Integração de AI Ops (Ollama + DynamoDB)

### Status

Aceito

### Contexto

A operação de uma plataforma multi-tenant gera um volume alto de logs e erros complexos. A análise manual é lenta. Ferramentas de IA Generativa podem acelerar o diagnóstico, mas o envio de logs sensíveis para APIs públicas (OpenAI/Anthropic) representa risco de vazamento de dados. Além disso, o histórico de diagnósticos precisa ser compartilhado entre analistas.

### Decisão

1.  **Inferência Local (Ollama):** Utilizar modelos LLM locais (ex: Llama 3) via Ollama para processar diagnósticos e gerar código. Isso garante que dados sensíveis de infraestrutura nunca saiam da rede do analista (Data Sovereignty).
2.  **Memória Compartilhada (DynamoDB):** Armazenar o histórico de diagnósticos e interações da IA na tabela `a-ponte-ai-history`. Isso permite que o aprendizado de um erro ocorrido com o Analista A seja visível para o Analista B.
3.  **Security Boundaries (System Prompts):** Injetar diretrizes de segurança imutáveis (Hardcoded Security Directives) em todos os prompts para impedir que a IA sugira configurações inseguras (ex: `AdministratorAccess`).
4.  **RAG Lite (Retrieval-Augmented Generation):** O sistema utiliza a memória compartilhada para buscar soluções de erros similares passados e injetá-las no contexto da IA, criando um ciclo de aprendizado contínuo.

### Capacidades Expandidas (Agentes)

O ecossistema de IA foi expandido para incluir agentes especializados:

- **Chaos Monkey (`chaos_monkey.py`):** Validação de resiliência via injeção de falhas.
- **Cloud Watcher (`cloud_watcher.py`):** Observabilidade ativa conectada ao diagnóstico de IA.

### Contexto Semântico do Projeto (Variáveis de Negócio)

Para aumentar a acurácia diagnóstica em ambientes multi-tenant, a IA deve identificar e correlacionar as seguintes variáveis presentes no estado do Terraform ou Tags de recursos:

- **`ProjectName` (ID):** Identificador único do tenant (ex: `ecommerce-prod`).
- **`app_name`:** Nome da aplicação agnóstica ao ambiente (ex: `ecommerce`). Útil para correlacionar erros lógicos de aplicação.
- **`resource_name`:** **(Nome do Componente):** Define o nome lógico para o principal recurso a ser criado (ex: `web-server`, `assets-bucket`, `main-db`). A IA usa isso para gerar nomes de recursos Terraform consistentes (ex: `aws_s3_bucket.assets-bucket`).
- **`environment`:** Identifica o Ambiente de deploy:(dev / prod)

### Consequências

- **Positivas:** Privacidade total de dados (Local), colaboração em equipe (DynamoDB) e segurança by-design (Prompts).
- **Negativas:** Requer hardware capaz de rodar LLMs locais na máquina do analista.

---

### Schema do DynamoDB

A tabela `a-ponte-registry` terá a seguinte estrutura:

- **Partition Key (PK):** `ProjectName` (String) - Nome único do projeto.
- **Atributos:**
  - `Environment` (String): `dev`, `prod`.
  - `IsProduction` (Boolean): Flag de proteção.
  - `CreatedAt` (String): Timestamp ISO 8601.
  - `CreatedBy` (String): Usuário/ARN que criou.
  - `Repositories` (Set/List of Strings): Lista de repositórios vinculados (`user/repo`).
  - `Status` (String): `ACTIVE`, `ARCHIVED`.
  - `AppName` (String): Nome da aplicação agnóstica ao ambiente (ex: `ecommerce`).
  - `ResourceName` (String): Nome do componente principal (ex: `web-server`).

#### Exemplo de Item JSON:

```json
{
  "ProjectName": { "S": "ecommerce-prod" },
  "Environment": { "S": "prod" },
  "Repositories": { "SS": ["org/frontend", "org/backend"] },
  "AppName": { "S": "ecommerce" },
  "ResourceName": { "S": "web-server" }
}
```

## ADR-018: Mantra de Versionamento e Persistência (Safety Nets)

### Status

Aceito

### Contexto

Com a introdução de agentes de IA que modificam código (`git_auditor`, `doc_bot`, `security_auditor`), o risco de alterações indesejadas ou destrutivas aumentou. Confiar apenas no Git não é suficiente para uma experiência de desenvolvimento segura ("Safety Net"), pois o usuário pode não ter commitado o estado anterior.

### Decisão

Implementar um **Mantra de Versionamento e Persistência** em todas as ferramentas de IA:

1.  **Versionamento Local (`.aponte-versions/`):** NENHUM arquivo deve ser sobrescrito por um agente de IA sem antes ser copiado para uma pasta de versionamento local com timestamp. Isso permite rollback imediato sem depender do Git.
2.  **Persistência de Memória (`DynamoDB`):** Todas as decisões, diagnósticos e eventos de auditoria gerados pela IA devem ser persistidos no DynamoDB (`a-ponte-ai-history`) para auditoria e aprendizado coletivo.
3.  **Sandbox de Validação:** Código gerado deve ser validado sintaticamente (ex: `terraform fmt`) antes de ser apresentado ou salvo.

### Consequências

- **Positivas:** Segurança psicológica para o operador (Undo/Rollback sempre disponível). Rastreabilidade total das ações da IA.
- **Negativas:** Aumento do uso de disco local (`.aponte-versions`). Necessidade de limpeza periódica (Comando `clean`).

---

## ADR-019: Hardening de Dependências (Strict Pinning)

### Status

Aceito

### Contexto

A cadeia de suprimentos de software (Supply Chain) é um vetor de ataque crítico. Dependências definidas com intervalos abertos (ex: `boto3>=1.26.0`) podem introduzir vulnerabilidades ou quebrar a aplicação se uma nova versão for lançada com bugs ou malware. Ferramentas de lock complexas (`poetry`, `pipenv`) adicionam fricção ao desenvolvimento em ambientes frugais.

### Decisão

Adotar **Strict Pinning** (Versionamento Exato) no arquivo `requirements.txt` para todas as dependências de produção e teste.

- Exemplo: `boto3==1.34.0` em vez de `boto3>=1.34.0`.

### Consequências

- **Positivas:**
  - **Reprodutibilidade:** O ambiente de execução é idêntico em todas as máquinas e no CI/CD.
  - **Segurança:** Previne a instalação automática de versões maliciosas ou quebradas.
  - **Simplicidade:** Mantém o uso do `pip` padrão sem ferramentas adicionais.
- **Negativas:**
  - **Manutenção:** Exige atualização manual periódica das versões para receber patches de segurança e features.

---

## ADR-020: Engenharia de Conhecimento Local (RAG Offline)

### Status

Aceito

### Contexto

A plataforma A-PONTE possui regras específicas de arquitetura e segurança que modelos genéricos (DeepSeek, Llama) desconhecem. Além disso, a documentação da AWS muda frequentemente. Precisamos de um mecanismo para "ensinar" a IA sobre o contexto do projeto e novas tecnologias sem enviar dados sensíveis para APIs externas (OpenAI/Anthropic), mantendo a soberania dos dados.

### Decisão

Implementar um fluxo de **Engenharia de Conhecimento Local**:

1.  **Ingestão:** Ferramentas CLI (`core/tools/knowledge_cli.py`) e Agente Pesquisador (`core/services/knowledge/researcher.py`) para capturar ADRs, snippets de texto e páginas Web (HTML limpo).
2.  **Armazenamento:** Arquivos Markdown estruturados em `docs/knowledge_base/` e `docs/adrs/`.
3.  **Brain as Code:** O script `core/services/knowledge/trainer.py` (via `aponte ai train`) gera um arquivo `config/ai/aponte-ai.modelfile` que contém toda a definição da memória da IA. Este arquivo é versionado no Git, permitindo que qualquer desenvolvedor reproduza o cérebro exato executando o setup.

### Consequências

- **Positivas:**
  - **Soberania:** Nenhum dado sai da máquina do engenheiro.
  - **Especialização:** A IA torna-se especialista nas regras do A-PONTE.
  - **Portabilidade:** O conhecimento é transferível via Git sem binários pesados.
  - **Offline:** O conhecimento Web é "baixado" e fica disponível sem internet.
- **Negativas:**
  - **Processo Manual:** Requer execução explícita do treinamento (`aponte ai train`) após adicionar novos conhecimentos.

---

## ADR-023: Observabilidade via TUI (Textual)

### Status

Aceito

### Contexto

Ferramentas de observabilidade tradicionais (Grafana, Datadog) exigem infraestrutura dedicada, autenticação complexa e saída do contexto do terminal. Para operações de "Dia-2" e diagnósticos rápidos na máquina do desenvolvedor, a troca de contexto entre Terminal e Browser gera fricção.

### Decisão

Adotar a biblioteca **Textual** (Python) para construir interfaces de usuário baseadas em texto (TUI) ricas e interativas diretamente no terminal. O **Centro de Comando (Dashboard)** deve agregar métricas locais (Docker), nuvem (AWS CloudWatch/Budgets) e segurança (Nativa) em uma única tela.

### Consequências

- **Positivas:**
  - **Zero Infra:** Roda localmente usando as credenciais da sessão atual.
  - **Foco:** O engenheiro não precisa sair do terminal.
  - **Performance:** Interface leve e responsiva via protocolo SSH ou local.
- **Negativas:**
  - **Dependência:** Adiciona `textual` ao `requirements.txt`.
  - **Compatibilidade:** Requer terminais modernos com suporte a cores e unicode (embora tenha fallback).

---

## ADR-021: Gerenciamento de Recursos Just-in-Time (Lifecycle AI)

### Status

Aceito

### Contexto

A execução de LLMs locais (Ollama) consome recursos significativos de RAM e VRAM. Em hardware limitado (ex: Laptops com 16GB RAM), manter o servidor de inferência rodando continuamente degrada a performance do sistema operacional e de outras ferramentas de desenvolvimento.

### Decisão

Implementar um ciclo de vida **Just-in-Time** para o serviço de IA. Os scripts Python (`llm_client.py`) são responsáveis por:
Implementar um ciclo de vida **Just-in-Time** para o serviço de IA. Os scripts Python (`core/services/llm_gateway.py`) são responsáveis por:

1.  **Start:** Verificar se o Ollama está rodando e iniciá-lo em background apenas quando uma tarefa de IA é solicitada.
2.  **Stop:** Matar o processo do Ollama imediatamente após a conclusão da tarefa (auditoria, chat ou geração de código).

### Consequências

- **Positivas:** Liberação imediata de memória RAM após o uso. Permite o uso de modelos mais pesados (ex: 7B/8B) em máquinas modestas, pois o recurso é alocado exclusivamente durante a inferência.
- **Negativas:** Latência de "Cold Start" (alguns segundos) ao iniciar novas tarefas.

---

## ADR-022: Auditoria Contextual (App vs Infra)

### Status

Aceito

### Contexto

A plataforma A-PONTE é focada em Infraestrutura e Governança. Tentar corrigir código de aplicação (Python, Java, Node.js) via IA consome muitos tokens, gera alucinações frequentes e foge do escopo do projeto.

### Decisão

O agente de auditoria (`git_auditor.py`) deve distinguir o tipo de repositório e adaptar seu comportamento:
O agente de auditoria (`core/tools/git_auditor.py`) deve distinguir o tipo de repositório e adaptar seu comportamento:

1.  **Repositórios de Infra (Terraform/HCL):** Foco em validação de sintaxe, segurança, conformidade com ADRs e **Auto-Fix** (correção automática de código).
2.  **Repositórios de App (Código de Negócio):** Foco estrito em **Análise de Requisitos**. A IA não deve corrigir o código fonte, mas sim ler o código para entender a stack (ex: "Precisa de Redis e Postgres") e **gerar o código Terraform** correspondente para suportar a aplicação na AWS.

### Consequências

- **Positivas:** Economia de tokens, redução de risco de quebrar lógica de negócio, foco na geração de valor (Infraestrutura como Código).
- **Negativas:** O desenvolvedor continua responsável por corrigir bugs na aplicação sem ajuda da IA da plataforma.

---

## ADR-024: Agente de Observabilidade e Diagnóstico (Observer)

### Status

Aceito (Evoluído)

### Contexto

A AWS CLI é poderosa mas verbosa. Operadores frequentemente precisam consultar o estado da infraestrutura, logs e custos, mas perdem tempo consultando a documentação da sintaxe CLI ou filtrando JSONs complexos.

### Decisão

Implementar o agente **Observer** (`core/agents/cloud_watcher.py`) que atua como um especialista em SRE e FinOps.

1.  **Integração MCP:** Utiliza o `mcp_aws_reader.py` para acessar CloudWatch (Alarmes e Logs), CloudTrail e Cost Explorer de forma segura.
2.  **Diagnóstico Ativo:** Cruza informações de logs e métricas para identificar causa raiz de problemas.
3.  **FinOps:** Monitora custos e sugere otimizações baseadas em dados reais.

### Consequências

 - **Positivas:** Visão holística da saúde do sistema (Logs + Métricas + Custo). Redução de fricção operacional. Segurança garantida por execução em sandbox (MCP).
 - **Negativas:** Dependência da disponibilidade do LLM local e do container MCP.

---

## ADR-025: Dashboards de Observabilidade Nativos (CloudWatch)

### Status

Aceito

### Contexto

Embora a CLI e TUI sejam úteis para desenvolvedores, a visualização de métricas históricas e correlação de eventos exige gráficos visuais acessíveis via navegador, especialmente para stakeholders e auditoria.

### Decisão

Provisionar Dashboards do CloudWatch automaticamente via Terraform (`module.observability`).

1.  **Dashboard Principal:** Criado por projeto (`${project_name}-main-dashboard`).
2.  **Widgets Padronizados:** Incluir métricas críticas de segurança (Uso de Root, Violação de Integridade CloudTrail) por padrão.

### Consequências

- **Positivas:** Visibilidade imediata pós-deploy ("Zero Config"). Link direto gerado no output do Terraform.
- **Negativas:** Custo adicional do CloudWatch Dashboard ($3/dashboard/mês).

---

## ADR-026: Evolução Cognitiva dos Agentes (Few-Shot & Memória)

### Status

Aceito

### Contexto

Os agentes de IA (Arquiteto, Auditor, Cloud Watcher) apresentavam dificuldades em seguir formatos estritos de comandos CLI e perdiam o contexto de aprendizado ao encerrar a sessão. A segurança (Allowlists) estava restritiva demais, bloqueando operações legítimas de diagnóstico por falta de exemplos claros no prompt.

### Decisão

1.  **Few-Shot Learning:** Implementar exemplos práticos ("Few-Shot") nos prompts de sistema de todos os agentes, demonstrando explicitamente situações de sucesso, erro e bloqueio de segurança. Isso reduz alucinações de sintaxe.
2.  **Memória de Sessão & Auto-Train:** O Agente Arquiteto agora persiste o histórico da conversa em `docs/knowledge_base/chat_sessions/` ao encerrar e dispara automaticamente o retreinamento do modelo (`aponte ai train`), consolidando o aprendizado de curto prazo em longo prazo (Long-Term Memory).
3.  **Refinamento de Permissões:** Expansão das _Allowlists_ de ferramentas e verbos (ex: `lookup-` e `filter-` no Cloud Watcher) para permitir diagnósticos profundos sem comprometer a segurança de escrita (Read-Only).

### Consequências

- **Positivas:** Aumento drástico na assertividade dos comandos gerados. O sistema aprende organicamente com o uso diário, sem necessidade de curadoria manual constante. Redução de falsos positivos nos guardrails de segurança.
- **Negativas:** O processo de `auto-train` na saída pode adicionar alguns segundos ao encerramento da CLI.

---

## ADR-027: Isolamento de Contexto via Override de Memória

### Status

Aceito

### Contexto

Em um ambiente multi-tenant local, a persistência do "último projeto acessado" em arquivos (`.current_project`) criava um risco de segurança: ao abrir o menu interativo, o usuário poderia disparar acidentalmente operações no projeto anterior (ex: `destroy`) antes de perceber que o contexto não havia sido resetado.

### Decisão

Implementar uma estratégia de **Isolamento de Contexto via Memória (In-Memory Override)**:

1.  **Hierarquia de Verdade:** A leitura do contexto deve obedecer estritamente à ordem: `Variável de Ambiente (TF_VAR_project_name)` > `Arquivo em Disco (.current_project)` > `Default ("home")`.
2.  **Injeção no Wrapper:** O comando de entrada `aponte` (sem argumentos) injeta `TF_VAR_project_name="home"` apenas na memória do processo do menu, forçando um estado neutro visual e lógico.
3.  **Limpeza Higiênica:** Ao encerrar a sessão interativa, o sistema reseta o arquivo físico para "home", garantindo que o estado de repouso da ferramenta seja sempre neutro e stateless.
4.  **Isolamento por Sessão (Session ID):** O arquivo de persistência em disco agora inclui o usuário e o ID da sessão (PID do Shell), no formato `.current_project.<user>.<session_id>`. Isso previne condições de corrida entre múltiplos terminais do mesmo usuário (Alice vs Alice).

### Consequências

- **Positivas:** Elimina a possibilidade de "Deploy Fantasma" (interface mostrando um projeto e backend executando em outro). Garante que toda sessão inicie limpa (Safety by Design).
- **Negativas:** Requer que o wrapper do shell (`install.go`) seja a única porta de entrada oficial para garantir a injeção das variáveis.

---

## ADR-028: Adoção do Model Context Protocol (MCP)

### Status

Aceito

### Contexto

Atualmente, os agentes do A-PONTE gastam muitos tokens e processamento da IA para "alucinar" a sintaxe correta de comandos CLI e fazer o parsing de saídas JSON. Além disso, a execução direta de subprocessos no host representa um risco de segurança.

### Decisão

Adotar o **Model Context Protocol (MCP)** com uma **Estratégia Híbrida de Execução**:

1.  **Separação de Responsabilidades:**
    - **O Cérebro (A-PONTE/LLM):** Foca puramente em **Intenção e Orquestração**. Ele decide *o que* fazer e *qual* ferramenta chamar, mantendo o contexto do negócio e os Guardrails de segurança.
    - **As Mãos (Executores):**
        - **Container (Isolamento):** Ferramentas que exigem runtime controlado e determinístico (Terraform, Terragrunt, Linters) rodam no container `mcp-terraform`. O binário `git` é mantido para resolução de módulos, mas sem credenciais.
        - **Host (Autenticação):** Ferramentas que dependem de credenciais de usuário complexas (Git Push/Commit com SSH/GPG, AWS CLI com SSO/MFA) rodam no Host via wrappers Python (`mcp_git.py`, `mcp_aws_reader.py`) para aproveitar a sessão autenticada do engenheiro.

2.  **Fluxo de Execução:**
    - O LLM envia uma mensagem JSON estruturada (Tool Call).
    - O Agente (`architect.py`) decide se despacha para o Docker (Terraform) ou executa localmente (Git/AWS), abstraindo essa complexidade da IA.

### Consequências

- **Fluxo de Integração (Ollama + MCP):**
  - **Ollama (Model):** Cérebro que decide *quando* usar uma ferramenta.
  - **Bridge (ArchitectAgent):** Orquestrador que conecta o modelo aos servidores MCP, injetando esquemas e executando chamadas.
  - **Servidores MCP:** Definição padronizada das ferramentas (Python) expostas via protocolo MCP (ex: FastMCP).

- **Positivas:**
  - **Eficiência:** O LLM não precisa mais ser treinado na sintaxe exata de cada ferramenta.
  - **Segurança:** A execução acontece dentro de containers isolados (Sandboxing), não no host do usuário.
  - **Extensibilidade:** Adicionar suporte a Kubernetes ou Azure torna-se tão simples quanto subir um novo container MCP, sem escrever código Python.
  - **Usabilidade (DX):** Elimina a necessidade de montar sockets SSH ou credenciais AWS dentro do container, reduzindo a superfície de ataque e simplificando o setup.
- **Negativas:**
  - **Dependência:** Aumenta a dependência do Docker para funcionamento dos agentes.
  - **Refatoração:** Exigirá a reescrita gradual dos agentes atuais (`core/agents/`) para consumirem o protocolo MCP em vez de `subprocess`.

---

## ADR-029: Refatoração da Squad de Agentes (Especialização)

### Status

Aceito

### Contexto

O crescimento orgânico das funcionalidades resultou em sobreposição de responsabilidades. O Agente Sentinel acumulava funções de segurança e aprendizado (web scraping). O Agente Cloud Watcher era limitado.

### Decisão

Reorganizar os agentes com responsabilidades únicas e claras (SQUAD):

1.  **Architect (Design):** Foco em interação humana e geração de Terraform via `mcp-terraform`.
2.  **Auditor (Compliance):** Foco em análise estática (SAST) de arquivos. Não acessa nuvem.
3.  **Sentinel (Runtime Security):** Foco estrito em Drift Detection e Intrusion Detection. Perde capacidade de aprendizado web.
4.  **Observer (Health):** Foco em Observabilidade, Logs e FinOps. Absorve capacidades de diagnóstico.
5.  **Researcher (Knowledge):** Novo serviço dedicado a RAG, ingestão de docs e treinamento de modelo, desacoplado da operação de segurança.

### Consequências

- **Positivas:** Separação de interesses (SoC), maior segurança, clareza no fluxo de desenvolvimento.
- **Negativas:** Necessidade de refatoração dos scripts existentes.
```

```
