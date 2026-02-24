package cmd

import (
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"

	"aponte/cli/internal/core"
	"aponte/cli/internal/utils"

	"github.com/spf13/cobra"
)

var setupCmd = &cobra.Command{
	Use:   "setup",
	Short: "Comandos de inicialização e bootstrap da plataforma",
}

var setupBootstrapCmd = &cobra.Command{
	Use:   "bootstrap",
	Short: "Provisiona a infraestrutura base (S3 State + Lock Table)",
	Run:   runSetupBootstrap,
}

var setupPythonCmd = &cobra.Command{
	Use:   "python",
	Short: "Instala dependências Python e o pacote 'core' em modo editável",
	Run:   runSetupPython,
}

var setupKeyCmd = &cobra.Command{
	Use:   "key",
	Short: "Configura API Key do Google Gemini",
	Run:   runSetupKey,
}

var setupOllamaCmd = &cobra.Command{
	Use:   "ollama",
	Short: "Instala o Ollama localmente (Linux)",
	Run:   runSetupOllama,
}

func init() {
	rootCmd.AddCommand(setupCmd)
	setupCmd.AddCommand(setupBootstrapCmd)
	setupCmd.AddCommand(setupPythonCmd)
	setupCmd.AddCommand(setupKeyCmd)
	setupCmd.AddCommand(setupOllamaCmd)
}

func runSetupBootstrap(cmd *cobra.Command, args []string) {
	// FIX: Usa injectProjectEnv para consistência (DRY) com deploy core
	project := "a-ponte"
	projData := &core.Project{
		Name:        project,
		Environment: "production", // Bootstrap é sempre considerado prod/crítico
	}
	injectProjectEnv(project, projData)

	core.BootstrapPlatform() // BootstrapPlatform agora usa core.SetContext internamente
}

func runSetupPython(cmd *cobra.Command, args []string) {
	fmt.Println("🐍 Instalando dependências Python (pip)...")

	pythonBin := getPythonBinary()

	root := utils.GetProjectRoot()
	// Executa: pip install -e <ROOT>[dev]
	// Usa caminho absoluto para permitir execução fora da raiz
	c := exec.Command(pythonBin, "-m", "pip", "install", "-e", fmt.Sprintf("%s[dev]", root))
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr

	if err := c.Run(); err != nil {
		log.Fatalf("❌ Erro na instalação das dependências: %v", err)
	}
	fmt.Println("✅ Ambiente Python configurado com sucesso.")
}

func runSetupKey(cmd *cobra.Command, args []string) {
	root := utils.GetProjectRoot()
	scriptPath := filepath.Join(root, "core", "tools", "setup_key.py")

	if _, err := os.Stat(scriptPath); os.IsNotExist(err) {
		fmt.Printf("❌ Erro: Script não encontrado em: %s\n", scriptPath)
		os.Exit(1)
	}

	pythonBin := getPythonBinary()

	c := exec.Command(pythonBin, append([]string{scriptPath}, args...)...)
	c.Stdout, c.Stderr, c.Stdin = os.Stdout, os.Stderr, os.Stdin
	c.Env = getPythonEnv(root)

	if err := c.Run(); err != nil {
		os.Exit(1)
	}
}

func runSetupOllama(cmd *cobra.Command, args []string) {
	// Verifica se já está instalado
	if _, err := exec.LookPath("ollama"); err == nil {
		fmt.Println("✅ Ollama já está instalado no sistema.")
		return
	}

	if runtime.GOOS != "linux" {
		fmt.Println("⚠️  Instalação automática suportada apenas no Linux. Por favor instale manualmente: https://ollama.com")
		return
	}

	fmt.Println("⬇️  Baixando e instalando Ollama (Requer sudo)...")
	// Executa o script oficial de instalação
	c := exec.Command("sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh")
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	if err := c.Run(); err != nil {
		log.Fatalf("❌ Erro ao instalar Ollama: %v", err)
	}
	fmt.Println("✅ Ollama instalado com sucesso!")
	fmt.Println("ℹ️  Dica: Execute 'aponte ai train' para baixar o modelo base e criar o cérebro 'aponte-ai'.")
}
