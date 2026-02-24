package core

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"time"

	"aponte/cli/internal/integrations"
	"aponte/cli/internal/utils"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

// BootstrapPlatform inicializa a infraestrutura base da plataforma.
func BootstrapPlatform() {
	ctx := context.Background()
	region := utils.GetRegion()
	accountID := utils.GetAccountID()

	if err := os.Setenv("TF_VAR_project_name", "a-ponte"); err != nil {
		log.Fatalf("❌ Erro ao definir variável de ambiente TF_VAR_project_name: %v", err)
	}
	if err := os.Setenv("TF_VAR_aws_region", region); err != nil {
		log.Fatalf("❌ Erro ao definir variável de ambiente TF_VAR_aws_region: %v", err)
	}
	if err := os.Setenv("TF_VAR_account_id", accountID); err != nil {
		log.Fatalf("❌ Erro ao definir variável de ambiente TF_VAR_account_id: %v", err)
	}
	if err := os.Setenv("TF_IN_AUTOMATION", "true"); err != nil {
		log.Fatalf("❌ Erro ao definir variável de ambiente TF_IN_AUTOMATION: %v", err)
	}

	if os.Getenv("TF_VAR_security_email") == "" {
		email := utils.Prompt("📧 Digite o e-mail para alertas de segurança:")
		if email == "" {
			log.Fatal("❌ O e-mail de segurança é obrigatório para o bootstrap.")
		}
		if err := os.Setenv("TF_VAR_security_email", email); err != nil {
			log.Fatalf("❌ Erro ao definir variável de ambiente TF_VAR_security_email: %v", err)
		}
	}

	fmt.Println("🏗️  Iniciando Bootstrap da Plataforma A-PONTE...")

	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(region))
	if err != nil {
		log.Fatalf("❌ Erro ao carregar config AWS: %v", err)
	}

	root := utils.GetProjectRoot()
	bootstrapDir := filepath.Join(root, "infrastructure", "bootstrap")

	backendFile := filepath.Join(bootstrapDir, "backend.tf")
	if _, err := os.Stat(backendFile); err == nil {
		fmt.Println("🧹 Removendo backend.tf existente...")
		if err := os.Remove(backendFile); err != nil {
			fmt.Printf("⚠️  Aviso: Falha ao remover backend.tf existente: %v\n", err)
		}
	}

	fmt.Println("🚀 Executando Terragrunt (Init + Apply)...")
	if err := runWithHeal(bootstrapDir, "init", "-reconfigure", "--terragrunt-non-interactive"); err != nil {
		log.Fatalf("❌ Falha no Terragrunt Init: %v", err)
	}
	if err := runWithHeal(bootstrapDir, "apply", "-auto-approve", "--terragrunt-non-interactive"); err != nil {
		log.Fatalf("❌ Falha no Terragrunt Apply: %v", err)
	}

	fmt.Println("📝 Registrando projeto 'a-ponte' no registro...")
	dynamoSvc := dynamodb.NewFromConfig(cfg)
	_, err = dynamoSvc.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String("a-ponte-registry"),
		Item: map[string]types.AttributeValue{
			"ProjectName": &types.AttributeValueMemberS{Value: "a-ponte"},
			"Type":        &types.AttributeValueMemberS{Value: "bootstrap"},
			"Environment": &types.AttributeValueMemberS{Value: "production"},
		},
	})
	if err != nil {
		log.Fatalf("❌ Falha ao registrar projeto 'a-ponte' no DynamoDB: %v", err)
	}

	if err := SetContext("a-ponte"); err != nil {
		log.Fatalf("❌ Falha ao definir o contexto para 'a-ponte': %v", err)
	}
	integrations.SyncSecrets("a-ponte") // Chamada sem verificação de erro, pois a função não retorna erro.
	// TODO: Para um tratamento de erro adequado, a função integrations.SyncSecrets deve ser modificada para retornar um erro.
	// Se a função for atualizada para retornar um erro, o bloco de tratamento de erro original pode ser restaurado.
	printSummary(bootstrapDir)
	if err := SetContext("home"); err != nil {
		log.Fatalf("❌ Falha ao resetar o contexto para 'home': %v", err)
	}
	fmt.Println("\n✅ Bootstrap concluído com sucesso!")
}

func runWithHeal(dir string, action string, args ...string) error {
	fullArgs := append([]string{action}, args...)
	cmd := utils.ExecMCP(dir, "terragrunt", fullArgs...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		fmt.Printf("\n⚠️  Falha em '%s'. Tentando auto-cura...\n", action)
		if err := os.RemoveAll(filepath.Join(dir, ".terraform")); err != nil {
			fmt.Printf("   - Aviso: Falha ao remover cache .terraform: %v\n", err)
		}
		if err := os.RemoveAll(filepath.Join(dir, ".terragrunt-cache")); err != nil {
			fmt.Printf("   - Aviso: Falha ao remover cache .terragrunt-cache: %v\n", err)
		}
		time.Sleep(2 * time.Second)
		return utils.ExecMCP(dir, "terragrunt", fullArgs...).Run()
	}
	return nil
}

func printSummary(dir string) {
	fmt.Println("\n📊 Resumo da Infraestrutura Base (Outputs):")
	out, _ := utils.ExecMCP(dir, "terragrunt", "output", "-json").Output()
	var outputs map[string]struct {
		Value string `json:"value"`
	}
	if err := json.Unmarshal(out, &outputs); err != nil {
		fmt.Println("   ⚠️  Não foi possível decodificar os outputs do Terraform.")
		return
	}
	keys := []string{"audit_logs_bucket", "config_logs_bucket", "github_actions_role_arn"}
	for _, k := range keys {
		if v, ok := outputs[k]; ok {
			fmt.Printf("   • %-25s: %s\n", k, v.Value)
		}
	}
}
