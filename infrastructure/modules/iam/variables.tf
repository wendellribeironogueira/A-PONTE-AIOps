variable "project_name" {
  description = "Nome do projeto (tenant)."
  type        = string
}

variable "account_id" {
  description = "ID da conta AWS."
  type        = string
}

variable "aws_region" {
  description = "Região AWS."
  type        = string
}

variable "registry_table_arn" {
  description = "ARN da tabela de registro do DynamoDB."
  type        = string
}

variable "github_repos" {
  description = "Lista de repositórios GitHub autorizados para a role OIDC."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags a serem aplicadas."
  type        = map(string)
  default     = {}
}

variable "oidc_provider_arn" {
  description = "ARN do provedor OIDC global a ser usado na política de confiança."
  type        = string
}

variable "create_global_resources" {
  description = "Flag para controlar a criação de recursos globais (Singleton) e permissões administrativas"
  type        = bool
  default     = false
}

variable "create_break_glass_role" {
  description = "Cria role de suporte de emergência (Break Glass) com permissões de Admin"
  type        = bool
  default     = false
}
