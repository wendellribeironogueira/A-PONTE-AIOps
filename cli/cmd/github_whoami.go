package cmd

import (
	"context"
	"fmt"
	"os"

	"aponte/cli/internal/github"

	"github.com/spf13/cobra"
)

var githubWhoamiCmd = &cobra.Command{
	Use:   "whoami",
	Short: "Verifica a autenticação com o GitHub (Token)",
	Run:   runGithubWhoami,
}

func init() {
	githubCmd.AddCommand(githubWhoamiCmd)
}

func runGithubWhoami(cmd *cobra.Command, args []string) {
	fmt.Println("🔍 Verificando credenciais do GitHub (via SDK)...")

	client := github.NewClient()
	ctx := context.Background()

	// Get("") retorna o usuário autenticado associado ao token
	user, resp, err := client.Users.Get(ctx, "")
	if err != nil {
		fmt.Printf("❌ Falha na autenticação: %v\n", err)
		if resp != nil && resp.StatusCode == 401 {
			fmt.Println("   Causa: Token inválido ou expirado.")
		} else if resp == nil {
			fmt.Println("   Causa: Token não encontrado (Acesso Anônimo) ou erro de rede.")
		}
		os.Exit(1)
	}

	fmt.Printf("✅ Autenticado como: %s\n", *user.Login)
	fmt.Printf("   URL: %s\n", *user.HTMLURL)
}
