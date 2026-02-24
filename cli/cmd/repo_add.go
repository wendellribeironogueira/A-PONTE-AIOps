package cmd

import (
	"bufio"
	"context"
	"fmt"
	"log"
	"os"
	"strings"

	"aponte/cli/internal/core"
	"aponte/cli/internal/github"
	"aponte/cli/internal/utils"
	"aponte/cli/internal/validator"

	"github.com/spf13/cobra"
)

var repoAddCmd = &cobra.Command{
	Use:   "add [repo] [project]",
	Short: "Adiciona um repositório ao projeto",
	Args:  cobra.MaximumNArgs(2),
	Run: func(cmd *cobra.Command, args []string) {
		var repo string
		if len(args) > 0 {
			repo = args[0]
		} else {
			fmt.Print("Digite o nome ou URL do repositório (ex: user/repo): ")
			reader := bufio.NewReader(os.Stdin)
			input, _ := reader.ReadString('\n')
			repo = strings.TrimSpace(input)
			if repo == "" {
				log.Fatal("❌ Nome do repositório é obrigatório.")
			}
		}

		var projectArgs []string
		if len(args) > 1 {
			projectArgs = args[1:]
		}
		// Resolve project from the second argument, or from context
		project := resolveProjectContext(projectArgs)
		runRepoAdd(repo, project)
	},
}

func init() {
	repoCmd.AddCommand(repoAddCmd)
}

func runRepoAdd(repo, project string) {
	checkProjectAndExitIfHome(project, "repo add")

	if err := validator.ValidateRepoName(repo); err != nil {
		log.Fatalf("❌ %v", err)
	}

	// Pergunta o tipo do repositório para enriquecer o contexto da IA
	repoType := "app"
	if os.Getenv("FORCE_NON_INTERACTIVE") != "true" {
		fmt.Printf("\nQual o tipo do repositório '%s'?\n", repo)
		fmt.Println("  1) App (Aplicação: Python, Java, Node...) [Padrão]")
		fmt.Println("  2) Infra (Infraestrutura: Terraform, Modules)")
		fmt.Print("Opção [1]: ")

		reader := bufio.NewReader(os.Stdin)
		input, _ := reader.ReadString('\n')
		input = strings.TrimSpace(input)

		if input == "2" {
			repoType = "infra"
		}

		// Validação de Visibilidade e Token
		fmt.Printf("\nO repositório '%s' é Público ou Privado?\n", repo)
		fmt.Println("  1) Público [Padrão]")
		fmt.Println("  2) Privado (Requer Token)")
		fmt.Print("Opção [1]: ")

		inputVis, _ := reader.ReadString('\n')
		inputVis = strings.TrimSpace(inputVis)

		if inputVis == "2" {
			if os.Getenv("GITHUB_TOKEN") == "" && os.Getenv("GH_TOKEN") == "" {
				fmt.Println("\n⚠️  Repositório privado detectado e nenhum token encontrado (GITHUB_TOKEN).")
				fmt.Print("👉 Insira seu GitHub Personal Access Token (PAT): ")
				token, _ := reader.ReadString('\n')
				token = strings.TrimSpace(token)
				if token != "" {
					os.Setenv("GITHUB_TOKEN", token)
					fmt.Println("✅ Token configurado temporariamente para validação.")
					fmt.Println("💡 Dica: Exporte GITHUB_TOKEN no seu shell para persistir.")
				}
			}
		}
	}

	// Validação remota (GitHub)
	fmt.Printf("🔍 Verificando repositório no GitHub: %s...\n", repo)
	if err := github.CheckRepoExists(context.Background(), repo); err != nil {
		fmt.Printf("⚠️  Falha ao verificar repositório '%s' (Erro: %v).\n", repo, err)
		fmt.Println("   Causas prováveis:")
		fmt.Println("   1. O repositório não existe.")
		fmt.Println("   2. Você não tem permissão de leitura (Token inválido/ausente).")
		fmt.Println("   3. O repositório é privado e você não configurou GITHUB_TOKEN.")

		if os.Getenv("FORCE_NON_INTERACTIVE") != "true" {
			if !utils.ConfirmAction("Deseja forçar a adição deste repositório? [s/N]") {
				os.Exit(1)
			}
			fmt.Println("⚠️  Adicionando repositório sem validação remota.")
		} else {
			log.Fatalf("❌ Validação falhou em modo não-interativo.")
		}
	} else {
		fmt.Println("✅ Repositório validado com sucesso.")
	}

	if err := core.AddRepository(project, repo, repoType); err != nil {
		log.Fatalf("❌ Erro ao adicionar repo no DynamoDB: %v", err)
	}

	fmt.Printf("✅ Repositório adicionado ao registro: %s -> %s\n", repo, project)

	// Sincroniza arquivos locais
	if err := core.SyncRepositories(project); err != nil {
		log.Fatalf("❌ Erro ao sincronizar arquivos locais: %v", err)
	}

	if repoType == "infra" {
		fmt.Println("\n💡 Próximos Passos (Infraestrutura Existente):")
		fmt.Printf("   1. Clone o código:      aponte git clone https://github.com/%s\n", repo)
		fmt.Println("   2. Padronize (Auto-Fix): aponte audit --local project")
		fmt.Println("      (Isso remove backends hardcoded e ajusta tags para o padrão A-PONTE)")
	}
}
