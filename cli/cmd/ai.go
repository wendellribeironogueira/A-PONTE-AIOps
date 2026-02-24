package cmd

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"

	"aponte/cli/internal/core"
	"aponte/cli/internal/utils"

	"github.com/spf13/cobra"
)

var aiCmd = &cobra.Command{
	Use:   "ai",
	Short: "Gerencia recursos de IA (Modelos, Treinamento)",
}

var aiValidateCmd = &cobra.Command{
	Use:   "validate",
	Short: "Valida se o modelo no Ollama corresponde ao Modelfile local",
	Run:   runAiValidate,
}

var aiTrainCmd = &cobra.Command{
	Use:   "train",
	Short: "Treina o modelo de IA com a base de conhecimento (RAG)",
	Run:   runAiTrain,
}

var aiIngestCmd = &cobra.Command{
	Use:   "ingest",
	Short: "Ingere novas fontes de conhecimento (Auto-Learn)",
	Run:   runAiIngest,
}

func init() {
	rootCmd.AddCommand(aiCmd)
	aiCmd.AddCommand(aiValidateCmd)
	aiCmd.AddCommand(aiTrainCmd)
	aiCmd.AddCommand(aiIngestCmd)
}

func runAiTrain(cmd *cobra.Command, args []string) {
	root := utils.GetProjectRoot()
	scriptPath := filepath.Join(root, "core", "services", "knowledge", "trainer.py")

	if _, err := os.Stat(scriptPath); os.IsNotExist(err) {
		fmt.Printf("❌ Erro: Script de treinamento não encontrado em: %s\n", scriptPath)
		os.Exit(1)
	}

	pythonBin := getPythonBinary()

	c := exec.Command(pythonBin, scriptPath)
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	c.Stdin = os.Stdin

	// FIX: Injeta contexto para que o treinamento considere dados do projeto atual
	if project, err := core.GetContext(); err == nil && project != "" && project != "home" {
		projData, _ := core.GetProject(project)
		injectProjectEnv(project, projData)
	}

	c.Env = getPythonEnv(root)

	fmt.Println("🧠 Iniciando treinamento do modelo...")
	if err := c.Run(); err != nil {
		fmt.Printf("❌ Erro no treinamento: %v\n", err)
		os.Exit(1)
	}
}

func runAiIngest(cmd *cobra.Command, args []string) {
	root := utils.GetProjectRoot()
	scriptPath := filepath.Join(root, "core", "services", "knowledge", "ingestor.py")

	if _, err := os.Stat(scriptPath); os.IsNotExist(err) {
		fmt.Printf("❌ Erro: Script de ingestão não encontrado em: %s\n", scriptPath)
		os.Exit(1)
	}

	pythonBin := getPythonBinary()

	c := exec.Command(pythonBin, scriptPath)
	c.Stdout, c.Stderr, c.Stdin = os.Stdout, os.Stderr, os.Stdin

	// FIX: Injeta contexto para ingestão de documentos do projeto
	if project, err := core.GetContext(); err == nil && project != "" && project != "home" {
		projData, _ := core.GetProject(project)
		injectProjectEnv(project, projData)
	}
	c.Env = getPythonEnv(root)

	if err := c.Run(); err != nil {
		fmt.Printf("❌ Erro na ingestão: %v\n", err)
		os.Exit(1)
	}
}

func runAiValidate(cmd *cobra.Command, args []string) {
	root := utils.GetProjectRoot()
	modelfilePath := filepath.Join(root, "config", "ai", "aponte-ai.modelfile")

	fmt.Println("🔍 Validando sincronização do modelo 'aponte-ai'...")

	localBytes, err := os.ReadFile(modelfilePath)
	if err != nil {
		fmt.Printf("❌ Erro ao ler Modelfile local: %v\n", err)
		return
	}
	localContent := string(localBytes)

	// MIGRATION: Tenta usar Ollama local primeiro, fallback para Docker (Legado)
	var remoteContent string

	// 1. Tenta Local
	out, err := exec.Command("ollama", "show", "aponte-ai", "--modelfile").CombinedOutput()
	if err == nil {
		remoteContent = string(out)
	} else {
		// 2. Fallback Docker
		outDocker, errDocker := exec.Command("docker", "exec", "ollama", "ollama", "show", "aponte-ai", "--modelfile").CombinedOutput()
		if errDocker != nil {
			fmt.Printf("❌ Erro ao consultar Ollama (Local e Docker falharam): %v\n", err)
			return
		}
		remoteContent = string(outDocker)
	}

	normLocal := normalizeModelfile(localContent)
	normRemote := normalizeModelfile(remoteContent)

	match := true
	if len(normLocal) != len(normRemote) {
		match = false
	} else {
		for i := range normLocal {
			if normLocal[i] != normRemote[i] {
				match = false
				break
			}
		}
	}

	if match {
		fmt.Println("✅ O modelo no Ollama está SINCRONIZADO com o arquivo local.")
	} else {
		fmt.Println("⚠️  DIVERGÊNCIA DETECTADA!")
		fmt.Println("   O modelo carregado no Ollama é diferente do 'config/ai/aponte-ai.modelfile'.")
		fmt.Println("   Isso significa que o arquivo foi alterado mas o 'aponte train' não foi executado.")

		// Debug info para ajudar a entender o que mudou
		fmt.Printf("\n   [DEBUG] Linhas Normalizadas - Local: %d | Remoto: %d\n", len(normLocal), len(normRemote))

		fmt.Println("\n   🔍 Detalhes da Divergência (Primeiras diferenças):")
		diffCount := 0
		maxLen := len(normLocal)
		if len(normRemote) > maxLen {
			maxLen = len(normRemote)
		}

		for i := 0; i < maxLen; i++ {
			var l, r string
			if i < len(normLocal) {
				l = normLocal[i]
			} else {
				l = "(EOF)"
			}
			if i < len(normRemote) {
				r = normRemote[i]
			} else {
				r = "(EOF)"
			}

			if l != r {
				// Trunca linhas muito longas para exibição
				if len(l) > 80 {
					l = l[:77] + "..."
				}
				if len(r) > 80 {
					r = r[:77] + "..."
				}

				fmt.Printf("   Line %d:\n     Local:  %s\n     Remote: %s\n", i+1, l, r)
				diffCount++
				if diffCount >= 3 {
					break
				}
			}
		}

		fmt.Println("\n Solução: Execute 'aponte train' para atualizar o cérebro.")
	}
}

func normalizeModelfile(content string) []string {
	lines := strings.Split(content, "\n")
	var clean []string
	var parameters []string
	inIgnoredBlock := false

	for _, line := range lines {
		l := strings.TrimSpace(line)
		if l == "" || strings.HasPrefix(l, "#") {
			continue
		}

		upper := strings.ToUpper(l)

		// FIX: Ignora FROM para evitar divergência entre Nome (Local) e Blob (Remoto)
		if strings.HasPrefix(upper, "FROM ") {
			continue
		}

		// Coleta PARAMETER para ordenação posterior (evita falso positivo por ordem)
		if strings.HasPrefix(upper, "PARAMETER ") {
			// Ignora PARAMETER stop herdados do modelo base que causam falso positivo na validação
			if strings.HasPrefix(upper, "PARAMETER STOP") {
				continue
			}
			parameters = append(parameters, l)
			continue
		}

		// Detecta início de blocos ignorados (LICENSE, TEMPLATE)
		if !inIgnoredBlock {
			if strings.HasPrefix(upper, "LICENSE") {
				if strings.Count(l, `"""`) == 1 {
					inIgnoredBlock = true
				}
				continue
			}

			if strings.HasPrefix(upper, "TEMPLATE") {
				if strings.Contains(l, `"""`) {
					if strings.Count(l, `"""`) == 1 {
						inIgnoredBlock = true
					}
				} else if strings.HasPrefix(upper, "TEMPLATE \"") {
					if !strings.HasSuffix(l, "\"") {
						inIgnoredBlock = true
					}
				}
				continue
			}
		} else {
			// Dentro de bloco ignorado: procura fechamento
			if strings.Contains(l, `"""`) {
				inIgnoredBlock = false
			} else if strings.HasSuffix(l, "\"") && !strings.HasSuffix(l, "\\\"") {
				// Fechamento de aspas simples (Ollama format)
				inIgnoredBlock = false
			}
			continue
		}

		l = strings.Join(strings.Fields(l), " ")
		clean = append(clean, l)
	}

	// Ordena e adiciona parâmetros ao final para comparação consistente
	sort.Strings(parameters)
	clean = append(clean, parameters...)

	return clean
}
