variable "project_name" {
  description = "Nome do projeto (Tenant ID)"
  type        = string
}

variable "environment" {
  description = "Ambiente de deploy (dev, staging, production)"
  type        = string
}

variable "security_email" {
  description = "E-mail de contato para alertas de segurança e orçamento"
  type        = string
}

variable "tags" {
  description = "Tags obrigatórias de governança"
  type        = map(string)
  default     = {}
}

variable "vpc_cidr" {
  description = "Bloco CIDR da VPC do projeto"
  type        = string
  default     = "10.0.0.0/16"
}

variable "github_repos" {
  description = "Lista de repositórios GitHub autorizados para CI/CD deste projeto"
  type        = list(string)
  default     = []
}

variable "app_name" {
  description = "Nome da aplicação (ex: site-institucional)"
  type        = string
}

variable "resource_name" {
  description = "Nome do recurso principal (ex: web-server)"
  type        = string
}
