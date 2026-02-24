package core

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"text/template"
	"time"

	"aponte/cli/internal/utils"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/aws/retry"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

const TerragruntTemplate = `# Configuração Terragrunt para {{.Name}}
include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
   # Fonte da Infraestrutura:
   # 1. Padrão: Usa o módulo 'app-template' do A-PONTE (Greenfield).
   # 2. Customizado: Aponte para um repositório clonado (ex: "./repos/minha-infra").
   source = "../../infrastructure/modules/app-template"
}

inputs = {
  project_name = "{{.Name}}"
  environment  = "{{.Env}}"
  app_name     = "{{.App}}"
  resource_name = "{{.Resource}}"
  security_email = "{{.Email}}"
  tags = {
    Project     = "{{.Name}}"
    Environment = "{{.Env}}"
    Application = "{{.App}}"
    Component   = "{{.Resource}}"
    ManagedBy   = "A-PONTE"
  }
}
`

// Project represents a project in the registry
type Project struct {
	Name          string
	Environment   string
	IsProduction  bool
	SecurityEmail string
	AppName       string
	ResourceName  string
	Status        string
	Repositories  []string
}

func getDynamoClient(ctx context.Context) (*dynamodb.Client, error) {
	cfg, err := config.LoadDefaultConfig(ctx,
		config.WithRegion(utils.GetRegion()),
		config.WithRetryer(func() aws.Retryer {
			return retry.NewStandard(func(o *retry.StandardOptions) {
				o.MaxAttempts = 5
			})
		}))
	if err != nil {
		return nil, err
	}
	return dynamodb.NewFromConfig(cfg), nil
}

// GetProject retrieves a project from DynamoDB
func GetProject(name string) (*Project, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	svc, err := getDynamoClient(ctx)
	if err != nil {
		return nil, fmt.Errorf("erro ao carregar config AWS: %w", err)
	}

	out, err := svc.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String("a-ponte-registry"),
		Key: map[string]types.AttributeValue{
			"ProjectName": &types.AttributeValueMemberS{Value: name},
		},
	})
	if err != nil {
		return nil, err
	}
	if out.Item == nil {
		return nil, nil // Not found
	}

	return mapToProject(out.Item), nil
}

func mapToProject(item map[string]types.AttributeValue) *Project {
	p := &Project{}
	if v, ok := item["ProjectName"].(*types.AttributeValueMemberS); ok {
		p.Name = v.Value
	}
	if v, ok := item["Environment"].(*types.AttributeValueMemberS); ok {
		p.Environment = v.Value
	} else {
		p.Environment = "development"
	}
	if v, ok := item["IsProduction"].(*types.AttributeValueMemberBOOL); ok {
		p.IsProduction = v.Value
	}
	if v, ok := item["SecurityEmail"].(*types.AttributeValueMemberS); ok {
		p.SecurityEmail = v.Value
	} else {
		if envEmail := os.Getenv("TF_VAR_security_email"); envEmail != "" {
			p.SecurityEmail = envEmail
		} else {
			p.SecurityEmail = "admin@example.com"
		}
	}
	if v, ok := item["AppName"].(*types.AttributeValueMemberS); ok {
		p.AppName = v.Value
	} else {
		p.AppName = p.Name
	}
	if v, ok := item["ResourceName"].(*types.AttributeValueMemberS); ok {
		p.ResourceName = v.Value
	} else {
		p.ResourceName = "tenant-root"
	}
	if v, ok := item["Status"].(*types.AttributeValueMemberS); ok {
		p.Status = v.Value
	}
	if v, ok := item["Repositories"].(*types.AttributeValueMemberSS); ok {
		p.Repositories = v.Value
	} else if v, ok := item["Repositories"].(*types.AttributeValueMemberL); ok {
		for _, item := range v.Value {
			if s, ok := item.(*types.AttributeValueMemberS); ok {
				p.Repositories = append(p.Repositories, s.Value)
			}
		}
	}
	return p
}

// CreateProject creates a new project in DynamoDB
func CreateProject(p Project) error {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	svc, err := getDynamoClient(ctx)
	if err != nil {
		return fmt.Errorf("erro ao carregar config AWS: %w", err)
	}

	// Verifica se a tabela existe, se não, cria (Self-Healing)
	_, err = svc.DescribeTable(ctx, &dynamodb.DescribeTableInput{TableName: aws.String("a-ponte-registry")})
	if err != nil {
		var notFound *types.ResourceNotFoundException
		if errors.As(err, &notFound) {
			log.Printf("⚠️  Tabela 'a-ponte-registry' não encontrada. Criando automaticamente...")
			CreateRegistryTable(svc, "a-ponte-registry")
		} else {
			return err
		}
	}

	_, err = svc.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String("a-ponte-registry"),
		Item: map[string]types.AttributeValue{
			"ProjectName":   &types.AttributeValueMemberS{Value: p.Name},
			"Environment":   &types.AttributeValueMemberS{Value: p.Environment},
			"IsProduction":  &types.AttributeValueMemberBOOL{Value: p.IsProduction},
			"SecurityEmail": &types.AttributeValueMemberS{Value: p.SecurityEmail},
			"CreatedAt":     &types.AttributeValueMemberS{Value: time.Now().Format(time.RFC3339)},
			"CreatedBy":     &types.AttributeValueMemberS{Value: "cli-go"},
			"Status":        &types.AttributeValueMemberS{Value: "ACTIVE"},
			"AppName":       &types.AttributeValueMemberS{Value: p.AppName},
			"ResourceName":  &types.AttributeValueMemberS{Value: p.ResourceName},
		},
		ConditionExpression: aws.String("attribute_not_exists(ProjectName)"),
	})
	return err
}

// ListProjects retrieves all projects
func ListProjects() ([]Project, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	svc, err := getDynamoClient(ctx)
	if err != nil {
		return nil, fmt.Errorf("erro ao carregar config AWS: %w", err)
	}

	paginator := dynamodb.NewScanPaginator(svc, &dynamodb.ScanInput{
		TableName:            aws.String("a-ponte-registry"),
		ProjectionExpression: aws.String("ProjectName, Environment, IsProduction, #s"),
		ExpressionAttributeNames: map[string]string{
			"#s": "Status",
		},
	})

	var projects []Project
	for paginator.HasMorePages() {
		page, err := paginator.NextPage(ctx)
		if err != nil {
			return nil, err
		}
		for _, item := range page.Items {
			projects = append(projects, *mapToProject(item))
		}
	}
	return projects, nil
}

// DeleteProject removes a project from DynamoDB
func DeleteProject(name string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	svc, err := getDynamoClient(ctx)
	if err != nil {
		return fmt.Errorf("erro ao carregar config AWS: %w", err)
	}

	_, err = svc.DeleteItem(ctx, &dynamodb.DeleteItemInput{
		TableName: aws.String("a-ponte-registry"),
		Key: map[string]types.AttributeValue{
			"ProjectName": &types.AttributeValueMemberS{Value: name},
		},
	})
	return err
}

// DetachProject removes local configuration files for a project.
func DetachProject(name string) error {
	root := utils.GetProjectRoot()
	projectsDir := filepath.Join(root, "projects")
	files := []string{
		filepath.Join(projectsDir, name+".repos"),
		filepath.Join(projectsDir, name+".auto.tfvars"),
		filepath.Join(projectsDir, name+".project.yml"),
	}

	for _, f := range files {
		if err := os.Remove(f); err != nil && !os.IsNotExist(err) {
			log.Printf("⚠️  Erro ao remover %s: %v", f, err)
		}
	}
	return nil
}

// CreateLocalFiles generates the local configuration files for a project.
func CreateLocalFiles(name, env string, isProd bool, email, app, resource string) {
	root := utils.GetProjectRoot()
	projectsDir := filepath.Join(root, "projects")
	if err := os.MkdirAll(projectsDir, 0755); err != nil {
		log.Printf("❌ Erro ao criar diretório de projetos: %v", err)
	}

	// .project.yml
	configContent := fmt.Sprintf("# Configuração do projeto: %s\nis_production=%v\nenvironment=%s\nallow_destroy=true\n", name, isProd, env)
	ymlPath := filepath.Join(projectsDir, name+".project.yml")
	// SAFETY NET: Se o arquivo já existe, faz backup antes de sobrescrever
	if _, err := os.Stat(ymlPath); err == nil {
		if _, err := utils.VersionFile(ymlPath, name, "overwrite_create"); err != nil {
			log.Printf("⚠️  Falha ao criar backup de %s: %v", ymlPath, err)
		}
	}
	if err := os.WriteFile(ymlPath, []byte(configContent), 0644); err != nil {
		log.Printf("❌ Erro ao escrever %s: %v", ymlPath, err)
	}

	// .repos (vazio inicialmente)
	reposFile := filepath.Join(projectsDir, name+".repos")
	if _, err := os.Stat(reposFile); os.IsNotExist(err) {
		if err := os.WriteFile(reposFile, []byte("# Cacheado do registro\n"), 0644); err != nil {
			log.Printf("❌ Erro ao criar %s: %v", reposFile, err)
		}
	}

	// Cria diretório do projeto para Terraform/Terragrunt (Fix Pipeline Error)
	projectPath := filepath.Join(projectsDir, name)
	if err := os.MkdirAll(projectPath, 0755); err != nil {
		log.Printf("❌ Erro ao criar diretório do projeto: %v", err)
	} else {
		// Cria um terragrunt.hcl básico para permitir que o 'plan' funcione
		tgFile := filepath.Join(projectPath, "terragrunt.hcl")
		if _, err := os.Stat(tgFile); os.IsNotExist(err) {
			tmpl, err := template.New("terragrunt").Parse(TerragruntTemplate)
			if err != nil {
				log.Printf("❌ Erro ao preparar template: %v", err)
				return
			}
			var buf bytes.Buffer
			data := struct{ Name, Env, Email, App, Resource string }{name, env, email, app, resource}
			if err := tmpl.Execute(&buf, data); err != nil {
				log.Printf("❌ Erro ao gerar terragrunt.hcl: %v", err)
				return
			}
			if err := os.WriteFile(tgFile, buf.Bytes(), 0644); err != nil {
				log.Printf("❌ Erro ao escrever %s: %v", tgFile, err)
			} else {
				fmt.Printf("📄 Arquivo gerado: %s\n", tgFile)
			}
		} else {
			// Auto-Fix: Verifica se o arquivo existente tem a configuração antiga/quebrada
			content, err := os.ReadFile(tgFile)
			if err == nil {
				sContent := string(content)
				if strings.Contains(sContent, "find_in_parent_folders()") {
					fmt.Printf("🔧 Corrigindo terragrunt.hcl legado em %s...\n", tgFile)
					newContent := strings.Replace(sContent, "find_in_parent_folders()", "find_in_parent_folders(\"root.hcl\")", 1)
					if err := os.WriteFile(tgFile, []byte(newContent), 0644); err != nil {
						log.Printf("❌ Erro ao atualizar %s: %v", tgFile, err)
					}
				}
			}
		}
	}

	// .current_project (Switch automático)
	if err := SetContext(name); err != nil {
		log.Printf("⚠️  Falha ao definir contexto automático: %v", err)
	}
}

// HydrateLocalFiles restores local configuration from DynamoDB data.
func HydrateLocalFiles(p *Project) {
	CreateLocalFiles(p.Name, p.Environment, p.IsProduction, p.SecurityEmail, p.AppName, p.ResourceName)
	fmt.Printf("✅ Arquivos locais sincronizados e contexto alterado para: %s\n", p.Name)
}

// CreateRegistryTable creates the DynamoDB table if it doesn't exist.
func CreateRegistryTable(svc *dynamodb.Client, tableName string) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	_, err := svc.CreateTable(ctx, &dynamodb.CreateTableInput{
		TableName: aws.String(tableName),
		AttributeDefinitions: []types.AttributeDefinition{
			{
				AttributeName: aws.String("ProjectName"),
				AttributeType: types.ScalarAttributeTypeS,
			},
		},
		KeySchema: []types.KeySchemaElement{
			{
				AttributeName: aws.String("ProjectName"),
				KeyType:       types.KeyTypeHash,
			},
		},
		BillingMode: types.BillingModePayPerRequest,
	})
	if err != nil {
		log.Fatalf("❌ Falha ao criar tabela: %v", err)
	}

	fmt.Print("⏳ Aguardando tabela ficar ativa...")
	waiter := dynamodb.NewTableExistsWaiter(svc)
	err = waiter.Wait(ctx, &dynamodb.DescribeTableInput{
		TableName: aws.String(tableName),
	}, 5*time.Minute)
	if err != nil {
		log.Fatalf("❌ Erro aguardando tabela: %v", err)
	}
	fmt.Println(" ✅")
}
