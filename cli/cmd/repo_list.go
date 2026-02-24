package cmd

import (
	"fmt"
	"log"

	"aponte/cli/internal/core"

	"github.com/spf13/cobra"
)

var repoListCmd = &cobra.Command{
	Use:   "list [project]",
	Short: "Lista repositórios vinculados a um projeto",
	Args:  cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		projectName := resolveProjectContext(args)
		runListRepos(projectName)
	},
}

func init() {
	repoCmd.AddCommand(repoListCmd)
}

func runListRepos(projectName string) {
	checkProjectAndExitIfHome(projectName, "repo list")

	repos, err := core.ListRepositories(projectName)
	if err != nil {
		log.Fatalf("❌ Erro ao listar repositórios: %v", err)
	}

	fmt.Printf("\n📦 Repositórios vinculados a '%s':\n\n", projectName)

	if len(repos) == 0 {
		fmt.Println("  (nenhum repositório vinculado)")
	} else {
		for _, repo := range repos {
			fmt.Printf("  ✓ %s\n", repo)
		}
	}
	fmt.Println("")
}
