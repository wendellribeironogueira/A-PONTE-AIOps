# 🤖 A Squad de Agentes (AI Team)

A plataforma A-PONTE não opera com um único "bot", mas sim com uma **Squad de Agentes Especializados** (ADR-029). Cada agente possui um escopo de responsabilidade, ferramentas específicas e um "perfil psicológico" (System Prompt) ajustado para sua função.

## 1. Architect Agent (O Arquiteto)
* **Comando:** `aponte architect`
* **Arquivo Fonte:** `core/agents/architect.py`
* **Função:** Interface primária com o usuário, design de soluções e orquestração.
* **Cérebro:** Híbrido (Gemini 2.5 Flash para raciocínio + Ollama para execução).

### Capacidades:
- **Entrevista Contextual:** Deduz variáveis de projeto (`project_name`, `environment`) antes de iniciar o trabalho.
- **Orquestração MCP:** Decide qual ferramenta chamar (ex: "Preciso ler logs" -> chama `aws_reader`).
- **Memória de Longo Prazo:** Acessa ADRs e documentação via RAG para tomar decisões arquiteturais embasadas.

---

## 2. Auditor Agent (O Inspetor)
* **Comando:** `aponte audit`
* **Arquivo Fonte:** `core/agents/auditor.py`
* **Função:** Análise Estática de Segurança (SAST), Compliance e Auto-Correção.

### Fluxo de Trabalho (Code Analysis):
1.  **Higiene:** Formata o código (`terraform fmt`).
2.  **Scan Determinístico:** Executa `checkov`, `tfsec` e `tflint`. Se estas ferramentas aprovarem, o LLM nem é acionado (Economia de Tokens).
3.  **Análise Cognitiva:** Se houver dúvidas ou complexidade, o LLM analisa o código buscando falhas lógicas que ferramentas estáticas perdem.
4.  **Auto-Fix:** Se autorizado, reescreve o código inseguro aplicando correções (ex: Adicionar criptografia AES256 em S3).

**Diferencial:** Possui a diretiva `SECURITY_DIRECTIVE` injetada no prompt, proibindo estritamente `0.0.0.0/0` em portas de gestão e exigindo criptografia.

---

## 3. Observer Agent (O Observador)
* **Comando:** `aponte ops` (ou via Architect)
* **Arquivo Fonte:** `core/agents/cloud_watcher.py`
* **Função:** SRE, Observabilidade e FinOps.

### Capacidades:
- **Diagnóstico de Causa Raiz:** Cruza logs do CloudTrail com Alarmes do CloudWatch.
- **FinOps:** Analisa custos via AWS Cost Explorer e sugere otimizações (ex: "Mude de gp2 para gp3").
- **Health Check:** Verifica a saúde dos containers Docker e serviços locais.

**⚠️ Dependências de Infraestrutura (Contrato .tf vs .py):**
Para que o Observer funcione, seu código Terraform deve criar:
1.  **Alarmes:** CloudWatch Alarms com nomes iniciando por `${var.project_name}-...`.
2.  **Logs:** Um Log Group chamado `aws-cloudtrail-logs-${var.project_name}` (ou ajuste o código do agente).

---

## 4. Sentinel Agent (O Vigia)
* **Comando:** `aponte sentinel`
* **Arquivo Fonte:** `core/agents/sentinel.py`
* **Função:** Daemon de segurança em tempo real (Runtime Security).

### Capacidades:
- **Drift Detection:** Alerta se a infraestrutura real divergiu do código Terraform.
- **Threat Detection:** Monitora eventos críticos no CloudTrail (ex: Login de Root, Desativação de Logs).
- **Race to Process:** Usa DynamoDB Locking para garantir que apenas uma instância do Sentinela processe um alerta em times distribuídos.

**🔍 O que ele vigia (Hardcoded Events):**
O Sentinel monitora ativamente os seguintes eventos no CloudTrail sem necessidade de configuração extra:
- **Acesso:** `ConsoleLogin` (Root), `CreateUser`, `CreateAccessKey`.
- **Rede:** `AuthorizeSecurityGroupIngress`, `CreateVpc`, `CreateLoadBalancer`.
- **Computação:** `RunInstances` (EC2), `CreateFunction2` (Lambda).
- **Dados & Auditoria:** `CreateBucket`, `DeleteTrail`, `StopLogging`.

---

## 5. Researcher Agent (O Pesquisador)
* **Comando:** `aponte ai train`
* **Arquivo Fonte:** `core/services/knowledge/researcher.py`
* **Função:** Engenharia de Conhecimento e Aprendizado Contínuo.

### Capacidades:
- **Web Crawling:** Navega na documentação da AWS/HashiCorp para aprender novas sintaxes.
- **Knowledge Base:** Compila aprendizados em arquivos Markdown para o RAG.
- **Model Training:** Gera arquivos `Modelfile` para atualizar o "cérebro" local do Ollama.