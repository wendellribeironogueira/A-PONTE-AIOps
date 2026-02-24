# 🛡️ Arquitetura de Segurança (Safety Nets)

A segurança no A-PONTE não é apenas uma "feature", é a base da arquitetura. Analisando o código fonte (`core/agents/auditor.py` e `core/tools/local_coder.py`), documentamos as seguintes camadas de proteção ativas.

## 1. O Mantra de Versionamento (ADR-018)
**Implementação:** `core/services/versioning.py`

Nenhum agente de IA tem permissão para sobrescrever um arquivo do usuário sem antes criar um backup.
*   **Como funciona:** Antes de qualquer escrita (`write_text`), o sistema copia o arquivo original para `.aponte-versions/<timestamp>_<filename>`.
*   **Auditabilidade:** O ID da versão de backup é registrado no log de auditoria (DynamoDB).

## 2. Validação "Fail Closed"
**Implementação:** `core/tools/local_coder.py`

Diferente de assistentes de código comuns que sugerem código "quebrado", o A-PONTE adota uma postura estrita:
*   Se os scanners de segurança (`tfsec`, `checkov`) falharem e a IA não conseguir corrigir, o código **não é retornado**.
*   O sistema prefere não entregar nada a entregar uma infraestrutura vulnerável.

## 3. Diretivas de Segurança Injetadas (System Prompts)
**Implementação:** `core/agents/auditor.py` (Variável `SECURITY_DIRECTIVE`)

Todo prompt enviado ao LLM carrega um "Preâmbulo Constitucional" que a IA é forçada a obedecer:
1.  **Least Privilege:** Proibido `0.0.0.0/0` em portas administrativas (22, 3389).
2.  **Encryption:** Obrigatório uso de `AES256` ou `aws:kms` em S3/RDS/EBS.
3.  **Data Sovereignty:** Foco exclusivo em AWS (ignora alucinações de Azure/GCP).
4.  **Multi-Tenant:** Uso obrigatório de variáveis (`var.project_name`) para nomenclatura de recursos.

## 4. Isolamento de Contexto (ADR-027)
**Implementação:** `cli/internal/utils/docker.go` e Scripts Python

*   **Memória Volátil:** O contexto do projeto (`project_name`) é injetado via variáveis de ambiente (`TF_VAR_project_name`) a cada execução.
*   **Prevenção de Cross-Talk:** O menu interativo sempre reseta para "home" ao iniciar, impedindo que um comando `destroy` seja executado no projeto errado por engano.

## 5. Auditoria Imutável
**Implementação:** `core/agents/auditor.py` -> `_save_audit_event`

Todas as ações críticas e diagnósticos são persistidos em dois locais:
1.  **Local:** Arquivos JSONL em `logs/security_audit.jsonl` (com rotação e lock de arquivo para concorrência).
2.  **Remoto:** Tabela DynamoDB `a-ponte-ai-history` (com TTL de 90 dias).

Isso garante rastreabilidade total: *"Quem pediu esse bucket público? Foi o usuário ou a IA?"*

## 6. Sandboxing de Execução (MCP)

As ferramentas que alteram estado ou executam binários complexos rodam dentro do container `mcp-terraform`.
*   **Benefício:** Se a IA for induzida a rodar um comando malicioso (`rm -rf /`), o dano fica contido no container Docker, protegendo o host do desenvolvedor.
*   **Network:** O container de execução não possui credenciais AWS permanentes; elas são injetadas temporariamente apenas durante a execução da tarefa.