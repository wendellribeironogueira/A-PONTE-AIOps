package utils

import (
	"context"
	"os"

	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/sts"
)

// GetRegion retorna a região AWS configurada ou o default sa-east-1
func GetRegion() string {
	if r := os.Getenv("AWS_REGION"); r != "" {
		return r
	}
	return "sa-east-1"
}

// GetProjectRoot retorna a raiz do projeto baseada na variável de ambiente APONTE_ROOT
// ou no diretório atual como fallback
func GetProjectRoot() string {
	if root := os.Getenv("APONTE_ROOT"); root != "" {
		return root
	}
	cwd, _ := os.Getwd()
	return cwd
}

// GetAccountID retorna o ID da conta AWS atual usando STS.
func GetAccountID() string {
	ctx := context.TODO()
	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(GetRegion()))
	if err != nil {
		return "unknown"
	}
	client := sts.NewFromConfig(cfg)
	identity, err := client.GetCallerIdentity(ctx, &sts.GetCallerIdentityInput{})
	if err != nil {
		return "unknown"
	}
	return *identity.Account
}

// GetUser retorna o usuário atual do sistema de forma cross-platform.
func GetUser() string {
	user := os.Getenv("USER")
	if user == "" {
		user = os.Getenv("USERNAME") // Windows fallback
	}
	if user == "" {
		user = "default"
	}
	return user
}
