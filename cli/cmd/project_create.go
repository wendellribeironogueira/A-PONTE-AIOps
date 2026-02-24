package cmd

import (
	"aponte/cli/internal/core"
	"aponte/cli/internal/utils"
	"bufio"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
)

var (
	createEnv      string
	createScaffold bool
	createEmail    string
)

var projectCreateCmd = &cobra.Command{
	Use:   "create [name]",
	Short: "Cria um novo projeto",
	Long: `Cria um novo projeto na plataforma A-PONTE.

O processo inclui:
  1. Registro de metadados no DynamoDB (Multi-Tenant)
  2. Seleção interativa de ambiente (Dev, Staging, Prod)
  3. Geração de arquivos de configuração locais (.project.yml, .repos)
  4. Scaffold opcional de estrutura de pastas e código inicial`,
	Args: cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		var name string
		if len(args) > 0 {
			name = args[0]
		} else {
			name = utils.Prompt("Nome do Projeto (slug):")
		}
		if name != "" {
			runCreateProject(name)
		}
	},
}

func init() {
	projectCreateCmd.Flags().StringVar(&createEnv, "env", "", "Ambiente (development, staging, production)")
	projectCreateCmd.Flags().BoolVar(&createScaffold, "scaffold", false, "Gera estrutura de pastas (Scaffold) automaticamente")
	projectCreateCmd.Flags().StringVar(&createEmail, "email", "", "E-mail do responsável")
	projectCmd.AddCommand(projectCreateCmd)
}

func runCreateProject(name string) {

	normalizedName := utils.NormalizeProjectName(name)
	if normalizedName != name {
		fmt.Printf("⚠️  Nome ajustado para padrão slug: '%s' -> '%s'\n", name, normalizedName)
		name = normalizedName
	}

	// 2. Verifica existência no DynamoDB
	existingProject, err := core.GetProject(name)
	if err != nil {
		log.Fatalf("❌ Erro ao verificar projeto: %v", err)
	}

	// Se já existe, apenas hidrata localmente (Idempotência)
	if existingProject != nil {
		log.Printf("⚠️  Projeto já existe no registro: %s", name)
		core.HydrateLocalFiles(existingProject)
		return
	}

	// 4. Seleção de Ambiente (Interativo)
	envName, isProd := selectEnvironment(createEnv)

	// 4.1. Coleta de E-mail (Fix Hardcoding)
	email := os.Getenv("TF_VAR_security_email")
	if createEmail != "" {
		email = createEmail
	}

	if email == "" {
		if os.Getenv("FORCE_NON_INTERACTIVE") != "true" {
			email = utils.Prompt("📧 Digite o e-mail do responsável (para alertas):")
		}
		if email == "" {
			log.Fatal("❌ O e-mail é obrigatório para criar o projeto.")
		}
	}

	// 4.5. Enforce de Nomenclatura (Fix GAP-02: Colisão de Ambientes)
	// Se o ambiente não estiver no nome do projeto, sugere/adiciona para evitar colisão no DynamoDB.
	if envName != "development" && !strings.Contains(name, envName) {
		newName := fmt.Sprintf("%s-%s", name, envName)
		fmt.Printf("ℹ️  Ajustando nome do projeto para incluir ambiente: '%s' -> '%s'\n", name, newName)
		name = newName

		// RE-CHECK: Verifica se o novo nome já existe (evita colisão/erro de duplicação)
		if existing, _ := core.GetProject(name); existing != nil {
			log.Printf("⚠️  Projeto '%s' já existe no registro.", name)
			core.HydrateLocalFiles(existing)
			return
		}
	}

	// FIX: Usa injectProjectEnv para garantir consistência de contexto (DRY/Integration)
	// MOVED: Injeta APÓS a normalização do nome para garantir que TF_VAR_project_name esteja correto
	projData := &core.Project{
		Name:          name,
		Environment:   envName,
		SecurityEmail: email,
	}
	injectProjectEnv(name, projData)

	// 4.6. Definição de Defaults para o Tenant (Sem perguntas interativas)
	appName := name // O próprio nome do projeto é o "App" container
	resourceName := "tenant-root"

	// 5. Registro de metadados (Item) no DynamoDB (A tabela é gerenciada via Terraform)
	err = core.CreateProject(core.Project{
		Name:          name,
		Environment:   envName,
		IsProduction:  isProd,
		SecurityEmail: email,
		AppName:       appName,
		ResourceName:  resourceName,
	})
	if err != nil {
		log.Fatalf("❌ Falha ao criar projeto no DynamoDB: %v", err)
	}

	// 6. Criação de Arquivos Locais
	core.CreateLocalFiles(name, envName, isProd, email, appName, resourceName)

	// 7. Scaffold (Opcional)
	if createScaffold || (os.Getenv("FORCE_NON_INTERACTIVE") != "true" && shouldRunScaffold()) {
		if err := runScaffold(name, envName, appName, resourceName); err != nil {
			fmt.Printf("⚠️  Aviso: O projeto foi criado, mas o scaffold falhou: %v\n", err)
			fmt.Printf("   👉 Para tentar novamente: aponte project scaffold %s\n", name)

			fmt.Println("↺ Revertendo criação do projeto no registro (Rollback)...")
			if errDel := core.DeleteProject(name); errDel != nil {
				fmt.Printf("❌ Falha no rollback: %v\n", errDel)
			} else {
				cleanupLocalFiles(name)
				fmt.Println("✅ Rollback concluído. Projeto e arquivos de configuração removidos.")
			}
			// Encerra com erro para evitar falso positivo em scripts de automação
			os.Exit(1)
		}
	}

	fmt.Printf("\n✅ Projeto criado com sucesso: %s\n", name)
}

func shouldRunScaffold() bool {
	fmt.Println("")
	return utils.ConfirmAction("🚀 Deseja gerar a estrutura padrão de pastas (src/, docs/, README)? [s/N]")
}

func cleanupLocalFiles(name string) {
	projectsDir := filepath.Join(utils.GetProjectRoot(), "projects")
	os.RemoveAll(filepath.Join(projectsDir, name))
	os.Remove(filepath.Join(projectsDir, name+".repos"))
	os.Remove(filepath.Join(projectsDir, name+".auto.tfvars"))
	os.Remove(filepath.Join(projectsDir, name+".project.yml"))
}

func selectEnvironment(flagEnv string) (string, bool) {
	envName := "development"
	isProd := false

	// Prioridade para Flag
	if flagEnv != "" {
		switch flagEnv {
		case "staging":
			return "staging", false
		case "production":
			return "production", true
		default:
			return "development", false
		}
	}

	// Pula interação se FORCE_NON_INTERACTIVE estiver setado (CI/CD)
	if os.Getenv("FORCE_NON_INTERACTIVE") != "true" {
		fmt.Println("\nSelecione o ambiente do projeto:")
		fmt.Println("  1) Development (Padrão)")
		fmt.Println("  2) Staging")
		fmt.Println("  3) Production (Proteção Máxima)")
		fmt.Print("Opção [1]: ")

		reader := bufio.NewReader(os.Stdin)
		input, _ := reader.ReadString('\n')
		input = strings.TrimSpace(input)

		switch input {
		case "2":
			envName = "staging"
			fmt.Println("Configurando projeto como STAGING")
		case "3":
			envName = "production"
			isProd = true
			fmt.Println("🔒 Configurando projeto como PRODUÇÃO")
		default:
			fmt.Println("Configurando projeto como DESENVOLVIMENTO")
		}
	}
	return envName, isProd
}

func runScaffold(name, env, app, resource string) error {
	root := utils.GetProjectRoot()
	script := filepath.Join(root, "core", "tools", "scaffold.py")
	region := utils.GetRegion()

	if _, err := os.Stat(script); os.IsNotExist(err) {
		return fmt.Errorf("script de scaffold não encontrado em: %s", script)
	}

	// Detecta interpretador Python (python3 ou python)
	pythonBin := getPythonBinary()

	// Chama o script Python passando os argumentos
	cmd := exec.Command(pythonBin, script,
		fmt.Sprintf("name=%s", name),
		fmt.Sprintf("environment=%s", env),
		fmt.Sprintf("app_name=%s", app),
		fmt.Sprintf("resource_name=%s", resource),
		fmt.Sprintf("aws_region=%s", region))
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Stdin = os.Stdin
	// FIX: Usa getPythonEnv para garantir APONTE_ROOT e PYTHONPATH (DRY)
	cmd.Env = getPythonEnv(root)

	if err := cmd.Run(); err != nil {
		return err
	}
	return nil
}
