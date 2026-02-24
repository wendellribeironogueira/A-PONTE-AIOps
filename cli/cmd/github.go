package cmd

import (
	"github.com/spf13/cobra"
)

// githubCmd represents the github command
var githubCmd = &cobra.Command{
	Use:   "github",
	Short: "Integração com GitHub",
	Long:  `Gerencia a integração entre a plataforma A-PONTE e o GitHub (Secrets, Variables, OIDC).`,
}

func init() {
	rootCmd.AddCommand(githubCmd)
}
