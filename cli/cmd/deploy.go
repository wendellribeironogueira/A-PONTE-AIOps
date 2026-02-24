package cmd

import (
	"aponte/cli/internal/core"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"aponte/cli/internal/utils"

	"github.com/spf13/cobra"
)

var deployCmd = &cobra.Command{
	Use:   "deploy",
	Short: "Gerencia deploys da infraestrutura",
}

var deployRemoteCmd = &cobra.Command{
	Use:   "remote [project]",
	Short: "Dispara deploy remoto via GitHub Actions",
	Run:   runDeployRemote,
}

var deployProjectCmd = &cobra.Command{
	Use:   "project",
	Short: "Executa o deploy (apply) do projeto atual",
	Run:   runDeployProject,
}

var deployCoreCmd = &cobra.Command{
	Use:   "core",
	Short: "Executa o deploy (bootstrap) do núcleo A-PONTE",
	Run:   runDeployCore,
}

func init() {
	rootCmd.AddCommand(deployCmd)
	deployCmd.AddCommand(deployRemoteCmd)
	deployCmd.AddCommand(deployProjectCmd)
	deployCmd.AddCommand(deployCoreCmd)
}

func runDeployRemote(cmd *cobra.Command, args []string) {
	project := resolveProjectContext(args)
	checkProjectAndExitIfHome(project, "deploy remote")

	// Validação de Segurança: Garante que o projeto existe no registro antes de disparar
	if _, err := core.GetProject(project); err != nil {
		fmt.Printf("❌ Erro: Projeto '%s' não encontrado no registro global.\n", project)
		fmt.Println("   Execute 'aponte project create' ou 'aponte project sync' primeiro.")
		os.Exit(1)
	}

	if _, err := exec.LookPath("gh"); err != nil {
		fmt.Println("❌ Erro: GitHub CLI (gh) não encontrada. Instale para continuar.")
		os.Exit(1)
	}

	fmt.Printf("🚀 Disparando workflow de deploy para o projeto %s...\n", project)

	c := exec.Command("gh", "workflow", "run", "apply-infra.yml", "--ref", "main", "-f", fmt.Sprintf("project=%s", project))
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr

	if err := c.Run(); err != nil {
		fmt.Printf("❌ Falha ao disparar workflow: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("✅ Workflow iniciado. Acompanhe com: gh run watch")
}

func runDeployProject(cmd *cobra.Command, args []string) {
	project := resolveProjectContext(args)
	checkProjectAndExitIfHome(project, "deploy project")

	// 1. Carrega metadados do projeto (DynamoDB/Cache)
	projData, err := core.GetProject(project)
	if err != nil {
		fmt.Printf("⚠️  Aviso: Não foi possível carregar metadados do projeto '%s': %v\n", project, err)
		fmt.Println("   Usando valores padrão (Environment=dev, Repos=[]).")
	}

	// 2. Injeta variáveis de contexto para o Terragrunt (root.hcl)
	injectProjectEnv(project, projData)

	fmt.Printf("🚀 Iniciando Deploy do Projeto: %s\n", project)

	root := utils.GetProjectRoot()
	projectDir := filepath.Join(root, resolveTfDir(project))

	// FIX: Injeta variáveis TF_VAR_ dentro do container via comando 'env'
	// O docker exec não herda ambiente do host automaticamente
	c := execMCPWithProjectEnv(projectDir, "terragrunt", "apply", "--terragrunt-source-update")
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	c.Stdin = os.Stdin

	if err := c.Run(); err != nil {
		fmt.Printf("❌ Erro no deploy: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("✅ Deploy concluído com sucesso!")
}

func runDeployCore(cmd *cobra.Command, args []string) {
	// FIX: Garante que o contexto seja 'a-ponte' para o bootstrap do core
	project := "a-ponte"

	// 1. Tenta carregar metadados do projeto 'a-ponte' para injetar configs globais
	projData, _ := core.GetProject(project)

	// Fallback: Se não existir no banco (bootstrap inicial), cria estrutura em memória para forçar Produção
	if projData == nil {
		projData = &core.Project{
			Name:        project,
			Environment: "production",
		}
	}
	injectProjectEnv(project, projData)

	fmt.Println("🚀 Iniciando Bootstrap/Deploy do Core (A-PONTE)...")

	root := utils.GetProjectRoot()
	// Path Fallback: Suporta estrutura legada (bootstrap) e nova (projects/a-ponte)
	projectDir := filepath.Join(root, resolveTfDir("a-ponte"))

	c := execMCPWithProjectEnv(projectDir, "terragrunt", "apply", "--terragrunt-source-update")
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	c.Stdin = os.Stdin

	if err := c.Run(); err != nil {
		fmt.Printf("❌ Erro no deploy do core: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("✅ Core atualizado com sucesso!")
}
