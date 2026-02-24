# 🎯 Workflow Multi-Projeto - Como Deveria Funcionar

## 📚 Conceito

O A-PONTE suporta **múltiplos projetos isolados** onde cada projeto tem:

- ✅ Backend próprio (S3 + DynamoDB)
- ✅ Repositórios autorizados próprios
- ✅ IAM roles isoladas
- ✅ Recursos taggeados com o nome do projeto

## 🏗️ Estrutura de Arquivos Locais

```
A-PONTE/
├── .bridge_context          # Contexto atual (ex: "ecommerce-prod")
├── a-ponte.repos            # Repos do core
├── a-ponte.auto.tfvars      # Variáveis do core
├── ecommerce-prod.repos     # Repos do projeto 1
├── ecommerce-prod.auto.tfvars
├── analytics-dev.repos      # Repos do projeto 2
├── analytics-dev.auto.tfvars
└── data-lake-staging.repos  # Repos do projeto 3
    data-lake-staging.auto.tfvars
```

## 🔄 Workflow Típico

### 0️⃣ Instalação Global (Opcional, Recomendado)

Para usar o A-PONTE de qualquer lugar do seu terminal (sem precisar entrar na pasta):

```bash
$ cd A-PONTE
$ aponte install
$ source ~/.bashrc  # ou ~/.zshrc
```

Agora você pode usar o comando `aponte`.

### 1️⃣ Setup Inicial (Uma vez)

```bash
# 1. Configurar o core (a-ponte)
$ aponte
# Menu → Opção 8 (Setup A-PONTE)
# Informa: usuario/a-ponte

# 2. Backend criado:
#    - S3: a-ponte-tfstate-bucket
#    - DynamoDB: a-ponte-tf-lock-table
#    - OIDC Provider (global, compartilhado)
```

### 2️⃣ Criar Projeto de E-commerce (Produção)

```bash
# 1. Criar contexto via menu
$ aponte
# Menu → Opção 1 (Criar Novo)
# Digite: ecommerce-prod

# 2. Adicionar repositório
# Menu → Opção 3 (Adicionar Repo)
# Digite: minhaorg/ecommerce-backend

# 3. Deploy
# Menu → Opção 5 (Apply)
# ✅ Infraestrutura provisionada

# 4. Backend criado automaticamente:
#    - S3: ecommerce-prod-tfstate-bucket
#    - DynamoDB: ecommerce-prod-tf-lock-table
#    - IAM Role: ecommerce-prod-github-actions-role
```

### 3️⃣ Criar Projeto de Analytics (Desenvolvimento)

```bash
# 1. Criar contexto
$ aponte
# Menu → Opção 1
# Digite: analytics-dev

# 2. Adicionar repos
# Menu → Opção 3
# Digite: minhaorg/analytics-pipeline
# Digite: minhaorg/analytics-api

# 3. Deploy
# Menu → Opção 5

# Backend criado:
#    - S3: analytics-dev-tfstate-bucket
#    - DynamoDB: analytics-dev-tf-lock-table
#    - IAM Role: analytics-dev-github-actions-role
```

### 4️⃣ Alternar Entre Projetos

```bash
# Ver projetos disponíveis
$ aponte
# Menu → Opção 2 (Alternar Projeto)

# Lista exibida:
#   🏠 a-ponte (1 repositório(s))
#   📂 ecommerce-prod (1 repositório(s))
#   📂 analytics-dev (2 repositório(s))

# Alternar
# Digite: analytics-dev
# ✅ Contexto mudado

# Todas as operações agora afetam apenas analytics-dev:
$ aponte deploy project    # Aplica em analytics-dev
$ aponte tf output   # Mostra outputs de analytics-dev
```

### 5️⃣ Adicionar/Remover Repositórios

```bash
# Contexto atual: ecommerce-prod
$ aponte
# Menu → Opção 3 (Adicionar Repo)
# Digite: minhaorg/ecommerce-frontend

# Arquivo atualizado: ecommerce-prod.repos
# Terraform aplicado automaticamente
# GitHub Secrets sincronizados
```

### 6️⃣ Destruir Projeto de Teste

```bash
# Projeto de teste após experimentação
$ echo "teste-feature-x" > .bridge_context
$ aponte

# Menu → Opção 7 (Destruir Projeto)
# Submenu → Opção 1 (Destruir Infraestrutura)

# ✅ Recursos AWS removidos
# ✅ Arquivos locais mantidos (teste-feature-x.repos)
# ⚠️  Backend (S3/DynamoDB) mantido
```

### 7️⃣ Offboarding Completo

```bash
# Projeto antigo sendo descontinuado
$ echo "legacy-app" > .bridge_context
$ aponte

# Menu → Opção 7
# Submenu → Opção 2 (OFFBOARDING)

# ⚠️  CONFIRMAÇÃO DUPLA
# ✅ Infraestrutura destruída
# ✅ Backend S3/DynamoDB removido
# ✅ Arquivos locais removidos (legacy-app.repos)
```

## 🎨 Convenções de Nomenclatura

### Projetos de Workload

```
<app>-<ambiente>

Exemplos:
✅ ecommerce-prod
✅ ecommerce-staging
✅ ecommerce-dev
✅ analytics-dev
✅ data-lake-staging
✅ api-gateway-prod
```

### Projeto Core

```
✅ a-ponte          # Nome reservado (protegido)
❌ home             # Contexto neutro (navegação)
```

### Repositórios GitHub

```
<org>/<repo>

Exemplos:
✅ minhaorg/ecommerce-backend
✅ minhaorg/analytics-pipeline
✅ minhaorg/a-ponte
❌ ecommerce-backend  # Falta org
❌ minhaorg/         # Falta repo
```

## 🔐 Níveis de Proteção (Automático por Nome)

### a-ponte (Core) - Proteção Máxima

```hcl
prevent_destroy = true   # ✅ Protegido
force_destroy = false    # ✅ Protegido
```

### \*-prod (Produção) - Proteção Padrão

```hcl
prevent_destroy = false  # ⚠️  Destruível (com confirmação)
force_destroy = true     # ✅ Permite limpeza
```

### \*-staging (Homologação) - Proteção Padrão

```hcl
prevent_destroy = false
force_destroy = true
```

### \*-dev (Desenvolvimento) - Proteção Mínima

```hcl
prevent_destroy = false
force_destroy = true     # ✅ Rápida limpeza
```

## 🚫 Anti-Patterns (Não Fazer)

### ❌ Misturar Ambientes no Mesmo Projeto

```bash
# ERRADO
$ echo "ecommerce" > .bridge_context
# Adiciona: minhaorg/ecommerce-prod
# Adiciona: minhaorg/ecommerce-dev
# ❌ Prod e dev no mesmo backend!
```

### ❌ Usar Contexto Home para Deploy

```bash
# ERRADO
$ echo "home" > .bridge_context
$ aponte deploy project
# ❌ Home é neutro, não deve ter recursos
```

### ❌ Nomes Genéricos Sem Ambiente

```bash
# ERRADO
$ echo "ecommerce" > .bridge_context
# ✅ CORRETO: ecommerce-prod ou ecommerce-dev
```

## 🎯 Mapeamento de Recursos AWS

### Projeto: ecommerce-prod

```
AWS Resources:
├── S3
│   ├── ecommerce-prod-tfstate-bucket (Backend)
│   ├── ecommerce-prod-audit-logs
│   └── ecommerce-prod-<custom-buckets>
├── DynamoDB
│   └── ecommerce-prod-tf-lock-table (Backend)
├── IAM
│   ├── ecommerce-prod-github-actions-role
│   ├── ecommerce-prod-infra-boundary (Policy)
│   └── ecommerce-prod-devops-policy-*
├── EC2
│   └── Tags: Project=ecommerce-prod
└── CloudWatch
    └── ecommerce-prod-*
```

### Projeto: analytics-dev

```
AWS Resources:
├── S3
│   ├── analytics-dev-tfstate-bucket (Backend)
│   ├── analytics-dev-audit-logs
│   └── analytics-dev-<custom-buckets>
├── DynamoDB
│   └── analytics-dev-tf-lock-table (Backend)
├── IAM
│   ├── analytics-dev-github-actions-role
│   ├── analytics-dev-infra-boundary
│   └── analytics-dev-devops-policy-*
└── ...
```

## 🔄 Sincronização GitHub Secrets

Cada projeto sincroniza seus próprios secrets:

```bash
# Contexto: ecommerce-prod
$ aponte setup github

# Sincroniza em: minhaorg/ecommerce-backend
AWS_ROLE_TO_ASSUME       = arn:aws:iam::123:role/ecommerce-prod-github-actions-role
PERMISSIONS_BOUNDARY_ARN = arn:aws:iam::123:policy/ecommerce-prod-infra-boundary
PROJECT_NAME             = ecommerce-prod
AWS_REGION               = sa-east-1
```

```bash
# Contexto: analytics-dev
$ aponte setup github

# Sincroniza em: minhaorg/analytics-pipeline E minhaorg/analytics-api
AWS_ROLE_TO_ASSUME       = arn:aws:iam::123:role/analytics-dev-github-actions-role
PERMISSIONS_BOUNDARY_ARN = arn:aws:iam::123:policy/analytics-dev-infra-boundary
PROJECT_NAME             = analytics-dev
AWS_REGION               = sa-east-1
```

## 📊 Dashboard de Múltiplos Projetos

```bash
$ aponte info

===============================================================
   📊 A-PONTE - Dashboard
===============================================================

☁️  AWS:
   Conta:   123456789012
   User:    admin
   Região:  sa-east-1

📂 Projeto Atual: ecommerce-prod
   Proteção: 🟢 PADRÃO (Workload)

🔑 Outputs Críticos:
   github_actions_role_arn       = "arn:aws:iam::123:role/ecommerce-prod-github-actions-role"
   permissions_boundary_arn      = "arn:aws:iam::123:policy/ecommerce-prod-infra-boundary"

===============================================================
```

## 🧪 Testes de Isolamento

```bash
# 1. Criar dois projetos
$ echo "projeto-a" > .bridge_context && aponte deploy project
$ echo "projeto-b" > .bridge_context && aponte deploy project

# 2. Verificar isolamento no AWS Console
# ✅ projeto-a-tfstate-bucket ≠ projeto-b-tfstate-bucket
# ✅ projeto-a-github-actions-role ≠ projeto-b-github-actions-role

# 3. Destruir projeto-a
$ echo "projeto-a" > .bridge_context
$ aponte tf destroy

# 4. Verificar que projeto-b não foi afetado
$ echo "projeto-b" > .bridge_context
$ aponte tf output
# ✅ Recursos intactos
```

## 🎓 Casos de Uso Reais

### Caso 1: Startup com Múltiplos Apps

```
Projetos:
├── landing-page-prod
├── api-backend-prod
├── api-backend-staging
├── analytics-dev
└── a-ponte (core)

Repositórios Totais: 6
Backends Isolados: 5 (cada projeto tem o seu)
OIDC Provider: 1 (compartilhado via a-ponte)
```

### Caso 2: Empresa com Ambientes Separados

```
Projetos:
├── ecommerce-prod
├── ecommerce-staging
├── ecommerce-dev
├── crm-prod
├── crm-dev
└── a-ponte

Repositórios Totais: 8
Backends Isolados: 6
Convenção: <app>-<ambiente>
```

## 📝 Checklist de Boas Práticas

- [ ] ✅ Nome do projeto inclui ambiente (`-prod`, `-dev`)
- [ ] ✅ Cada projeto tem arquivo `.repos` próprio
- [ ] ✅ Backend é criado automaticamente (não manual)
- [ ] ✅ Contexto `home` é usado apenas para navegação
- [ ] ✅ Contexto `a-ponte` nunca é destruído
- [ ] ✅ Repositórios seguem padrão `org/repo`
- [ ] ✅ GitHub Secrets são sincronizados por projeto
- [ ] ✅ Tags AWS incluem `Project=<nome>`

---

**Conclusão**: O A-PONTE já tem a arquitetura correta. Precisamos apenas:

1. Remover proteções hardcoded que impedem destroy legítimo
2. Melhorar UX para indicar nível de proteção
3. Facilitar navegação entre projetos

Não precisamos de feature flags de ambiente - o nome do projeto JÁ faz isso!
