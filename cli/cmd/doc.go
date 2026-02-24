package cmd

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"aponte/cli/internal/core"
	"aponte/cli/internal/utils"

	"github.com/spf13/cobra"
)

var docCmd = &cobra.Command{
	Use:   "doc",
	Short: "Gera documentação automática (DocBot)",
	Run:   runDoc,
}

func init() {
	aiCmd.AddCommand(docCmd)
}

func runDoc(cmd *cobra.Command, args []string) {
	root := utils.GetProjectRoot()
	scriptPath := filepath.Join(root, "core", "tools", "doc_bot.py")

	if _, err := os.Stat(scriptPath); os.IsNotExist(err) {
		fmt.Printf("❌ Erro: Script DocBot não encontrado em: %s\n", scriptPath)
		os.Exit(1)
	}

	pythonBin := getPythonBinary()

	// FIX: Injeta contexto para que o DocBot documente o projeto correto
	if project, err := core.GetContext(); err == nil && project != "" && project != "home" {
		projData, _ := core.GetProject(project)
		injectProjectEnv(project, projData)
	}

	fmt.Println("📝 Gerando documentação...")
	c := exec.Command(pythonBin, scriptPath)
	c.Stdout, c.Stderr, c.Stdin = os.Stdout, os.Stderr, os.Stdin
	c.Env = getPythonEnv(root)

	if err := c.Run(); err != nil {
		os.Exit(1)
	}
}
