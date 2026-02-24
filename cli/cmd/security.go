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

var securityCmd = &cobra.Command{
	Use:   "security",
	Short: "Ferramentas de segurança (TFSec, Trivy, Prowler)",
	Long: `Suite de segurança integrada.

Ferramentas:
  - TFSec: Análise estática de IaC
  - Trivy: Scanner de vulnerabilidades em containers e filesystem
  - Prowler: Auditoria de conformidade AWS (CIS, GDPR, HIPAA)
  - Audit: Varredura unificada com relatório JSON`,
}

var tfsecCmd = &cobra.Command{
	Use:   "tfsec",
	Short: "Executa TFSec",
	Run:   runTfsec,
}

var trivyCmd = &cobra.Command{
	Use:   "trivy",
	Short: "Executa Trivy",
	Run:   runTrivy,
}

var prowlerCmd = &cobra.Command{
	Use:   "prowler",
	Short: "Executa Prowler (Auditoria AWS)",
	Run:   runProwler,
}

var scanAllCmd = &cobra.Command{
	Use:   "audit",
	Short: "Executa varredura completa de segurança e salva JSON",
	Args:  cobra.MaximumNArgs(1),
	Run:   runScanAll,
}

var reportCmd = &cobra.Command{
	Use:   "report",
	Short: "Gera relatório visual de segurança (Tabela TUI)",
	Run:   runReport,
}

var gitAuditCmd = &cobra.Command{
	Use:   "git-audit",
	Short: "Auditoria de repositórios Git (Sandbox)",
	Run:   runGitAudit,
}

func init() {
	rootCmd.AddCommand(securityCmd)
	securityCmd.AddCommand(tfsecCmd)
	securityCmd.AddCommand(trivyCmd)
	securityCmd.AddCommand(prowlerCmd)
	securityCmd.AddCommand(scanAllCmd)
	securityCmd.AddCommand(reportCmd)
	securityCmd.AddCommand(gitAuditCmd)
}

func getProjectContext(root string) (string, string) {
	project, err := core.GetContext()
	if err != nil || project == "" {
		project = "home"
	}
	if project == "home" {
		return "", ""
	}
	tfDir := filepath.Join(root, resolveTfDir(project))
	return project, tfDir
}

func runTfsec(cmd *cobra.Command, args []string) {
	root := utils.GetProjectRoot()
	project, tfDir := getProjectContext(root)
	if tfDir == "" {
		fmt.Println("❌ Erro: Selecione um projeto.")
		os.Exit(1)
	}

	// FIX: Injeta contexto (DRY/Integration)
	projData, _ := core.GetProject(project)
	injectProjectEnv(project, projData)

	fmt.Println("🛡️  Executando TFSec...")
	c := execMCPWithProjectEnv(tfDir, "tfsec", ".")
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr

	if err := c.Run(); err != nil {
		fmt.Printf("❌ Erro ao executar TFSec: %v\n", err)
		os.Exit(1)
	}
}

func runGitAudit(cmd *cobra.Command, args []string) {
	project := resolveProjectContext(args)
	checkProjectAndExitIfHome(project, "security git-audit")

	// FIX: Injeta contexto do projeto (DRY) para garantir que o auditor saiba o ambiente
	projData, _ := core.GetProject(project)
	injectProjectEnv(project, projData)

	fmt.Println("🐙 Auditando Git (Sandbox)...")

	// Usa ExecMCP para rodar dentro do container com as variáveis corretas
	// O ExecMCP já deve tratar montagem de volumes e credenciais AWS básicas
	// FIX: Usa GetProjectRoot() em vez de "." para garantir que o container monte a raiz e encontre o script core/
	// FIX: Injeta variáveis de ambiente explicitamente via 'env' para garantir que existam DENTRO do container
	c := execPythonInMCP("core/tools/git_auditor.py")

	c.Stdout = os.Stdout
	c.Stderr = os.Stderr

	if err := c.Run(); err != nil {
		fmt.Printf("❌ Erro na auditoria Git: %v\n", err)
		os.Exit(1)
	}
}

func runScanAll(cmd *cobra.Command, args []string) {
	project := resolveProjectContext(args)

	// FIX: Injeta contexto (DRY) para o ingestor de segurança
	projData, _ := core.GetProject(project)
	injectProjectEnv(project, projData)

	fmt.Println("🛡️  Iniciando varredura unificada (A-PONTE Security)...")

	// Executa o script Python dentro do container MCP para garantir ambiente consistente
	// python3 core/services/security_ingestor.py --project <project> --dir . --output security_report.json
	// FIX: Injeta variáveis de ambiente explicitamente via 'env' para garantir que existam DENTRO do container
	c := execPythonInMCP("core/services/security_ingestor.py",
		"--project", project,
		"--dir", ".",
		"--output", "security_report.json")

	c.Stdout = os.Stdout
	c.Stderr = os.Stderr

	if err := c.Run(); err != nil {
		fmt.Printf("❌ Erro na varredura: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("✅ Relatório salvo em security_report.json")
}

func runReport(cmd *cobra.Command, args []string) {
	// Garante que o scan foi executado antes de gerar o relatório
	runScanAll(cmd, args)

	root := utils.GetProjectRoot()
	scriptPath := filepath.Join(root, "core", "tools", "security_report.py")

	if _, err := os.Stat(scriptPath); os.IsNotExist(err) {
		fmt.Printf("❌ Script não encontrado: %s\n", scriptPath)
		os.Exit(1)
	}

	pythonBin := getPythonBinary()

	// FIX: Usa caminho absoluto para o relatório, garantindo que seja encontrado mesmo rodando de subdiretórios
	reportFile := filepath.Join(root, "security_report.json")
	c := exec.Command(pythonBin, scriptPath, "--file", reportFile)
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	c.Env = getPythonEnv(root)

	if err := c.Run(); err != nil {
		fmt.Printf("❌ Erro ao gerar relatório: %v\n", err)
		os.Exit(1)
	}
}

func runTrivy(cmd *cobra.Command, args []string) {
	root := utils.GetProjectRoot()
	project, tfDir := getProjectContext(root)
	if tfDir == "" {
		fmt.Println("❌ Erro: Selecione um projeto.")
		os.Exit(1)
	}

	// FIX: Injeta contexto (DRY/Integration)
	projData, _ := core.GetProject(project)
	injectProjectEnv(project, projData)

	fmt.Println("🛡️  Executando Trivy...")
	c := execMCPWithProjectEnv(tfDir, "trivy", "config", ".")
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr

	if err := c.Run(); err != nil {
		fmt.Printf("❌ Erro ao executar Trivy: %v\n", err)
		os.Exit(1)
	}
}

func runProwler(cmd *cobra.Command, args []string) {
	root := utils.GetProjectRoot()

	fmt.Println("🛡️  Executando Prowler (AWS Security Audit)...")
	c := execMCPWithProjectEnv(root, "prowler", "aws")
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr

	if err := c.Run(); err != nil {
		fmt.Printf("❌ Erro ao executar Prowler: %v\n", err)
		os.Exit(1)
	}
}
