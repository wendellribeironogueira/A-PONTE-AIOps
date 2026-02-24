package cmd

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"aponte/cli/internal/utils"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/budgets"
	"github.com/aws/aws-sdk-go-v2/service/cloudtrail"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs"
	"github.com/aws/aws-sdk-go-v2/service/configservice"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/iam"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"
	"github.com/aws/aws-sdk-go-v2/service/ssm"
	"github.com/aws/smithy-go"
	"github.com/spf13/cobra"
)

var setupCleanupCmd = &cobra.Command{
	Use:   "cleanup",
	Short: "Limpa recursos zumbis do Bootstrap",
	Run:   runSetupCleanup,
}

func init() {
	setupCmd.AddCommand(setupCleanupCmd)
}

// cleanupTargets define os recursos a serem limpos (Separation of Data)
type CleanupConfig struct {
	IAMRoles         []string `json:"iam_roles"`
	IAMPolicies      []string `json:"iam_policies"`
	SSMParams        []string `json:"ssm_params"`
	LogGroups        []string `json:"log_groups"`
	Trails           []string `json:"trails"`
	ConfigRules      []string `json:"config_rules"`
	Budgets          []string `json:"budgets"`
	S3BucketPrefixes []string `json:"s3_bucket_prefixes"`
}

var defaultCleanupTargets = CleanupConfig{
	IAMRoles: []string{
		"a-ponte-github-actions-role",
		"a-ponte-cloudtrail-cw-role",
		"a-ponte-config-role",
	},
	IAMPolicies: []string{
		"policy/a-ponte-devops-policy",
		"policy/a-ponte-infra-boundary",
		"policy/APonteRegistryAccess-a-ponte",
	},
	SSMParams: []string{
		"/a-ponte/global/security/contact_email",
		"/a-ponte/global/dynamodb/registry_table_name",
		"/a-ponte/global/s3/audit_logs_bucket_name",
		"/a-ponte/global/s3/config_bucket_name",
	},
	LogGroups: []string{
		"/aws/cloudtrail/a-ponte",
	},
	Trails: []string{
		"a-ponte-main-trail",
	},
	ConfigRules: []string{
		"encrypted-volumes",
		"root-account-mfa-enabled",
		"s3-bucket-server-side-encryption-enabled",
	},
	Budgets: []string{
		"a-ponte-monthly-budget",
	},
	S3BucketPrefixes: []string{
		"a-ponte-audit-logs",
		"a-ponte-config-logs",
	},
}

var cleanupTargets CleanupConfig

func runSetupCleanup(cmd *cobra.Command, args []string) {
	fmt.Println("🧹 Iniciando limpeza de recursos conflitantes...")

	// OCP: Tenta carregar configuração externa, fallback para default
	root := utils.GetProjectRoot()
	configPath := filepath.Join(root, "config", "cleanup.json")

	if content, err := os.ReadFile(configPath); err == nil {
		if err := json.Unmarshal(content, &cleanupTargets); err != nil {
			fmt.Printf("⚠️  Erro ao ler %s: %v. Usando defaults.\n", configPath, err)
			cleanupTargets = defaultCleanupTargets
		} else {
			fmt.Printf("📄 Configuração de limpeza carregada de: %s\n", configPath)
		}
	} else {
		cleanupTargets = defaultCleanupTargets
	}

	ctx := context.TODO()
	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(utils.GetRegion()))
	if err != nil {
		fmt.Printf("❌ Erro ao carregar config AWS: %v\n", err)
		return
	}

	accountID := utils.GetAccountID()

	cleanupIAM(ctx, cfg, accountID)
	cleanupDynamoDB(ctx, cfg)
	cleanupSSM(ctx, cfg)
	cleanupLogs(ctx, cfg)
	cleanupTrail(ctx, cfg)
	cleanupConfig(ctx, cfg)
	cleanupBudgets(ctx, cfg, accountID)
	cleanupS3(ctx, cfg)

	fmt.Println("✅ Limpeza concluída. Agora você pode rodar 'aponte setup' novamente.")
}

func cleanupIAM(ctx context.Context, cfg aws.Config, accountID string) {
	iamClient := iam.NewFromConfig(cfg)

	for _, role := range cleanupTargets.IAMRoles {
		fmt.Printf("👤 Processando Role: %s\n", role)
		// Remove Permissions Boundary
		_, err := iamClient.DeleteRolePermissionsBoundary(ctx, &iam.DeleteRolePermissionsBoundaryInput{RoleName: aws.String(role)})
		ignoreNotFound(err)

		// Detach Policies (Dinâmico para evitar DeleteConflict)
		paginator := iam.NewListAttachedRolePoliciesPaginator(iamClient, &iam.ListAttachedRolePoliciesInput{RoleName: aws.String(role)})
		for paginator.HasMorePages() {
			page, err := paginator.NextPage(ctx)
			if err != nil {
				ignoreNotFound(err)
				break
			}
			for _, pol := range page.AttachedPolicies {
				fmt.Printf("   🔗 Detaching: %s\n", *pol.PolicyName)
				_, err := iamClient.DetachRolePolicy(ctx, &iam.DetachRolePolicyInput{RoleName: aws.String(role), PolicyArn: pol.PolicyArn})
				ignoreNotFound(err)
			}
		}

		// Delete Role
		_, err = iamClient.DeleteRole(ctx, &iam.DeleteRoleInput{RoleName: aws.String(role)})
		ignoreNotFound(err)
	}

	for _, polSuffix := range cleanupTargets.IAMPolicies {
		pol := fmt.Sprintf("arn:aws:iam::%s:%s", accountID, polSuffix)
		fmt.Printf("📜 Deletando Policy: %s\n", pol)
		_, err := iamClient.DeletePolicy(ctx, &iam.DeletePolicyInput{PolicyArn: aws.String(pol)})
		ignoreNotFound(err)
	}

	oidcArn := fmt.Sprintf("arn:aws:iam::%s:oidc-provider/token.actions.githubusercontent.com", accountID)
	fmt.Printf("🌐 Deletando OIDC: %s\n", oidcArn)
	_, err := iamClient.DeleteOpenIDConnectProvider(ctx, &iam.DeleteOpenIDConnectProviderInput{OpenIDConnectProviderArn: aws.String(oidcArn)})
	ignoreNotFound(err)
}

func cleanupDynamoDB(ctx context.Context, cfg aws.Config) {
	fmt.Println("🗄️  Deletando Tabela DynamoDB...")
	if utils.ConfirmAction("⚠️  ATENÇÃO: Isso deletará a tabela de registro 'a-ponte-registry'. Todos os metadados de projetos serão perdidos. Continuar? [y/N]") {
		dbClient := dynamodb.NewFromConfig(cfg)
		_, err := dbClient.DeleteTable(ctx, &dynamodb.DeleteTableInput{TableName: aws.String("a-ponte-registry")})
		ignoreNotFound(err)
	} else {
		fmt.Println("⏭️  Pulando deleção do registro...")
	}
}

func cleanupSSM(ctx context.Context, cfg aws.Config) {
	fmt.Println("🔑 Deletando Parâmetros SSM...")
	ssmClient := ssm.NewFromConfig(cfg)
	for _, p := range cleanupTargets.SSMParams {
		_, err := ssmClient.DeleteParameter(ctx, &ssm.DeleteParameterInput{Name: aws.String(p)})
		ignoreNotFound(err)
	}
}

func cleanupLogs(ctx context.Context, cfg aws.Config) {
	fmt.Println("📝 Deletando Log Groups...")
	logsClient := cloudwatchlogs.NewFromConfig(cfg)
	for _, lg := range cleanupTargets.LogGroups {
		_, err := logsClient.DeleteLogGroup(ctx, &cloudwatchlogs.DeleteLogGroupInput{LogGroupName: aws.String(lg)})
		ignoreNotFound(err)
	}
}

func cleanupTrail(ctx context.Context, cfg aws.Config) {
	fmt.Println("👣 Deletando Trail...")
	trailClient := cloudtrail.NewFromConfig(cfg)
	for _, t := range cleanupTargets.Trails {
		_, err := trailClient.DeleteTrail(ctx, &cloudtrail.DeleteTrailInput{Name: aws.String(t)})
		ignoreNotFound(err)
	}
}

func cleanupConfig(ctx context.Context, cfg aws.Config) {
	fmt.Println("⚙️  Limpando AWS Config...")
	cfgClient := configservice.NewFromConfig(cfg)
	_, err := cfgClient.DeleteDeliveryChannel(ctx, &configservice.DeleteDeliveryChannelInput{DeliveryChannelName: aws.String("a-ponte-config-delivery")})
	ignoreNotFound(err)
	_, err = cfgClient.DeleteConfigurationRecorder(ctx, &configservice.DeleteConfigurationRecorderInput{ConfigurationRecorderName: aws.String("a-ponte-config-recorder")})
	ignoreNotFound(err)

	for _, r := range cleanupTargets.ConfigRules {
		_, err := cfgClient.DeleteConfigRule(ctx, &configservice.DeleteConfigRuleInput{ConfigRuleName: aws.String(r)})
		ignoreNotFound(err)
	}
}

func cleanupBudgets(ctx context.Context, cfg aws.Config, accountID string) {
	fmt.Println("💰 Deletando Budgets...")
	budgetsClient := budgets.NewFromConfig(cfg)
	for _, b := range cleanupTargets.Budgets {
		_, err := budgetsClient.DeleteBudget(ctx, &budgets.DeleteBudgetInput{AccountId: aws.String(accountID), BudgetName: aws.String(b)})
		ignoreNotFound(err)
	}
}

func cleanupS3(ctx context.Context, cfg aws.Config) {
	fmt.Println("📦 Deletando Buckets S3 (Force)...")
	s3Client := s3.NewFromConfig(cfg)

	// Robustez: Busca buckets por prefixo para evitar falha em nomes dinâmicos (ex: com sufixo de conta)
	if listBuckets, err := s3Client.ListBuckets(ctx, &s3.ListBucketsInput{}); err == nil {
		for _, b := range listBuckets.Buckets {
			name := aws.ToString(b.Name)
			for _, prefix := range cleanupTargets.S3BucketPrefixes {
				if strings.HasPrefix(name, prefix) {
					forceDeleteBucket(ctx, s3Client, name)
					break // Evita deletar duas vezes se houver sobreposição de prefixos
				}
			}
		}
	}
}

// ignoreNotFound engole erros de recursos inexistentes para garantir idempotência
func ignoreNotFound(err error) {
	if err == nil {
		return
	}
	var ae smithy.APIError
	if errors.As(err, &ae) {
		switch ae.ErrorCode() {
		case "NoSuchEntity", "ResourceNotFoundException", "ParameterNotFound", "NotFound", "NoSuchBucket":
			return
		}
	}
	// Loga outros erros mas não para a execução (Best Effort cleanup)
	fmt.Printf("   ⚠️  Erro ignorado: %v\n", err)
}

func forceDeleteBucket(ctx context.Context, svc *s3.Client, bucket string) {
	// 1. Esvazia objetos
	paginator := s3.NewListObjectsV2Paginator(svc, &s3.ListObjectsV2Input{Bucket: aws.String(bucket)})
	for paginator.HasMorePages() {
		page, err := paginator.NextPage(ctx)
		if err != nil {
			ignoreNotFound(err)
			return
		}

		var objects []types.ObjectIdentifier
		for _, obj := range page.Contents {
			objects = append(objects, types.ObjectIdentifier{Key: obj.Key})
		}

		if len(objects) > 0 {
			svc.DeleteObjects(ctx, &s3.DeleteObjectsInput{
				Bucket: aws.String(bucket),
				Delete: &types.Delete{Objects: objects, Quiet: aws.Bool(true)},
			})
		}
	}

	// 2. Esvazia versões (se versionado)
	verPaginator := s3.NewListObjectVersionsPaginator(svc, &s3.ListObjectVersionsInput{Bucket: aws.String(bucket)})
	for verPaginator.HasMorePages() {
		page, err := verPaginator.NextPage(ctx)
		if err != nil {
			ignoreNotFound(err)
			return
		}

		var objects []types.ObjectIdentifier
		for _, ver := range page.Versions {
			objects = append(objects, types.ObjectIdentifier{
				Key:       ver.Key,
				VersionId: ver.VersionId,
			})
		}
		for _, del := range page.DeleteMarkers {
			objects = append(objects, types.ObjectIdentifier{
				Key:       del.Key,
				VersionId: del.VersionId,
			})
		}

		if len(objects) > 0 {
			svc.DeleteObjects(ctx, &s3.DeleteObjectsInput{
				Bucket: aws.String(bucket),
				Delete: &types.Delete{Objects: objects, Quiet: aws.Bool(true)},
			})
		}
	}

	// 3. Deleta o bucket
	_, err := svc.DeleteBucket(ctx, &s3.DeleteBucketInput{Bucket: aws.String(bucket)})
	if err != nil {
		ignoreNotFound(err)
		fmt.Printf("   ❌ Falha ao deletar bucket %s: %v\n", bucket, err)
	} else {
		fmt.Printf("   🗑️  Bucket deletado: %s\n", bucket)
	}
}
