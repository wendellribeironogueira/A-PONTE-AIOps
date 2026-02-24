package cmd

import (
	"log"

	"aponte/cli/internal/core"

	"github.com/spf13/cobra"
)

var repoSyncCmd = &cobra.Command{
	Use:   "sync [project]",
	Short: "Sincroniza arquivos locais com o registro na nuvem",
	Args:  cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		projectName := resolveProjectContext(args)
		runRepoSync(projectName)
	},
}

func init() {
	repoCmd.AddCommand(repoSyncCmd)
}

func runRepoSync(projectName string) {
	checkProjectAndExitIfHome(projectName, "repo sync")

	if err := core.SyncRepositories(projectName); err != nil {
		log.Fatalf("❌ Erro ao sincronizar repositórios: %v", err)
	}
}
