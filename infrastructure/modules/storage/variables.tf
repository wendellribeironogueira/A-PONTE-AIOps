variable "project_name" {
  type        = string
  description = "Nome do projeto"
}

variable "tags" {
  type        = map(string)
  description = "Tags padrão"
}

variable "create_global_resources" {
  type        = bool
  description = "Se deve criar recursos globais (Config, etc)"
  default     = true
}
