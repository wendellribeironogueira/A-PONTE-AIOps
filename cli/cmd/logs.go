package cmd

import (
	"context"
	"fmt"
	"io"
	"os"
	"strings"

	"aponte/cli/internal/docker"

	"github.com/docker/docker/pkg/stdcopy"
	"github.com/spf13/cobra"
)

var logsCmd = &cobra.Command{
	Use:   "logs [service]",
	Short: "Exibe logs de um serviço (Docker SDK)",
	Long:  `Faz tail nos logs de um container específico usando o Docker SDK.`,
	Args:  cobra.MaximumNArgs(1),
	Run:   runLogs,
}

func init() {
	rootCmd.AddCommand(logsCmd)
}

func runLogs(cmd *cobra.Command, args []string) {
	service := ""
	if len(args) > 0 {
		service = args[0]
	}

	if service == "" {
		fmt.Println("⚠️  Especifique o serviço para ver os logs (ex: aponte logs ollama)")
		fmt.Println("   Serviços comuns: ollama, crawl4ai, mcp-terraform")
		return
	}

	client, err := docker.NewClient()
	if err != nil {
		fmt.Printf("❌ Erro Docker: %v\n", err)
		return
	}

	ctx := context.Background()
	containers, err := client.ListContainers(ctx)
	if err != nil {
		fmt.Printf("❌ Erro ao listar containers: %v\n", err)
		return
	}

	var targetID string
	for _, c := range containers {
		if s, ok := c.Labels["com.docker.compose.service"]; ok && s == service {
			targetID = c.ID
			break
		}
		for _, name := range c.Names {
			if strings.Contains(name, service) {
				targetID = c.ID
				break
			}
		}
	}

	if targetID == "" {
		fmt.Printf("❌ Serviço '%s' não encontrado (container não está rodando?).\n", service)
		return
	}

	fmt.Printf("📜 Streamando logs de %s (%s)...\n", service, targetID[:12])

	out, err := client.StreamLogs(ctx, targetID)
	if err != nil {
		fmt.Printf("❌ Erro ao obter logs: %v\n", err)
		return
	}
	defer func() {
		if err := out.Close(); err != nil {
			fmt.Printf("❌ Erro ao fechar o stream de logs: %v\n", err)
		}
	}()

	if _, err := stdcopy.StdCopy(os.Stdout, os.Stderr, out); err != nil && err != io.EOF {
		fmt.Printf("❌ Erro no stream: %v\n", err)
	}
}
