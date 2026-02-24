package cmd

import (
	"aponte/cli/internal/utils"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
)

var contextCmd = &cobra.Command{
	Use:   "context",
	Short: "Gerencia o contexto da sessão (Projeto Ativo)",
}

var contextShowCmd = &cobra.Command{
	Use:   "show",
	Short: "Exibe o projeto atualmente ativo",
	Run:   runContextShow,
}

func init() {
	rootCmd.AddCommand(contextCmd)
	contextCmd.AddCommand(contextShowCmd)
}

func runContextShow(cmd *cobra.Command, args []string) {
	// 1. Prioridade: Variável de Ambiente (Injeção do Wrapper)
	if env := os.Getenv("TF_VAR_project_name"); env != "" {
		fmt.Println(env)
		return
	}

	// 2. Persistência em Disco (.aponte/context)
	root := utils.GetProjectRoot()
	contextFile := filepath.Join(root, ".aponte", "context")

	content, err := os.ReadFile(contextFile)
	if err != nil {
		fmt.Println("home") // Default seguro
		return
	}
	fmt.Println(strings.TrimSpace(string(content)))
}
