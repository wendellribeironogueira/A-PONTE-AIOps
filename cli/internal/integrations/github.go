package integrations

import (
	"bufio"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"aponte/cli/internal/utils"
)

type TFOutput struct {
	Value string `json:"value"`
}

// SyncSecrets sincroniza secrets e variáveis do GitHub com outputs do Terraform.
func SyncSecrets(project string) {
	// 1. Skip CI
	if os.Getenv("GITHUB_ACTIONS") == "true" {
		fmt.Println("⚠️  Execução em CI detectada. Pulando sincronização de secrets.")
		return
	}

	fmt.Printf("🔄 Sincronizando secrets para GitHub: %s\n", project)

	// 2. Verifica dependências
	if _, err := exec.LookPath("gh"); err != nil {
		log.Fatal("❌ GitHub CLI (gh) não instalado.")
	}

	// 3. Obtém Outputs do Terraform
	fmt.Println("📥 Lendo outputs do Terraform...")

	// Configura ambiente para o Terragrunt saber qual projeto olhar
	if err := os.Setenv("TF_VAR_project_name", project); err != nil {
		log.Fatalf("❌ Erro ao definir variável de ambiente TF_VAR_project_name: %v", err)
	}
	region := utils.GetRegion()
	if err := os.Setenv("TF_VAR_aws_region", region); err != nil {
		log.Fatalf("❌ Erro ao definir variável de ambiente TF_VAR_aws_region: %v", err)
	}

	// Define o diretório correto onde o Terraform/Terragrunt deve rodar
	var relTfDir string
	if project == "a-ponte" {
		relTfDir = filepath.Join("infrastructure", "bootstrap")
	} else {
		relTfDir = filepath.Join("projects", project)
	}

	cmd := utils.ExecMCP(relTfDir, "terragrunt", "output", "-json")
	outputBytes, err := cmd.Output()
	if err != nil {
		log.Printf("⚠️  Falha ao ler outputs do Terraform: %v", err)
		fmt.Println("   💡 Dica: O projeto precisa ser aplicado antes de sincronizar secrets.")
		return
	}

	var outputs map[string]TFOutput
	if err := json.Unmarshal(outputBytes, &outputs); err != nil {
		log.Fatalf("❌ Erro ao parsear JSON do Terraform: %v", err)
	}

	roleArn := outputs["github_actions_role_arn"].Value
	boundaryArn := outputs["permissions_boundary_arn"].Value
	supportArn := outputs["support_break_glass_role_arn"].Value

	if roleArn == "" {
		log.Fatal("❌ Output 'github_actions_role_arn' não encontrado.")
	}

	fmt.Printf("🔑 Role ARN: %s\n", roleArn)

	// 4. Identifica Repositórios
	repos := getReposForProject(project)
	if len(repos) == 0 {
		fmt.Println("⚠️  Nenhum repositório vinculado encontrado. Tentando configurar no repositório atual...")
		configureRepo(".", roleArn, boundaryArn, supportArn)
	} else {
		for _, repo := range repos {
			configureRepo(repo, roleArn, boundaryArn, supportArn)
		}
	}

	fmt.Println("\n✅ Sincronização concluída!")
}

func getReposForProject(project string) []string {
	reposFile := filepath.Join(utils.GetProjectRoot(), "projects", project+".repos")
	file, err := os.Open(reposFile)
	if err != nil {
		return []string{}
	}
	defer func() {
		if err := file.Close(); err != nil {
			log.Printf("⚠️  Falha ao fechar arquivo de repositórios: %v", err)
		}
	}()

	var repos []string
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line != "" && !strings.HasPrefix(line, "#") {
			repos = append(repos, line)
		}
	}
	return repos
}

func configureRepo(repo, roleArn, boundaryArn, supportArn string) {
	fmt.Printf("⚙️  Configurando: %s\n", repo)

	setSecret := func(key, value string) {
		if value == "" {
			return
		}
		args := []string{"secret", "set", key, "--body", value}
		if repo != "." {
			args = append(args, "-R", repo)
		}
		if err := exec.Command("gh", args...).Run(); err != nil {
			fmt.Printf("   ❌ Falha ao configurar secret %s: %v\n", key, err)
		} else {
			fmt.Printf("   ✅ %s configurado\n", key)
		}
	}

	setVar := func(key, value string) {
		if value == "" {
			return
		}
		args := []string{"variable", "set", key, "--body", value}
		if repo != "." {
			args = append(args, "-R", repo)
		}
		// Tenta remover antes (Upsert robusto)
		delArgs := []string{"variable", "delete", key}
		if repo != "." {
			delArgs = append(delArgs, "-R", repo)
		}
		// Ignora o erro, pois a variável pode não existir.
		_ = exec.Command("gh", delArgs...).Run()
		if err := exec.Command("gh", args...).Run(); err != nil {
			fmt.Printf("   ❌ Falha ao configurar variable %s: %v\n", key, err)
		} else {
			fmt.Printf("   ✅ Variable %s configurada\n", key)
		}
	}

	// Configura novos secrets
	setSecret("AWS_ROLE_ARN", roleArn)
	setSecret("AWS_REGION", utils.GetRegion())
	if supportArn != "" && supportArn != "null" {
		setSecret("AWS_SUPPORT_ROLE_ARN", supportArn)
	}
	if boundaryArn != "" && boundaryArn != "null" {
		setVar("PERMISSIONS_BOUNDARY_ARN", boundaryArn)
	}
}
