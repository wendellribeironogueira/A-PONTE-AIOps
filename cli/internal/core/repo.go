package core

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	"aponte/cli/internal/utils"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/smithy-go"
)

func AddRepository(project, repo, repoType string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	svc, err := getDynamoClient(ctx)
	if err != nil {
		return err
	}

	_, err = svc.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName: aws.String("a-ponte-registry"),
		Key: map[string]types.AttributeValue{
			"ProjectName": &types.AttributeValueMemberS{Value: project},
		},
		UpdateExpression: aws.String("ADD Repositories :r SET RepositoryMetadata.#k = :v"),
		ExpressionAttributeNames: map[string]string{
			"#k": repo,
		},
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":r": &types.AttributeValueMemberSS{Value: []string{repo}},
			":v": &types.AttributeValueMemberS{Value: repoType},
		},
	})

	if err != nil {
		var apiError smithy.APIError
		if errors.As(err, &apiError) && apiError.ErrorCode() == "ValidationException" && strings.Contains(apiError.ErrorMessage(), "document path provided in the update expression is invalid") {
			_, err = svc.UpdateItem(ctx, &dynamodb.UpdateItemInput{
				TableName: aws.String("a-ponte-registry"),
				Key: map[string]types.AttributeValue{
					"ProjectName": &types.AttributeValueMemberS{Value: project},
				},
				UpdateExpression: aws.String("ADD Repositories :r SET RepositoryMetadata = :m"),
				ExpressionAttributeValues: map[string]types.AttributeValue{
					":r": &types.AttributeValueMemberSS{Value: []string{repo}},
					":m": &types.AttributeValueMemberM{Value: map[string]types.AttributeValue{
						repo: &types.AttributeValueMemberS{Value: repoType},
					}},
				},
			})
		}
	}
	return err
}

func RemoveRepository(project, repo string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	svc, err := getDynamoClient(ctx)
	if err != nil {
		return err
	}

	_, err = svc.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName: aws.String("a-ponte-registry"),
		Key: map[string]types.AttributeValue{
			"ProjectName": &types.AttributeValueMemberS{Value: project},
		},
		UpdateExpression: aws.String("DELETE Repositories :r"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":r": &types.AttributeValueMemberSS{Value: []string{repo}},
		},
	})
	return err
}

func ListRepositories(project string) ([]string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	svc, err := getDynamoClient(ctx)
	if err != nil {
		return nil, err
	}

	out, err := svc.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String("a-ponte-registry"),
		Key: map[string]types.AttributeValue{
			"ProjectName": &types.AttributeValueMemberS{Value: project},
		},
		ProjectionExpression: aws.String("Repositories"),
	})
	if err != nil {
		return nil, err
	}
	if out.Item == nil {
		return nil, fmt.Errorf("projeto não encontrado: %s", project)
	}

	var repos []string
	if ss, ok := out.Item["Repositories"].(*types.AttributeValueMemberSS); ok {
		repos = ss.Value
	}
	return repos, nil
}

func SyncRepositories(project string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	svc, err := getDynamoClient(ctx)
	if err != nil {
		return err
	}

	out, err := svc.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String("a-ponte-registry"),
		Key: map[string]types.AttributeValue{
			"ProjectName": &types.AttributeValueMemberS{Value: project},
		},
		ProjectionExpression: aws.String("Repositories, RepositoryMetadata"),
	})
	if err != nil {
		return err
	}
	if out.Item == nil {
		return fmt.Errorf("projeto não encontrado: %s", project)
	}

	var repos []string
	if ss, ok := out.Item["Repositories"].(*types.AttributeValueMemberSS); ok {
		repos = ss.Value
	}

	meta := make(map[string]string)
	if m, ok := out.Item["RepositoryMetadata"].(*types.AttributeValueMemberM); ok {
		for k, v := range m.Value {
			if s, ok := v.(*types.AttributeValueMemberS); ok {
				meta[k] = s.Value
			}
		}
	}

	updateLocalRepoFiles(project, repos, meta)
	return nil
}

func updateLocalRepoFiles(projectName string, repos []string, meta map[string]string) {
	projectsDir := filepath.Join(utils.GetProjectRoot(), "projects")
	if err := os.MkdirAll(projectsDir, 0755); err != nil {
		log.Printf("❌ Erro ao criar diretório de projetos: %v", err)
	}

	// Atualiza .repos
	reposFile := filepath.Join(projectsDir, projectName+".repos")
	if path, err := utils.VersionFile(reposFile, projectName, "sync_repos"); err == nil && path != "" {
		fmt.Printf("   📦 Backup criado: %s\n", filepath.Base(path))
	}
	reposContent := "# Cacheado do registro (DynamoDB)\n"
	if len(repos) > 0 {
		reposContent += strings.Join(repos, "\n") + "\n"
	}
	if err := os.WriteFile(reposFile, []byte(reposContent), 0644); err != nil {
		log.Printf("⚠️  Falha ao escrever .repos: %v", err)
	}

	// Atualiza .repos_meta.json (Contexto para IA)
	if len(meta) > 0 {
		metaFile := filepath.Join(projectsDir, projectName+".repos_meta.json")
		if _, err := utils.VersionFile(metaFile, projectName, "sync_meta"); err != nil {
			log.Printf("⚠️  Falha ao criar backup de %s: %v", metaFile, err)
		}
		if data, err := json.MarshalIndent(meta, "", "  "); err == nil {
			if err := os.WriteFile(metaFile, data, 0644); err != nil {
				log.Printf("⚠️  Falha ao escrever .repos_meta.json: %v", err)
			}
		}
	}

	// Atualiza .auto.tfvars
	tfvarsFile := filepath.Join(projectsDir, projectName+".auto.tfvars")
	if path, err := utils.VersionFile(tfvarsFile, projectName, "sync_tfvars"); err == nil && path != "" {
		fmt.Printf("   📦 Backup criado: %s\n", filepath.Base(path))
	}
	quotedRepos := make([]string, len(repos))
	for i, r := range repos {
		quotedRepos[i] = fmt.Sprintf("\"%s\"", r)
	}
	tfvarsContent := fmt.Sprintf(`# Arquivo gerado automaticamente - NÃO EDITAR MANUALMENTE
# Sincronizado em: %s

github_repos = [%s]
`, time.Now().Format(time.RFC3339), strings.Join(quotedRepos, ", "))
	if err := os.WriteFile(tfvarsFile, []byte(tfvarsContent), 0644); err != nil {
		log.Printf("⚠️  Falha ao escrever .auto.tfvars: %v", err)
	}

	fmt.Printf("✅ Sincronizado: %s (%d repositórios)\n", projectName, len(repos))
}
