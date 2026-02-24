package core

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"aponte/cli/internal/integrations"
	"aponte/cli/internal/utils"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/aws/retry"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/scheduler"
	schedulerTypes "github.com/aws/aws-sdk-go-v2/service/scheduler/types"
	"github.com/aws/aws-sdk-go-v2/service/ssm"
	"github.com/aws/aws-sdk-go-v2/service/sts"
)

// EnableBreakGlass ativa o modo de emergência para um projeto.
func EnableBreakGlass(project string) {
	fmt.Println("🚑 ATIVANDO MODO BREAK-GLASS (EMERGÊNCIA)")
	fmt.Println("   Isso emitirá credenciais temporárias de suporte e as enviará para o GitHub.")

	// Confirmação
	if os.Getenv("FORCE_NON_INTERACTIVE") != "true" {
		if !utils.ConfirmAction("Confirma ativação? [s/N]:") {
			fmt.Println("❌ Cancelado.")
			return
		}
	}

	// 1. Configura Terraform Env
	if err := os.Setenv("TF_VAR_project_name", project); err != nil {
		log.Fatalf("❌ Erro ao definir variável de ambiente TF_VAR_project_name: %v", err)
	}
	if err := os.Setenv("TF_VAR_aws_region", utils.GetRegion()); err != nil {
		log.Fatalf("❌ Erro ao definir variável de ambiente TF_VAR_aws_region: %v", err)
	}

	// 2. Verifica se a role existe (via output)
	roleArn := getTerraformOutput(project, "support_break_glass_role_arn")

	// 3. Se não existe, cria on-demand
	if roleArn == "" || roleArn == "null" {
		fmt.Println("⚠️  Role de suporte não existe. Criando on-demand...")
		if err := os.Setenv("TF_VAR_create_break_glass_role", "true"); err != nil {
			log.Fatalf("❌ Erro ao definir variável de ambiente TF_VAR_create_break_glass_role: %v", err)
		}
		dir := getTfDir(project)
		cmd := utils.ExecMCP(dir, "terragrunt", "apply", "-auto-approve", "-var", "create_break_glass_role=true")
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		if err := cmd.Run(); err != nil {
			log.Fatalf("❌ Falha ao criar role de suporte: %v", err)
		}
		// Relê output
		if err := os.Setenv("TF_VAR_create_break_glass_role", "false"); err != nil { // Reset para leituras futuras
			log.Fatalf("❌ Erro ao resetar variável de ambiente TF_VAR_create_break_glass_role: %v", err)
		}
		roleArn = getTerraformOutput(project, "support_break_glass_role_arn")
	}

	if roleArn == "" || roleArn == "null" {
		log.Fatal("❌ Falha ao obter ARN da role de suporte.")
	}

	fmt.Printf("🔑 Role encontrada: %s\n", roleArn)

	// 4. Assume Role (STS)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	cfg, err := config.LoadDefaultConfig(ctx,
		config.WithRegion(utils.GetRegion()),
		config.WithRetryer(func() aws.Retryer {
			return retry.NewStandard(func(o *retry.StandardOptions) {
				o.MaxAttempts = 5
			})
		}))
	if err != nil {
		log.Fatalf("❌ Erro AWS Config: %v", err)
	}
	stsClient := sts.NewFromConfig(cfg)

	creds, err := stsClient.AssumeRole(ctx, &sts.AssumeRoleInput{
		RoleArn:         aws.String(roleArn),
		RoleSessionName: aws.String("BreakGlassSession"),
		DurationSeconds: aws.Int32(3600), // 1 hora
	})
	if err != nil {
		log.Fatalf("❌ Falha ao assumir role: %v", err)
	}

	// 5. Envia para GitHub
	fmt.Println("📤 Enviando credenciais temporárias para o GitHub...")

	setSecret := func(key, value string) {
		reposFile := filepath.Join(utils.GetProjectRoot(), "projects", project+".repos")
		content, _ := os.ReadFile(reposFile)
		lines := strings.Split(string(content), "\n")

		for _, repo := range lines {
			repo = strings.TrimSpace(repo)
			if repo == "" || strings.HasPrefix(repo, "#") {
				continue
			}

			cmd := exec.Command("gh", "secret", "set", key, "--body", value, "-R", repo)
			if err := cmd.Run(); err != nil {
				fmt.Printf("   ❌ Falha em %s: %s\n", repo, key)
			} else {
				fmt.Printf("   ✅ %s -> %s\n", key, repo)
			}
		}
	}

	setSecret("AWS_ACCESS_KEY_ID", *creds.Credentials.AccessKeyId)
	setSecret("AWS_SECRET_ACCESS_KEY", *creds.Credentials.SecretAccessKey)
	setSecret("AWS_SESSION_TOKEN", *creds.Credentials.SessionToken)

	fmt.Println("\n✅ MODO BREAK-GLASS ATIVADO (Válido por 1h)")

	// 5.5 Persiste estado no DynamoDB (Server-Side State)
	registerBreakGlassSession(project, 3600)

	// 6. Agenda Auto-Disable (Server-Side via EventBridge Scheduler)
	scheduleAutoDisable(project)
}

// DisableBreakGlass desativa o modo de emergência.
func DisableBreakGlass(project string) {
	fmt.Println("🔒 Desativando Break-Glass...")

	// 1. Destroi a role (via Terraform)
	if err := os.Setenv("TF_VAR_project_name", project); err != nil {
		log.Fatalf("❌ Erro ao definir variável de ambiente TF_VAR_project_name: %v", err)
	}
	if err := os.Setenv("TF_VAR_aws_region", utils.GetRegion()); err != nil {
		log.Fatalf("❌ Erro ao definir variável de ambiente TF_VAR_aws_region: %v", err)
	}
	if err := os.Setenv("TF_VAR_create_break_glass_role", "false"); err != nil {
		log.Fatalf("❌ Erro ao definir variável de ambiente TF_VAR_create_break_glass_role: %v", err)
	}

	dir := getTfDir(project)
	cmd := utils.ExecMCP(dir, "terragrunt", "apply", "-auto-approve", "-var", "create_break_glass_role=false")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		fmt.Printf("⚠️  Aviso: Falha ao destruir role (pode já estar destruída): %v\n", err)
	} else {
		fmt.Println("✅ Role de suporte destruída.")
	}

	// 2. Restaura OIDC (Github Sync)
	integrations.SyncSecrets(project)

	// 3. Remove estado do DynamoDB
	unregisterBreakGlassSession(project)

	// 4. Remove agendamento
	cancelAutoDisable(project)

	fmt.Println("✅ Break-Glass desativado com sucesso.")
}

func getTerraformOutput(project, key string) string {
	dir := getTfDir(project)
	cmd := utils.ExecMCP(dir, "terragrunt", "output", "-json")
	out, err := cmd.Output()
	if err != nil {
		log.Printf("⚠️  Erro ao ler outputs do Terraform: %v", err)
		return ""
	}
	if idx := bytes.IndexByte(out, '{'); idx != -1 {
		out = out[idx:]
	}
	var outputs map[string]struct {
		Value string `json:"value"`
	}
	if err := json.Unmarshal(out, &outputs); err != nil {
		return ""
	}
	return outputs[key].Value
}

func getTfDir(project string) string {
	if project == "a-ponte" {
		return filepath.Join("infrastructure", "bootstrap")
	}
	return filepath.Join("projects", project)
}

func registerBreakGlassSession(project string, duration int32) {
	ctx := context.Background()
	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(utils.GetRegion()))
	if err != nil {
		log.Printf("⚠️  Erro ao carregar config AWS: %v", err)
		return
	}
	svc := dynamodb.NewFromConfig(cfg)
	ttl := time.Now().Add(time.Duration(duration) * time.Second).Unix()
	_, err = svc.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String("a-ponte-registry"),
		Item: map[string]types.AttributeValue{
			"ProjectName":    &types.AttributeValueMemberS{Value: fmt.Sprintf("BREAKGLASS#%s", project)},
			"Type":           &types.AttributeValueMemberS{Value: "BreakGlassSession"},
			"TargetProject":  &types.AttributeValueMemberS{Value: project},
			"CreatedAt":      &types.AttributeValueMemberS{Value: time.Now().Format(time.RFC3339)},
			"ExpirationTime": &types.AttributeValueMemberN{Value: fmt.Sprintf("%d", ttl)},
			"Status":         &types.AttributeValueMemberS{Value: "ACTIVE"},
			"CreatedBy":      &types.AttributeValueMemberS{Value: utils.GetUser()},
		},
	})
	if err != nil {
		log.Printf("⚠️  Falha ao registrar sessão no DynamoDB: %v", err)
	} else {
		fmt.Println("📝 Sessão de emergência registrada no DynamoDB (Audit Trail).")
	}
}

func unregisterBreakGlassSession(project string) {
	ctx := context.Background()
	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(utils.GetRegion()))
	if err != nil {
		return
	}
	svc := dynamodb.NewFromConfig(cfg)
	_, err = svc.DeleteItem(ctx, &dynamodb.DeleteItemInput{
		TableName: aws.String("a-ponte-registry"),
		Key: map[string]types.AttributeValue{
			"ProjectName": &types.AttributeValueMemberS{Value: fmt.Sprintf("BREAKGLASS#%s", project)},
		},
	})
	if err != nil {
		log.Printf("⚠️  Falha ao remover registro da sessão no DynamoDB: %v", err)
	}
}

func scheduleAutoDisable(project string) {
	ctx := context.Background()
	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(utils.GetRegion()))
	if err != nil {
		return
	}
	ssmClient := ssm.NewFromConfig(cfg)
	lambdaParam, _ := ssmClient.GetParameter(ctx, &ssm.GetParameterInput{Name: aws.String("/a-ponte/global/security/break_glass_lambda_arn")})
	roleParam, _ := ssmClient.GetParameter(ctx, &ssm.GetParameterInput{Name: aws.String("/a-ponte/global/security/break_glass_scheduler_role_arn")})
	if lambdaParam == nil || roleParam == nil {
		return
	}

	schedulerClient := scheduler.NewFromConfig(cfg)
	executionTime := time.Now().Add(1 * time.Hour).Format("2006-01-02T15:04:05")
	_, err = schedulerClient.CreateSchedule(ctx, &scheduler.CreateScheduleInput{
		Name:                  aws.String(fmt.Sprintf("BreakGlass-Cleanup-%s", project)),
		ScheduleExpression:    aws.String(fmt.Sprintf("at(%s)", executionTime)),
		Target:                &schedulerTypes.Target{Arn: lambdaParam.Parameter.Value, RoleArn: roleParam.Parameter.Value, Input: aws.String(fmt.Sprintf(`{"project_name": "%s"}`, project))},
		FlexibleTimeWindow:    &schedulerTypes.FlexibleTimeWindow{Mode: schedulerTypes.FlexibleTimeWindowModeOff},
		ActionAfterCompletion: schedulerTypes.ActionAfterCompletionDelete,
	})
	if err != nil {
		fmt.Printf("⚠️  Aviso: Falha ao agendar limpeza automática: %v\n", err)
		return
	}
	fmt.Printf("⏰ Limpeza automática agendada para: %s (Server-Side)\n", executionTime)
}

func cancelAutoDisable(project string) {
	ctx := context.Background()
	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(utils.GetRegion()))
	if err != nil {
		return
	}
	schedulerClient := scheduler.NewFromConfig(cfg)
	_, err = schedulerClient.DeleteSchedule(ctx, &scheduler.DeleteScheduleInput{Name: aws.String(fmt.Sprintf("BreakGlass-Cleanup-%s", project))})
	if err != nil {
		fmt.Printf("⚠️  Aviso: Falha ao remover agendamento (pode já ter sido executado/removido): %v\n", err)
		return
	}
	fmt.Println("🗑️  Agendamento de limpeza removido.")
}
