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

var auditCmd = &cobra.Command{
	Use:   "audit",
	Short: "Executa auditorias de segurança e conformidade",
	Args:  cobra.MaximumNArgs(1),
	Run:   runAudit,
}

var auditGitCmd = &cobra.Command{
	Use:   "git",
	Short: "Audita repositórios vinculados (Alinhamento App/Infra)",
	Args:  cobra.MaximumNArgs(1),
	Run:   runAuditGit,
}

func init() {
	rootCmd.AddCommand(auditCmd)
	auditCmd.AddCommand(auditGitCmd)
}

func runAudit(cmd *cobra.Command, args []string) {
	fmt.Println("🕵️  Iniciando Auditoria de Segurança (Infra)...")
	root := utils.GetProjectRoot()
	script := filepath.Join(root, "core", "agents", "auditor.py")

	// FIX: Integração de contexto (SOLID/DRY)
	project := resolveProjectContext(args)
	projData, _ := core.GetProject(project)
	injectProjectEnv(project, projData)

	c := exec.Command(getPythonBinary(), script)
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	c.Stdin = os.Stdin
	c.Env = getPythonEnv(root)

	if err := c.Run(); err != nil {
		fmt.Printf("❌ Erro na auditoria: %v\n", err)
		os.Exit(1)
	}
}

func runAuditGit(cmd *cobra.Command, args []string) {
	fmt.Println("🐙 Iniciando Auditoria de Repositórios (Git)...")
	root := utils.GetProjectRoot()
	script := filepath.Join(root, "core", "tools", "git_auditor.py")

	// FIX: Integração de contexto (SOLID/DRY)
	project := resolveProjectContext(args)
	projData, _ := core.GetProject(project)
	injectProjectEnv(project, projData)

	// --local project audita todos os repos vinculados ao projeto atual
	c := exec.Command(getPythonBinary(), script, "--local", "project")
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	c.Stdin = os.Stdin
	c.Env = getPythonEnv(root)

	if err := c.Run(); err != nil {
		fmt.Printf("❌ Erro na auditoria git: %v\n", err)
		os.Exit(1)
	}
}
