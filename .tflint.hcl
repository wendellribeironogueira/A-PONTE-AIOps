# Configuração TFLint para A-PONTE
# Habilita regras específicas para AWS e Terraform

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

config {
    module = true
    force = false
    disabled_by_default = false
}

# Plugin AWS (Obrigatório para validar tipos de instância, regiões, etc)
plugin "aws" {
    enabled = true
    version = "0.28.0"
    source  = "github.com/terraform-linters/tflint-ruleset-aws"
}

# --- A-PONTE HOUSE RULES (GOVERNANÇA) ---

# 1. Variáveis devem ter tipos explícitos (Robustez)
rule "terraform_typed_variables" {
    enabled = true
}

# 2. Variáveis não usadas devem ser removidas (Limpeza)
rule "terraform_unused_declarations" {
    enabled = true
}

# 3. Convenção de Nomes (Snake Case padrão)
rule "terraform_naming_convention" {
    enabled = true
}

# 4. Tags Obrigatórias (FinOps & Multi-Tenant Isolation)
# Garante que todo recurso rastreável tenha as tags de contexto para isolamento de custo e lógica
rule "aws_resource_missing_tags" {
    enabled = true
    tags = ["Project", "Environment", "App", "Component", "ManagedBy"]
}
