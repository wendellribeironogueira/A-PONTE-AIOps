Aqui está um exemplo de código para o arquivo de teste `test.terraform` usando Terraform e `Terrafest`:


module "test" {
  source = "./tests"

  variable "env" {
    type = var.env
    default = {}
  }

  provider "env" {
    region         = var.region
    project_name   = var.project_name
    account_id   = var.account_id

    env = {
     gs_dynamodb_table = module.storage.dynamodb_table.gs_dynamodb_table.value,
     aws_dynamodb_table = module.storage.dynamodb_table.aws_dynamodb_table.value,
     aws_dynamodb_table_arn  = module.storage.dynamodb_table.aws_dynamodb_table_arn.value,
     governance_bucket_name   = var.govermination_bucket_name,
    }
  }

  provider "identity" {
    region        = var.region
    project_name     = var.project_name
    account_id    = var.account_id
    github_repos   = var.github_repos

    init = (
      var.tags = module.identity.tags,
      security_email = var.security_email,
    )

    env = {
      account_id           = var.account_id,
      id                  = var.id,
      region              = var.region,
      tags               = var.tags,
    }
  }

  provider "storage" {
    region        = var.region
    project_name     = var.project_name

    env = {
      cloudTrail_log_group_name = module.storage.cloudTrail_log_group_name.value,
      permissions_boundary_arn = module.security-permissions-boundary-arn.value,
    }
  }

  provider "security" {
    region        = var.region
    project_name     = var.project_name
    tags           = var.tags

    env = {
      account_id       = var.account_id,
      init = (
        verify_all365 = true,
      ),
    }
  }

  provider "governance" {
    region        = var.region
    project_name     = var.project_name
    tags           = var.tags

    env = {
      kms_key_alias   = module.kms.key-alias.value,
    }
  }
}


Para executar os testes, você pode usar:

bash
terraform init


e depois executar:

bash
terraform plan --env var.env || run .


ou

bash
terraform apply/destroy --env var.env || run .


Isso será executado na raiz do projeto, incluindo todos os testes.
