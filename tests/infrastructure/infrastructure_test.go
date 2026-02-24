package tests

import (
	"testing"

	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/assert"
)

func TestTerraformIdentityModule(t *testing.T) {
	t.Parallel()

	// Define as opções do Terraform para o módulo de Identity
	terraformOptions := &terraform.Options{
		// O caminho relativo para a pasta do módulo
		TerraformDir: "../terraform/modules/identity",

		// Desabilita o backend para testes locais/rápidos (evita lock no DynamoDB real)
		BackendConfig: map[string]interface{}{},
	}

	// Executa 'terraform init' e 'terraform validate'.
	// Falha o teste se houver erros de sintaxe ou configuração.
	output := terraform.InitAndValidate(t, terraformOptions)

	assert.Contains(t, output, "Success! The configuration is valid.")
}
