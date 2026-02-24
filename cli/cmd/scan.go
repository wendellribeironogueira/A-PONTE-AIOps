package cmd

import (
	"fmt"
	"os"
	"path/filepath"

	"aponte/cli/internal/core"
	"aponte/cli/internal/utils"

	"github.com/spf13/cobra"
)

var scanCmd = &cobra.Command{
	Use:   "checkov",
	Short: "Executa análise estática de segurança (Checkov)",
	Long:  `Executa o Checkov via container Docker para analisar o código Terraform do projeto atual.`,
	Run:   runScan,
}

func init() {
	securityCmd.AddCommand(scanCmd)
}

func runScan(cmd *cobra.Command, args []string) {
	project, err := core.GetContext()
	if err != nil || project == "" {
		project = "home"
	}

	if project == "home" {
		fmt.Println("❌ Erro: Selecione um projeto para escanear (aponte project switch <nome>).")
		os.Exit(1)
	}

	// FIX: Injeta contexto do projeto para garantir que o scanner tenha as variáveis corretas
	projData, _ := core.GetProject(project)
	injectProjectEnv(project, projData)

	root := utils.GetProjectRoot()
	tfDir := filepath.Join(root, resolveTfDir(project))

	fmt.Println("🛡️  Executando Checkov (Static Analysis)...")
	c := execMCPWithProjectEnv(tfDir, "checkov", "-d", ".")
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr

	if err := c.Run(); err != nil {
		fmt.Println("⚠️  Vulnerabilidades encontradas.")
		os.Exit(1)
	}
	fmt.Println("✅ Checkov finalizado com sucesso.")
}
