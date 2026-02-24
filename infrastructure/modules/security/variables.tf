variable "project_name" {
  description = "Nome do projeto (Tenant ID) para namespace de recursos"
  type        = string
}

variable "tags" {
  description = "Mapa de tags padrão para governança e FinOps"
  type        = map(string)
  default     = {}
}

variable "create_global_resources" {
  description = "Flag para controlar a criação de recursos globais (Singleton) como Security Hub"
  type        = bool
  default     = false
}

variable "security_email" {
  description = "E-mail de contato para alertas de segurança (SNS)"
  type        = string
  default     = null
}

variable "registry_table_name" {
  description = "Nome da tabela DynamoDB de registro de projetos"
  type        = string
  default     = null
}

variable "audit_logs_bucket_name" {
  description = "Nome do bucket S3 para centralização de logs de auditoria"
  type        = string
  default     = null
}

variable "config_bucket_name" {
  description = "Nome do bucket S3 para logs do AWS Config"
  type        = string
  default     = null
}
