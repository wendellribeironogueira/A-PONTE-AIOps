# 🔍 Troubleshooting & Resolução de Problemas

Este documento centraliza soluções para erros comuns encontrados durante o uso da plataforma A-PONTE.

## 🏗️ Terraform & Infraestrutura (Drift)

### Erro: `EntityAlreadyExists` ou `ResourceAlreadyExists`

**Sintoma:**
Durante o `bootstrap` ou `apply`, o Terraform falha informando que um recurso já existe, mas ele não consta no arquivo de estado (`tfstate`).

```text
Error: creating SSM Parameter (...): ParameterAlreadyExists: ...
Error: creating Log Group (...): ResourceAlreadyExistsException: ...
```

**Causa:**
Isso geralmente acontece quando:
1. O recurso foi criado manualmente via Console AWS.
2. Uma execução anterior do Terraform criou o recurso mas falhou ao salvar o arquivo de estado (S3).
3. O recurso é um "Singleton" global (ex: Security Hub) que já estava ativo na conta.

**Solução (Importação):**
Você deve importar o recurso existente para o estado do Terraform para que ele possa ser gerenciado.

**Comando Genérico:**
```bash
terraform import <ENDERECO_DO_RECURSO_NO_TF> <ID_DO_RECURSO_NA_AWS>
```

**Exemplos Práticos (Bootstrap):**

1. **SSM Parameters:**
   ```bash
   terraform import module.security.aws_ssm_parameter.registry_table_name /a-ponte/global/dynamodb/registry_table_name
   ```

2. **CloudWatch Log Groups:**
   ```bash
   terraform import 'module.observability.aws_cloudwatch_log_group.cloudtrail[0]' /aws/cloudtrail/a-ponte
   ```

3. **IAM OIDC Provider:**
   ```bash
   # O ID é a URL sem o protocolo https://
   terraform import module.global.aws_iam_openid_connect_provider.github token.actions.githubusercontent.com
   ```

4. **AWS Budgets:**
   ```bash
   # O ID é <ACCOUNT_ID>:<BUDGET_NAME>
   terraform import module.governance.aws_budgets_budget.cost_budget 123456789012:a-ponte-monthly-budget
   ```

---

## 🔐 Bloqueios (Locks)

### Erro: `Error acquiring the state lock`

**Sintoma:**
O Terraform informa que o estado está bloqueado por outra operação.

**Solução:**
Se você tem certeza que não há outra execução em andamento:
1. Copie o `LockID` exibido na mensagem de erro.
2. Execute:
   ```bash
   terraform force-unlock <LOCK_ID>
   ```

---

## 🤖 Agentes de IA

### Erro: `Connection refused` ou `Docker not found`

**Sintoma:**
O Agente Arquiteto não consegue executar comandos Terraform ou Git.

**Solução:**
1. Verifique se o Docker está rodando.
2. Reinicie os containers de suporte:
   ```bash
   aponte infra up
   ```
