package cmd

import (
	"fmt"
	"log"
	"path/filepath"

	"aponte/cli/internal/utils"

	"github.com/spf13/cobra"
)

var projectBackupCmd = &cobra.Command{
	Use:   "backup [name]",
	Short: "Faz backup do arquivo de configuração do projeto",
	Args:  cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		project := resolveProjectContext(args)
		runProjectBackup(project)
	},
}

func init() {
	projectCmd.AddCommand(projectBackupCmd)
}

func runProjectBackup(name string) {
	checkProjectAndExitIfHome(name, "project backup")

	root := utils.GetProjectRoot()
	srcPath := filepath.Join(root, "projects", name, name+".project.yml")

	backupPath, err := utils.VersionFile(srcPath, name, "manual_backup")
	if err != nil {
		log.Fatalf("❌ Erro ao fazer backup: %v", err)
	}
	if backupPath == "" {
		log.Fatalf("❌ Arquivo de configuração não encontrado: %s", srcPath)
	}

	fmt.Printf("✅ Backup realizado com sucesso: %s\n", backupPath)
}
