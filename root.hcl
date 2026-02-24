# =================================================================================
# A-PONTE: Configuração Enterprise do Terragrunt
# =================================================================================
# Substitui a lógica manual de bootstrap do Python.
# Responsável por:
# 1. Criar Bucket S3 e Tabela DynamoDB automaticamente
# 2. Gerar arquivo backend.tf
# 3. Gerenciar State Locking e Criptografia
# =================================================================================

remote_state {
  backend = "s3"

  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }

  config = {
    # Nome dinâmico baseado em variáveis de ambiente injetadas pela CLI
    # SANITIZAÇÃO: Removidos defaults inseguros ("a-ponte") para garantir Fail Fast se ENV estiver ausente.
    # MUDANÇA (ADR-009): Bucket Centralizado para evitar limite de 100 buckets da AWS
    bucket         = "a-ponte-central-tfstate-${get_aws_account_id()}"
    key            = "${get_env("TF_VAR_project_name")}/terraform.tfstate"
    region         = get_env("TF_VAR_aws_region", "sa-east-1")

    # Configurações de Segurança (Substitui check_bucket_exists e encryption manual)
    encrypt        = true
    # MUDANÇA (Análise de Escalabilidade): Tabela de lock por projeto para evitar contenção.
    # Antes: Tabela central. Depois: Tabela isolada por projeto.
    dynamodb_table = "a-ponte-lock-${get_env("TF_VAR_project_name")}"

    # --- SECURITY HARDENING (Paridade com Backend-IaC) ---
    # Terragrunt cria automaticamente bucket S3 e tabela DynamoDB se não existirem
    # Configurações de segurança aplicadas automaticamente
    enable_lock_table_ssencryption     = true  # Criptografia na tabela de Lock
    skip_bucket_enforced_tls           = false # Garante que o bucket recuse conexões não-HTTPS
    skip_bucket_public_access_blocking = false # Bloqueia acesso público
    skip_bucket_root_access            = true  # FIX (Bootstrap): Evita falha de verificação em usuários federados (OIDC/SSO)
    skip_bucket_versioning             = false # Garante histórico de estado
    # Não desabilita criação automática - Terragrunt gerencia isso
    # CRÍTICO (Bootstrap Paradox): Deve ser FALSE para permitir que o Terragrunt crie o bucket automaticamente (No-Code).
    disable_bucket_update              = false

    s3_bucket_tags = {
      ManagedBy   = "Terragrunt"
      Project     = "A-PONTE-Core" # Recurso Compartilhado
      Environment = "Management"
    }

    dynamodb_table_tags = {
      ManagedBy = "Terragrunt"
      Purpose   = "State Locking"
      Project   = get_env("TF_VAR_project_name") # Isolamento por Projeto
    }
  }
}

# Repassa inputs para o Terraform
inputs = {
  project_name   = get_env("TF_VAR_project_name")
  aws_region     = get_env("TF_VAR_aws_region", "sa-east-1")
  account_id     = get_env("TF_VAR_account_id", get_aws_account_id())
  security_email = get_env("TF_VAR_security_email", "admin@example.com")
  # Decodifica a lista JSON de repositórios passada pela CLI
  github_repos   = jsondecode(get_env("TF_VAR_github_repos", "[]"))

  # Tags enriquecidas com project_name para rastreabilidade e evitar recursos órfãos
  tags = {
    ManagedBy   = "A-PONTE"
    Project     = get_env("TF_VAR_project_name")
    Environment = get_env("TF_VAR_environment", "development")
    CreatedBy   = "Terragrunt"
  }
}
