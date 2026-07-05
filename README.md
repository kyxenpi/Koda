<div align="center">
  <img src="static/logo.png" alt="Koda" width="100" height="100" />
  <h1>🤖 Koda</h1>
  <p><strong>Agente de IA autônomo com interface web, ferramentas inteligentes e deploy nativo na nuvem</strong></p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.11-blue?style=flat&logo=python" alt="Python 3.11" />
    <img src="https://img.shields.io/badge/Flask-3.0-black?style=flat&logo=flask" alt="Flask" />
    <img src="https://img.shields.io/badge/Groq-LLM-ff6f00?style=flat" alt="Groq" />
    <img src="https://img.shields.io/badge/PostgreSQL-SQLite-336791?style=flat&logo=postgresql" alt="DB" />
    <img src="https://img.shields.io/badge/PWA-ready-5A0FC8?style=flat&logo=pwa" alt="PWA" />
    <img src="https://img.shields.io/badge/Docker-ready-2496ED?style=flat&logo=docker" alt="Docker" />
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat" alt="License" />
  </p>
  <br />
</div>

---

## ✨ Sobre

O **Koda** é um assistente pessoal com IA que combina um motor de raciocínio autônomo (ReAct loop) com mais de **20 ferramentas integradas** — desde busca na web até Google Workspace, passando por sistema de arquivos, terminal, OCR e muito mais.

Tudo roda em uma interface web moderna e responsiva, com suporte a **voz**, **upload de documentos**, **modo escuro**, **PWA** e **BYOK** (suas chaves de API ficam só no seu navegador).

---

## 🎯 Funcionalidades

### 🧠 Agente Autônomo
- Ciclo ReAct com até **8 passos de raciocínio**
- Execução de ferramentas em **paralelo** ou **sequencial**
- **Reflexão**: o próprio agente valida se o objetivo foi cumprido
- Fallback automático entre modelos primário (`llama-3.3-70b`) e secundário (`llama-3.1-8b`)
- Streaming de eventos em tempo real via SSE

### 🛠️ Ferramentas
| Categoria | Ferramentas |
|-----------|-------------|
| **Web** | Busca DuckDuckGo, fetch de páginas, API REST genérica |
| **Google** | Docs (ler/escrever), Drive, Calendar, Sheets, Gmail, YouTube, Contatos |
| **Arquivos** | Listar, ler, escrever, anexar, buscar, deletar (com restrição de path) |
| **Sistema** | Terminal (comandos pré-mapeados), info do sistema, Python runner |
| **Utilitários** | Calculadora, notas, listar ferramentas |

### 🌐 Interface Web
- **Streaming ao vivo**: veja os tokens chegando em tempo real
- **Voz**: ditado por microfone + narração das respostas (Web Speech API)
- **Documentos**: arraste PDF, DOCX ou TXT — o texto é extraído no navegador
- **Comandos `/`**: `/search`, `/calc`, `/resumir`, `/help`, `/export`, `/clear` com autocomplete
- **Tema claro/escuro**: alternância suave, persistido no `localStorage`
- **Perfil do usuário**: nome, idioma e bio — injetados no contexto da IA
- **Exportar conversas**: chat atual ou todas em Markdown
- **Histórico**: sidebar com navegação, exclusão e contador de tokens

### 📱 PWA
- Instalável como aplicativo no celular/desktop
- Service Worker com cache-first
- Manifest completo com ícones 192px e 512px

### 🔐 BYOK (Bring Your Own Key)
- Suas chaves (Groq, OCR, Google) ficam no **IndexedDB do navegador**
- Enviadas por formulário ao backend apenas durante a requisição
- Limpeza automática com `threading.local()` + `finally` — nunca persistem no servidor

### 🤖 Telegram
- Webhook para mensagens de texto e fotos
- OCR automático em imagens enviadas pelo Telegram

---

## 🚀 Como usar

### 1. Local (desenvolvimento)

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/koda.git
cd koda

# Crie um ambiente virtual
python -m venv .venv
source .venv/bin/activate

# Instale as dependências
pip install -r requirements.txt

# Configure as variáveis de ambiente
cp .env.example .env
# Edite o .env e adicione sua GROQ_API_KEY (obrigatório)

# Rode o servidor de desenvolvimento
python main.py
```

Acesse **http://localhost:5000** no navegador.

### 2. Docker

```bash
docker build -t koda .
docker run -p 5000:5000 --env-file .env koda
```

### 3. Produção (Render)

```bash
# Configure as variáveis de ambiente no painel da Render:
#   GROQ_API_KEY, DATABASE_URL (postgres://...), ENVIRONMENT=production
# Start command: gunicorn wsgi:app
```

---

## ⚙️ Configuração

### Variáveis de Ambiente

| Variável | Obrigatório | Descrição |
|----------|-------------|-----------|
| `GROQ_API_KEY` | ✅ | Chave da API Groq (começa com `gsk_`) |
| `TELEGRAM_TOKEN` | ❌ | Token do bot do Telegram |
| `DATABASE_URL` | ❌ | URL do PostgreSQL. Vazio = SQLite |
| `OCR_SPACE_API_KEY` | ❌ | Chave da API OCR.space |
| `GOOGLE_CREDENTIALS_JSON` | ❌ | JSON de credenciais OAuth do Google |
| `GOOGLE_TOKEN_JSON` | ❌ | Token OAuth do Google (para produção) |
| `ENVIRONMENT` | ❌ | `production` para modo cloud |
| `PORT` | ❌ | Porta do servidor (padrão: 5000) |

> 💡 **BYOK**: mesmo com `GROQ_API_KEY` configurada no servidor, cada usuário pode usar a **própria chave** pelo frontend — ela nunca é salva no servidor.

---

## 🏗️ Arquitetura

```
                    ┌──────────────────────────────┐
                    │      Navegador (PWA)          │
                    │  IndexedDB · Web Speech API   │
                    │  pdf.js · mammoth.js · Lucide │
                    └───────────┬──────────────────┘
                                │ SSE / FormData
                    ┌───────────▼──────────────────┐
                    │     Flask / Gunicorn          │
                    │  routes/web.py · routes/tg.py │
                    └───────────┬──────────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
  ┌───────▼───────┐   ┌────────▼────────┐   ┌────────▼────────┐
  │   Agente IA    │   │  Model Manager  │   │   Database      │
  │  (agent.py)    │   │  (models.py)    │   │  (memory_db.py) │
  │                │   │                 │   │                 │
  │ • ReAct loop   │   │ • Groq API      │   │ • SQLite (dev)  │
  │ • Reflexão     │   │ • Fallback      │   │ • PostgreSQL    │
  │ • Tool calls   │   │ • Stream        │   │   (prod)        │
  └───────┬───────┘   │ • Transcrição    │   └─────────────────┘
          │           └─────────────────┘
  ┌───────▼───────┐
  │  ToolExecutor  │
  │  (executor.py) │
  │                │
  │ • 20+ tools    │
  │ • Thread pool  │
  │ • Timeouts     │
  └────────────────┘
```

### Modelos de IA

| Função | Modelo | Provedor |
|--------|--------|----------|
| **Primário** | `llama-3.3-70b-versatile` | Groq |
| **Fallback** | `llama-3.1-8b-instant` | Groq |
| **Transcrição** | `whisper-large-v3` | Groq |

---

## 🛠️ Tecnologias

| Backend | Frontend | Infra |
|---------|----------|-------|
| Python 3.11 | HTML/CSS/JS vanilla | Docker |
| Flask 3.0 | marked.js | Render |
| Gunicorn | pdf.js | gunicorn |
| Groq SDK | mammoth.js | gthread workers |
| psycopg2 | Lucide icons | Rate limiting |
| google-api-client | Web Speech API | WAL mode (SQLite) |
| psutil | Service Worker | Health checks |

---

## 📁 Estrutura

```
koda/
├── agent/          # Núcleo do agente (ciclo ReAct, reflexão, contexto)
├── core/           # Infraestrutura (logger, runtime, segurança, cache)
├── database/       # Camada de banco (SQLite + PostgreSQL)
├── routes/         # Endpoints web e Telegram
├── tools/          # 20+ ferramentas integradas
├── static/         # Manifest, service worker, logo
├── templates/      # Single-page frontend (index.html)
├── main.py         # Entrypoint Flask
├── wsgi.py         # Entrypoint Gunicorn
├── config.py       # Config centralizada
├── Dockerfile      # Build otimizado
└── gunicorn.conf.py# Config do Gunicorn
```

---

## 🤝 Contribuindo

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues e pull requests.

---

## 📄 Licença

MIT © 2026 Koda
