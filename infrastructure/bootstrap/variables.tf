variable "project_name" {
  type        = string
  description = "Nome do projeto"
}

variable "aws_region" {
  type        = string
  description = "Região AWS"
}

variable "account_id" {
  type        = string
  description = "ID da conta AWS"
}

variable "github_repos" {
  type        = list(string)
  description = "Lista de repositórios GitHub permitidos"
  default     = []
}

variable "tags" {
  type        = map(string)
  description = "Tags padrão"
  default     = {}
}


variable "security_email" {
  type        = string
  description = "Email para alertas de segurança"
}

variable "create_break_glass_role" {
  type        = bool
  description = "Flag para criar role de emergência"
  default     = false
}
