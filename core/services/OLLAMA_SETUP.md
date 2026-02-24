# 🦙 Guia de Configuração do Ollama (Hardware Profile)

Este guia ajuda você a escolher e configurar o modelo de IA ideal para o seu hardware, garantindo que a plataforma A-PONTE rode de forma fluida.

## 1. Instalação

Baixe e instale o Ollama em [ollama.com](https://ollama.com).

## 2. Escolha seu Perfil de Hardware

### 💻 Perfil 1: "Guerreiro" (PC Fraco / Laptop)
**Cenário:** CPU Intel/AMD antiga, Sem GPU dedicada, 8GB-16GB RAM.
**Foco:** Velocidade e baixo consumo de memória.

*   **Modelo Recomendado:** `deepseek-r1:1.5b` (Padrão)
*   **Alternativa:** `qwen2.5-coder:1.5b`
*   **Comando:** `ollama pull deepseek-r1:1.5b`

### 🎮 Perfil 2: "Gamer / Dev" (GPU Dedicada)
**Cenário:** Placa de Vídeo NVIDIA (RTX 3060+), 16GB+ RAM.
**Foco:** Inteligência e raciocínio complexo.

*   **Modelo Recomendado:** `deepseek-r1:7b` ou `deepseek-r1:8b`
*   **Alternativa:** `llama3.1:8b`
*   **Comando:** `ollama pull deepseek-r1:7b`

### 🚀 Perfil 3: "Servidor / Workstation" (High-End)
**Cenário:** GPU Profissional (A100/H100) ou Mac Studio, 64GB+ RAM.
**Foco:** Capacidade máxima.

*   **Modelo Recomendado:** `deepseek-r1:32b`
*   **Comando:** `ollama pull deepseek-r1:32b`

## 3. Configurando no A-PONTE

Diga ao A-PONTE qual modelo usar definindo a variável de ambiente `A_PONTE_AI_MODEL`.

**No terminal (Linux/Mac):**
```bash
export A_PONTE_AI_MODEL=deepseek-r1:7b
```

**No arquivo `.env` (Recomendado):**
```bash
A_PONTE_AI_MODEL=deepseek-r1:7b
```

## 4. Treinando o Cérebro

Após configurar, rode o treinamento para criar o modelo especializado `aponte-ai`:

```bash
aponte ai train
```

O sistema detectará automaticamente o modelo base configurado.
