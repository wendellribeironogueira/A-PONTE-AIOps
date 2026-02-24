# =================================================================================
# A-PONTE: Bootstrap Child Configuration
# =================================================================================
# Herda as configurações globais (Backend S3, DynamoDB, Inputs) da raiz.
# =================================================================================

# FIX: Bootstrap deve ser independente do root.hcl para evitar hooks de proteção (prevent_root_execution)
# e dependências circulares durante a criação inicial do backend.
remote_state {
  backend = "s3"
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
  config = {
    bucket         = "a-ponte-central-tfstate-${get_aws_account_id()}"
    key            = "a-ponte/terraform.tfstate"
    region         = get_env("TF_VAR_aws_region", "sa-east-1")
    encrypt        = true
    dynamodb_table = "a-ponte-lock-a-ponte"
  }
}

# FIX: Define tags explicitamente já que não herdamos do root.hcl
inputs = {
  account_id     = get_aws_account_id()
  aws_region     = get_env("TF_VAR_aws_region", "sa-east-1")
  security_email = get_env("TF_VAR_security_email", "security@aponte.platform")

  tags = {
    Project     = "a-ponte"
    Environment = "production"
    ManagedBy   = "A-PONTE"
    CreatedBy   = "Bootstrap"
  }
}
