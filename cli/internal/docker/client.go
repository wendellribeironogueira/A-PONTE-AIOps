package docker

import (
	"context"
	"io"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/client"
)

// Client wraps the official Docker client to provide helper methods
type Client struct {
	api *client.Client
}

// NewClient creates a new Docker client with automatic API version negotiation
func NewClient() (*Client, error) {
	// FIX: WithAPIVersionNegotiation resolve o erro "client version 1.43 is too old"
	api, err := client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())
	if err != nil {
		return nil, err
	}
	return &Client{api: api}, nil
}

// ListContainers returns a list of running containers
func (c *Client) ListContainers(ctx context.Context) ([]types.Container, error) {
	return c.api.ContainerList(ctx, container.ListOptions{})
}

// StreamLogs returns a stream of logs for a specific container
func (c *Client) StreamLogs(ctx context.Context, containerID string) (io.ReadCloser, error) {
	return c.api.ContainerLogs(ctx, containerID, container.LogsOptions{
		ShowStdout: true,
		ShowStderr: true,
		Follow:     true,
	})
}

// IsRunning checks if the Docker daemon is reachable
func (c *Client) IsRunning(ctx context.Context) bool {
	_, err := c.api.Ping(ctx)
	return err == nil
}
