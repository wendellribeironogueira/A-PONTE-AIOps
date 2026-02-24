package cmd

import (
	"bufio"
	"fmt"
	"log"
	"os"
	"strings"

	"aponte/cli/internal/core"

	"github.com/spf13/cobra"
)

var repoRemoveCmd = &cobra.Command{
	Use:   "remove [repo] [project]",
	Short: "Remove um repositório do projeto",
	Args:  cobra.MaximumNArgs(2),
	Run: func(cmd *cobra.Command, args []string) {
		var repo string
		if len(args) > 0 {
			repo = args[0]
		} else {
			fmt.Print("Digite o nome do repositório para remover: ")
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
		runRepoRemove(repo, project)
	},
}

func init() {
	repoCmd.AddCommand(repoRemoveCmd)
}

func runRepoRemove(repo, project string) {
	checkProjectAndExitIfHome(project, "repo remove")

	if err := core.RemoveRepository(project, repo); err != nil {
		log.Fatalf("❌ Erro ao remover repo no DynamoDB: %v", err)
	}

	fmt.Printf("✅ Repositório removido do registro: %s <- %s\n", repo, project)

	// Sincroniza arquivos locais
	core.SyncRepositories(project)
}
