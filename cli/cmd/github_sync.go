package cmd

import (
	"aponte/cli/internal/integrations"

	"github.com/spf13/cobra"
)

var githubSyncCmd = &cobra.Command{
	Use:   "sync [project]",
	Short: "Sincroniza secrets e variáveis do GitHub",
	Args:  cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		project := resolveProjectContext(args)
		runGithubSync(project)
	},
}

func init() {
	githubCmd.AddCommand(githubSyncCmd)
}

func runGithubSync(project string) {
	checkProjectAndExitIfHome(project, "github sync")
	integrations.SyncSecrets(project)
}
