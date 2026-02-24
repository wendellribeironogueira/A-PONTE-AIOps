# 🚪 Escape Hatches - A-PONTE

## 🆘 Quando Usar

Use estas rotas de emergência quando:

- Precisar destruir um projeto que está bloqueado
- Tiver recursos órfãos que o Terraform não consegue gerenciar
- Precisar limpar tudo e recomeçar
- Estiver em ambiente de desenvolvimento/testes

## ⚠️ NUNCA USE EM PRODUÇÃO SEM APROVAÇÃO

---

## 🔓 Escape Hatch #1: Remover Proteção de Destroy

### Problema

```
Error: Instance cannot be destroyed
│ Resource has lifecycle.prevent_destroy set
```

### Solução Temporária

```bash
# 1. Desabilita proteção TEMPORARIAMENTE
sed -i 's/prevent_destroy = true/prevent_destroy = false/g' terraform/storage.tf
sed -i 's/prevent_destroy = true/prevent_destroy = false/g' terraform/iam.tf

# 2. Aplica destroy
aponte tf destroy

# 3. IMPORTANTE: Restaura proteções (git)
git checkout terraform/storage.tf terraform/iam.tf
```

### Solução Permanente (Feature Flag)

Adicione no `terraform.tfvars` ou via env:

```hcl
enable_destroy_protection = false # APENAS PARA DEV/TEST
```

---

## 🔓 Escape Hatch #2: Limpar Projeto "Preso" no Contexto Home

### Problema

```
❌ Erro: O contexto 'home' é neutro e não permite X
```

### Solução

```bash
# Force o contexto para qualquer projeto
echo "meu-projeto-teste" > .bridge_context

# OU crie um contexto de limpeza
echo "cleanup-temp" > .bridge_context
touch cleanup-temp.repos

# Execute a operação bloqueada
aponte tf destroy
```

---

## 🔓 Escape Hatch #3: Destruir Projeto a-ponte (Core)

### Problema

O projeto `a-ponte` tem proteções extras por ser Core.

### Solução CUIDADOSA

```bash
# 1. Muda o contexto
echo "a-ponte" > .bridge_context

# 2. Remove flag que impede destroy
export TF_VAR_is_aponte="false"
export TF_VAR_create_global_resources="false"

# 3. Desabilita proteções
sed -i 's/prevent_destroy = true/prevent_destroy = false/g' terraform/*.tf

# 4. Destroy
terragrunt destroy -auto-approve

# 5. Limpa backend manualmente
aws s3 rb s3://a-ponte-tfstate-bucket --force
aws dynamodb delete-table --table-name a-ponte-tf-lock-table

# 6. Restaura arquivos
git checkout terraform/
```

---

## 🔓 Escape Hatch #4: Limpar Dependências Bloqueadas

### Problema

```
Error: Error deleting IAM Policy: DeleteConflict
```

### Solução

```bash
# Script de limpeza forçada (DANGEROUS)
PROJECT_NAME="meu-projeto"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Remove todas as roles do projeto
aws iam list-roles --query "Roles[?starts_with(RoleName, '${PROJECT_NAME}-')].RoleName" \
  --output text | xargs -I {} aws iam delete-role --role-name {}

# Remove policies órfãs
aws iam list-policies --scope Local \
  --query "Policies[?starts_with(PolicyName, '${PROJECT_NAME}-')].Arn" \
  --output text | xargs -I {} aws iam delete-policy --policy-arn {}
```

---

## 🔓 Escape Hatch #5: Reset Total (Última Opção)

### Quando Usar

- Tudo deu errado
- Recursos órfãos por toda parte
- Estado corrompido

### Solução Nuclear 💣

```bash
#!/bin/bash
# ESTE SCRIPT DELETA TUDO. USE COM EXTREMA CAUTELA.

PROJECT_NAME="seu-projeto"
REGION="sa-east-1"

echo "🚨 INICIANDO LIMPEZA NUCLEAR DO PROJETO: $PROJECT_NAME"
echo "⏰ Você tem 10 segundos para Ctrl+C cancelar..."
sleep 10

# 1. Tenta destroy normal
echo "a-ponte" > .bridge_context
terragrunt destroy -auto-approve || echo "Falha no destroy, continuando..."

# 2. Nuke IAM
echo "🧹 Limpando IAM..."
for role in $(aws iam list-roles --query "Roles[?contains(RoleName, '$PROJECT_NAME')].RoleName" --output text); do
  aws iam delete-role --role-name "$role" 2>/dev/null || true
done

# 3. Nuke S3
echo "🧹 Limpando S3..."
for bucket in $(aws s3api list-buckets --query "Buckets[?contains(Name, '$PROJECT_NAME')].Name" --output text); do
  aws s3 rb "s3://$bucket" --force 2>/dev/null || true
done

# 4. Nuke DynamoDB
echo "🧹 Limpando DynamoDB..."
for table in $(aws dynamodb list-tables --query "TableNames[?contains(@, '$PROJECT_NAME')]" --output text); do
  aws dynamodb delete-table --table-name "$table" 2>/dev/null || true
done

# 5. Limpa arquivos locais
echo "🧹 Limpando arquivos locais..."
rm -rf .terragrunt-cache .terraform
rm -f ${PROJECT_NAME}.repos ${PROJECT_NAME}.auto.tfvars
echo "home" > .bridge_context

echo "✅ Limpeza nuclear concluída."
echo "⚠️  Verifique o Console AWS manualmente para confirmar."
```

---

## 🛡️ Recomendações de Segurança

### Para Desenvolvimento

```hcl
# Adicione no terraform.tfvars (GIT IGNORE)
environment = "dev"
enable_destroy_protection = false
enable_break_glass = true
```

### Para Produção

```hcl
# Hardcode no código (Commit)
lifecycle {
  prevent_destroy = true
}

variable "enable_destroy_protection" {
  type    = bool
  default = true
  validation {
    condition     = var.enable_destroy_protection == true
    error_message = "PRODUÇÃO: Destroy protection deve estar ATIVADA. Use 'aponte project detach' se necessário."
  }
}
```

---

## 📋 Checklist Pós-Escape

Após usar um Escape Hatch:

- [ ] ✅ Restaurei arquivos modificados via `git checkout`
- [ ] ✅ Verifiquei recursos órfãos no Console AWS
- [ ] ✅ Documentei o motivo do uso do escape hatch
- [ ] ✅ Revisei as proteções para evitar repetição
- [ ] ✅ Alterei contexto para `home` (`echo "home" > .bridge_context`)

---

## 🔐 Feature Flags Recomendadas

Adicione ao `variables.tf`:

```hcl
variable "enable_destroy_protection" {
  description = "Habilita lifecycle.prevent_destroy em recursos críticos"
  type        = bool
  default     = true # PRODUÇÃO
}

variable "environment" {
  description = "Ambiente (dev/staging/prod)"
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Ambiente deve ser: dev, staging ou prod."
  }
}

# No código:
lifecycle {
  prevent_destroy = var.enable_destroy_protection
}
```

---

## 🆘 Último Recurso: AWS Nuke

Se TUDO falhar:

```bash
# Instale: https://github.com/rebuy-de/aws-nuke
brew install aws-nuke

# Configure nuke-config.yml
cat > nuke-config.yml <<EOF
regions:
  - sa-east-1

account-blocklist:
  - "999999999999" # Sua conta de PRODUÇÃO

accounts:
  "123456789012": # Sua conta DEV
    filters:
      IAMRole:
        - type: contains
          value: "a-ponte"
      S3Bucket:
        - type: contains
          value: "a-ponte"
EOF

# EXECUTE COM CUIDADO
aws-nuke -c nuke-config.yml --profile dev --no-dry-run
```

---

## 📞 Suporte

Se nenhum escape hatch funcionar:

1. Abra uma issue no GitHub com logs completos
2. Compartilhe o `terragrunt state list` e `aws sts get-caller-identity`
3. Marque com label `emergency`

**Lembre-se**: Escape hatches são para emergências. Use com responsabilidade.
