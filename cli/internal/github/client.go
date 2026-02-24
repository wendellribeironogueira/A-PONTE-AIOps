package github

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"strings"

	"github.com/google/go-github/v69/github"
	"golang.org/x/oauth2"
)

// NewClient cria um cliente GitHub autenticado (se token disponível) ou anônimo
func NewClient() *github.Client {
	token := os.Getenv("GITHUB_TOKEN")
	if token == "" {
		token = os.Getenv("GH_TOKEN")
	}

	var tc *http.Client
	if token != "" {
		ts := oauth2.StaticTokenSource(
			&oauth2.Token{AccessToken: token},
		)
		tc = oauth2.NewClient(context.Background(), ts)
	}

	return github.NewClient(tc)
}

// CheckRepoExists verifica se um repositório existe e é acessível
func CheckRepoExists(ctx context.Context, repoFullName string) error {
	parts := strings.Split(repoFullName, "/")
	if len(parts) != 2 {
		return fmt.Errorf("formato inválido (esperado 'user/repo')")
	}

	client := NewClient()
	_, _, err := client.Repositories.Get(ctx, parts[0], parts[1])
	return err
}
