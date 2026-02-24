variable "project_name" {
  description = "Nome do projeto"
  type        = string
}

variable "tags" {
  description = "Tags obrigatórias"
  type        = map(string)
}

variable "create_global_resources" {
  description = "Se true, cria recursos globais (CloudTrail, Config, etc)"
  type        = bool
  default     = false
}

variable "audit_logs_bucket_name" {
  description = "Nome do bucket de logs de auditoria"
  type        = string
}

variable "config_bucket_name" {
  description = "Nome do bucket de logs do AWS Config"
  type        = string
}

variable "security_email" {
  description = "Email para alertas de segurança"
  type        = string
}

variable "permissions_boundary_arn" {
  description = "ARN do Permissions Boundary"
  type        = string
}

variable "log_retention_days" {
  description = "Dias de retenção dos logs"
  type        = number
  default     = 365
}

variable "cloudtrail_log_group_name" {
  description = "Nome do Log Group do CloudTrail para filtros de métrica"
  type        = string
}

variable "sns_topic_arn" {
  description = "ARN do tópico SNS para alertas de segurança"
  type        = string
}
