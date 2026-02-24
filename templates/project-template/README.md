# {{ cookiecutter.project_name }}

> Environment: {{ cookiecutter.environment }}
> App Name: {{ cookiecutter.app_name }}
> AWS Region: {{ cookiecutter.aws_region }}

## Estrutura do Projeto

Este projeto foi gerado automaticamente pela plataforma A-PONTE.

- `terragrunt.hcl`: Configuração de Infraestrutura (IaC).
- `src/`: Código fonte da aplicação.
- `docs/`: Documentação.

## Como Usar

1. Validar infraestrutura: `aponte tf:plan`
2. Aplicar mudanças: `aponte tf:apply`
