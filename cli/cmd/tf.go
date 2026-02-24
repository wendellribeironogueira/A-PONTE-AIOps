package cmd

import (
	"fmt"
	"os"
	"path/filepath"
	"time"

	"aponte/cli/internal/core"
	"aponte/cli/internal/utils"

	"github.com/spf13/cobra"
)

var tfCmd = &cobra.Command{
	Use:   "tf",
	Short: "Utilitários para Terraform com Auto-Healing",
	Long: `Wrapper avançado para Terraform e Terragrunt.

Funcionalidades:
  - Execução isolada via container MCP (Model Context Protocol)
  - Auto-Healing: Tenta corrigir erros comuns (lock, cache corrompido) automaticamente
  - Gerenciamento de Backend S3/DynamoDB
  - Suporte a múltiplos ambientes via Contexto de Projeto`,
}

var tfGenBackendCmd = &cobra.Command{
	Use:   "gen-backend",
	Short: "Gera arquivo backend.tf para estado remoto",
	Run:   runTfGenBackend,
}

var tfInitCmd = &cobra.Command{
	Use:   "init [project]",
	Short: "Inicializa o Terraform/Terragrunt",
	Run: func(cmd *cobra.Command, args []string) {
		runTfCommand("init", args)
	},
}

var tfPlanCmd = &cobra.Command{
	Use:   "plan [project]",
	Short: "Executa o plan do Terraform",
	Run: func(cmd *cobra.Command, args []string) {
		runTfCommand("plan", args)
	},
}

var tfApplyCmd = &cobra.Command{
	Use:   "apply [project]",
	Short: "Aplica as mudanças (Deploy)",
	Run: func(cmd *cobra.Command, args []string) {
		runTfCommand("apply", args, "-auto-approve")
	},
}

var tfDestroyCmd = &cobra.Command{
	Use:   "destroy [project]",
	Short: "Destrói a infraestrutura",
	Run: func(cmd *cobra.Command, args []string) {
		runTfCommand("destroy", args, "-auto-approve")
	},
}

var tfOutputCmd = &cobra.Command{
	Use:   "output [project]",
	Short: "Exibe outputs do Terraform",
	Run: func(cmd *cobra.Command, args []string) {
		runTfCommand("output", args, "-json")
	},
}

var (
	backendBucket string
	backendKey    string
	backendRegion string
	backendTable  string
)

func init() {
	rootCmd.AddCommand(tfCmd)
	tfCmd.AddCommand(tfGenBackendCmd)
	tfCmd.AddCommand(tfInitCmd)
	tfCmd.AddCommand(tfPlanCmd)
	tfCmd.AddCommand(tfApplyCmd)
	tfCmd.AddCommand(tfDestroyCmd)
	tfCmd.AddCommand(tfOutputCmd)

	tfGenBackendCmd.Flags().StringVar(&backendBucket, "bucket", "", "Bucket S3 de Estado")
	tfGenBackendCmd.Flags().StringVar(&backendKey, "key", "", "Chave (Path) do Estado")
	tfGenBackendCmd.Flags().StringVar(&backendRegion, "region", "", "Região AWS")
	tfGenBackendCmd.Flags().StringVar(&backendTable, "table", "", "Tabela DynamoDB de Lock")
}

func runTfGenBackend(cmd *cobra.Command, args []string) {
	content := fmt.Sprintf(`terraform {
  backend "s3" {
    bucket = "%s"
    key = "%s"
    region = "%s"
    dynamodb_table = "%s"
    encrypt = true
  }
}`, backendBucket, backendKey, backendRegion, backendTable)

	if err := os.WriteFile("backend.tf", []byte(content), 0644); err != nil {
		fmt.Printf("❌ Erro ao gerar backend.tf: %v\n", err)
		os.Exit(1)
	}
}

func runTfCommand(action string, args []string, extraArgs ...string) {
	project := resolveProjectContext(args)

	if project == "home" {
		fmt.Println("❌ Erro: Selecione um projeto para executar comandos Terraform.")
		os.Exit(1)
	}

	dir := resolveTfDir(project)
	root := utils.GetProjectRoot()

	// UX: Verifica se terragrunt.hcl existe antes de subir o container
	hclPath := filepath.Join(root, dir, "terragrunt.hcl")
	if _, err := os.Stat(hclPath); os.IsNotExist(err) {
		fmt.Printf("❌ ERRO: Arquivo de configuração não encontrado: %s\n", hclPath)
		fmt.Println("   Certifique-se de que o projeto foi criado corretamente (aponte project create).")
		os.Exit(1)
	}

	// FIX: Injeta variáveis de contexto (Environment, Repos, etc)
	// Isso garante paridade com 'deploy' e 'drift', evitando falhas por falta de variáveis.
	projData, _ := core.GetProject(project)
	// Chama injectProjectEnv incondicionalmente. Se projData for nil, ele define ao menos o TF_VAR_project_name.
	injectProjectEnv(project, projData)

	fmt.Printf("🚀 Executando Terraform %s para projeto: %s\n", action, project)

	tfArgs := []string{action}
	tfArgs = append(tfArgs, extraArgs...)

	if err := execWithHealing(root, dir, action, tfArgs); err != nil {
		os.Exit(1)
	}
}

// execWithHealing encapsula a lógica de execução do Terraform com tentativas de auto-recuperação
func execWithHealing(root, dir, action string, args []string) error {
	absDir := filepath.Join(root, dir)

	// 1. Tentativa Normal
	fullArgs := []string{"terragrunt"}
	fullArgs = append(fullArgs, args...)
	cmd := execMCPWithProjectEnv(absDir, fullArgs...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	if err := cmd.Run(); err == nil {
		return nil
	}

	// Falha detectada: Inicia protocolo de Auto-Healing
	fmt.Printf("\n⚠️  Falha no Terraform %s. Tentando auto-cura...\n", action)

	// Guardrail: Evita auto-cura destrutiva em comandos de leitura
	if action == "plan" || action == "output" || action == "validate" {
		return fmt.Errorf("auto-cura ignorada para comando de leitura (exit code não-zero)")
	}

	// 2. Limpeza de Cache
	fmt.Println("🧹 Limpando caches locais...")
	targets := []string{".terraform", ".terragrunt-cache"}
	for _, t := range targets {
		os.RemoveAll(filepath.Join(absDir, t))
	}

	// 3. Re-Init (se não for o próprio init)
	if action != "init" {
		fmt.Println("⚙️  Executando re-init forçado...")
		initCmd := execMCPWithProjectEnv(absDir, "terragrunt", "init", "-reconfigure")
		initCmd.Stdout = os.Stdout
		initCmd.Stderr = os.Stderr
		if err := initCmd.Run(); err != nil {
			fmt.Printf("❌ Falha no re-init: %v\n", err)
			return err
		}
	}

	// 4. Retry Final
	fmt.Println("🔄 Retentando comando original...")
	time.Sleep(1 * time.Second)
	cmdRetry := execMCPWithProjectEnv(absDir, fullArgs...)
	cmdRetry.Stdout = os.Stdout
	cmdRetry.Stderr = os.Stderr
	if err := cmdRetry.Run(); err != nil {
		fmt.Printf("❌ Falha no Terraform %s após auto-cura: %v\n", action, err)
		return err
	}
	fmt.Println("✅ Recuperado com sucesso!")
	return nil
}

func resolveTfDir(project string) string {
	if project == "a-ponte" {
		root := utils.GetProjectRoot()
		if _, err := os.Stat(filepath.Join(root, "projects", "a-ponte")); err == nil {
			return filepath.Join("projects", "a-ponte")
		}
		return filepath.Join("infrastructure", "bootstrap")
	}
	return filepath.Join("projects", project)
}
