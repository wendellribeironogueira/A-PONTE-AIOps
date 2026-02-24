package cmd

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	"aponte/cli/internal/core"
	"aponte/cli/internal/utils"

	"github.com/spf13/cobra"
)

var projectDestroyCmd = &cobra.Command{
	Use:   "destroy [name]",
	Short: "Destrói um projeto (Infraestrutura + Configuração)",
	Long:  `Executa o terraform destroy, remove o registro do DynamoDB e apaga arquivos locais.`,
	Args:  cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		projectName := resolveProjectContext(args)
		runDestroyProject(projectName)
	},
}

func init() {
	projectCmd.AddCommand(projectDestroyCmd)
}

func runDestroyProject(name string) {
	// 1. Guardrail inicial
	checkProjectAndExitIfHome(name, "project destroy")

	// 2. Guardrails (Proteção)
	// Lê configuração local para saber se é produção
	isProd := false
	var projData *core.Project
	if p, err := core.GetProject(name); err == nil && p != nil {
		isProd = p.IsProduction
		projData = p
	}

	if name == "a-ponte" {
		fmt.Println("\n⚠️  PERIGO: Você está tentando destruir o NÚCLEO (A-PONTE).")
		fmt.Println("   Isso removerá toda a governança e automação.")
		if !utils.ConfirmAction("Tem certeza absoluta que deseja continuar? [s/N]") {
			fmt.Println("❌ Operação cancelada.")
			return
		}
		os.Setenv("ALLOW_APONTE_MODIFICATIONS", "true")
	}

	if isProd {
		fmt.Println("\n🔒 Este é um projeto de PRODUÇÃO.")
		if os.Getenv("ALLOW_PRODUCTION_DESTROY") != "true" {
			log.Fatal("❌ Proteção de Produção Ativa! Defina ALLOW_PRODUCTION_DESTROY=true para continuar.")
		}
	}

	// 3. Confirmação Final
	fmt.Printf("\n🧨 ATENÇÃO: Esta ação é DESTRUTIVA e IRREVERSÍVEL para: %s\n", name)
	fmt.Println("   1. Backup do estado será criado")
	fmt.Println("   2. Terraform Destroy será executado")
	fmt.Println("   3. Registro no DynamoDB será removido")
	fmt.Println("   4. Arquivos locais serão deletados")

	if !utils.ConfirmAction(fmt.Sprintf("Digite '%s' para confirmar a destruição:", name), name) {
		fmt.Println("❌ Operação cancelada.")
		return
	}

	// Configura ambiente para todas as operações subsequentes (Init, Backup, Destroy)
	// FIX: Injeta variáveis de contexto (Environment, Repos) para garantir que o destroy tenha os dados corretos
	injectProjectEnv(name, projData)
	os.Setenv("TF_VAR_aws_region", utils.GetRegion())
	os.Setenv("TF_VAR_create_global_resources", "false")
	os.Setenv("TF_VAR_is_aponte", "false")

	// 3.5. Inicialização (Auto-Healing do Backend)
	// Garante que o backend esteja configurado para o projeto atual antes de qualquer operação
	fmt.Println("\n⚙️  Inicializando Terraform (Reconfigure)...")
	root := utils.GetProjectRoot()
	tfDir := resolveTfDir(name)
	absTfDir := filepath.Join(root, tfDir)
	skipDestroy := false
	initCmd := execMCPWithProjectEnv(absTfDir, "terragrunt", "init", "-reconfigure")
	if out, err := initCmd.CombinedOutput(); err != nil {
		// Se o bucket não existe, o init falha. Isso significa que não há estado remoto.
		// Nesse caso, podemos pular o backup e o destroy do terraform, focando na limpeza local.
		if strings.Contains(string(out), "does not exist") || strings.Contains(string(out), "NoSuchBucket") {
			log.Printf("⚠️  Backend S3 não encontrado. Assumindo que não há infraestrutura para destruir.")
			skipDestroy = true
		} else {
			log.Printf("⚠️  Aviso: Falha no init (pode ser ignorado se o backend não existir):\n%s", string(out))
		}
	}

	if !skipDestroy {
		// 4. Backup do Estado
		fmt.Println("\n📦 Criando backup do estado...")
		if err := backupState(name); err != nil {
			log.Printf("⚠️  Falha no backup: %v", err)
			if !utils.ConfirmAction("Deseja continuar sem backup? [s/N]") {
				fmt.Println("❌ Operação cancelada.")
				return
			}
		} else {
			fmt.Println("✅ Backup realizado com sucesso.")
		}

		// 5. Terraform Destroy
		fmt.Println("\n🔥 Executando Terraform Destroy...")
		{
			cmd := execMCPWithProjectEnv(absTfDir, "terragrunt", "destroy", "-auto-approve")
			cmd.Stdout = os.Stdout
			cmd.Stderr = os.Stderr
			if err := cmd.Run(); err != nil {
				log.Printf("❌ Falha no Terraform Destroy: %v", err)
				fmt.Println("⚠️  A infraestrutura pode não ter sido totalmente removida.")
				if !utils.ConfirmAction("Deseja forçar a limpeza dos arquivos locais e registro? [s/N]") {
					fmt.Println("❌ Operação cancelada.")
					return
				}
			} else {
				fmt.Println("✅ Infraestrutura destruída.")
			}
		}
	}

	// 6. Remove do DynamoDB
	fmt.Println("🗑️  Removendo do registro...")
	if err := core.DeleteProject(name); err != nil {
		log.Printf("⚠️  Erro ao remover do DynamoDB: %v", err)
	}

	// 7. Limpeza Local
	fmt.Println("🧹 Limpando arquivos locais...")
	cleanupProjectFiles(name)

	// Reset context se necessário
	current, _ := core.GetPersistedContext()
	if current == name {
		core.SetContext("home")
		fmt.Println("✅ Contexto resetado para 'home'")
	}

	fmt.Printf("\n💀 Projeto %s destruído com sucesso.\n", name)
}

func cleanupProjectFiles(name string) {
	projectsDir := filepath.Join(utils.GetProjectRoot(), "projects")
	files := []string{
		filepath.Join(projectsDir, name+".repos"),
		filepath.Join(projectsDir, name+".auto.tfvars"),
		filepath.Join(projectsDir, name+".project.yml"),
	}
	for _, f := range files {
		// SAFETY NET: Backup de arquivos de configuração antes da deleção
		utils.VersionFile(f, name, "pre_destroy_config")
		os.Remove(f)
	}

	// Remove o diretório do projeto (Limpeza completa)
	projectPath := filepath.Join(projectsDir, name)

	// SAFETY NET: Backup recursivo de todo o código do projeto antes de deletar a pasta
	filepath.WalkDir(projectPath, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() {
			// OTIMIZAÇÃO: Ignora diretórios pesados/inúteis para backup de segurança
			if d.Name() == ".terraform" || d.Name() == ".git" || d.Name() == "node_modules" || d.Name() == "venv" || d.Name() == "__pycache__" {
				return filepath.SkipDir
			}
		} else {
			utils.VersionFile(path, name, "pre_destroy_code")
		}
		return nil
	})

	os.RemoveAll(projectPath)
}

func backupState(name string) error {
	root := utils.GetProjectRoot()
	backupDir := filepath.Join(root, ".aponte-versions", "states", name, time.Now().Format("20060102-150405"))
	if err := os.MkdirAll(backupDir, 0755); err != nil {
		return err
	}

	backupFile := filepath.Join(backupDir, "terraform.tfstate")
	file, err := os.Create(backupFile)
	if err != nil {
		return err
	}

	// Garante limpeza em caso de falha (evita arquivo vazio/corrompido)
	success := false
	defer func() {
		file.Close()
		if !success {
			os.Remove(backupFile)
		}
	}()

	// Puxa estado remoto
	tfDir := resolveTfDir(name)
	absTfDir := filepath.Join(root, tfDir)
	cmd := execMCPWithProjectEnv(absTfDir, "terragrunt", "state", "pull")
	cmd.Stdout = file

	if err := cmd.Run(); err != nil {
		return err
	}

	success = true
	return nil
}
