# Dashboard Recompra · Maestro

Dashboard de jornada do comprador com atualização automática de hora em hora via GitHub Actions + Google Sheets API.

---

## Arquitetura

```
Google Sheets
     │
     │  (GitHub Actions · toda hora)
     ▼
scripts/fetch_data.py  →  data/data.json  →  index.html (GitHub Pages)
```

---

## Setup completo (passo a passo)

### 1. Criar projeto e Service Account no GCP

1. Acesse [console.cloud.google.com](https://console.cloud.google.com)
2. Clique em **Select a project** → **New Project**
   - Nome: `maestro-dashboard` → **Create**
3. Com o projeto selecionado, vá em **APIs & Services → Library**
4. Busque **Google Sheets API** → clique → **Enable**
5. Vá em **APIs & Services → Credentials**
6. Clique **+ Create Credentials → Service Account**
   - Nome: `sheets-reader` → **Create and Continue** → **Done**
7. Na lista de Service Accounts, clique no email criado
8. Aba **Keys → Add Key → Create new key → JSON → Create**
   - Vai baixar um arquivo `.json` — **guarde bem, usaremos no passo 3**

### 2. Compartilhar a planilha com a Service Account

1. Abra o arquivo `.json` baixado e copie o valor do campo `"client_email"`
   - Exemplo: `sheets-reader@maestro-dashboard.iam.gserviceaccount.com`
2. Abra a planilha do Google Sheets
3. Clique em **Compartilhar** (botão verde, canto superior direito)
4. Cole o email da service account → papel **Visualizador** → **Enviar**

> A planilha **não precisa ser pública**. Só a service account precisa de acesso.

### 3. Adicionar secrets no GitHub

1. No repositório GitHub, vá em **Settings → Secrets and variables → Actions**
2. Clique **New repository secret** e adicione dois secrets:

| Nome | Valor |
|------|-------|
| `SPREADSHEET_ID` | ID da planilha (parte da URL: `docs.google.com/spreadsheets/d/**ID_AQUI**/edit`) |
| `GCP_SERVICE_ACCOUNT_JSON` | Conteúdo completo do arquivo `.json` baixado no passo 1 (cole tudo) |

### 4. Ativar GitHub Pages

1. Vá em **Settings → Pages**
2. Em **Source**, selecione **Deploy from a branch**
3. Branch: `main` | Folder: `/ (root)` → **Save**
4. Após alguns segundos, o link do seu dashboard aparecerá (ex: `https://seu-usuario.github.io/dashboard-recompra-maestro`)

### 5. Rodar o primeiro fetch manualmente

Antes de esperar a hora cheia, rode manualmente:

1. Vá em **Actions** no repositório
2. Clique em **Atualizar dados (hourly)**
3. Clique **Run workflow → Run workflow**
4. Aguarde ~30s e recarregue o dashboard

---

## Estrutura do repositório

```
dashboard-recompra-maestro/
├── .github/
│   └── workflows/
│       └── update-data.yml     ← Roda a cada hora automaticamente
├── data/
│   └── data.json               ← Gerado pelo script (não editar manualmente)
├── scripts/
│   └── fetch_data.py           ← Lê o Sheets e gera o data.json
├── index.html                  ← Dashboard (GitHub Pages serve este arquivo)
├── requirements.txt
└── README.md
```

---

## Lógica de negócio

### Quais registros são considerados

Somente linhas com:
- `order_status = paid`
- `webhook_event_type` em: `order_approved`, `subscription_payment`, `subscription_reactivated`

Isso garante que renovações de assinatura também entram como compras do comprador.

### Classificação de origem

| Padrão detectado | Canal |
|---|---|
| `fb`, `fbads`, `facebook`, `meta` | Meta Ads |
| `instagram`, `ig` | Instagram |
| `youtube`, `yt` | YouTube |
| `email`, `mailing` | E-mail |
| `whatsapp`, `wpp`, `zap` | WhatsApp |
| Todos os campos vazios | Sem origem |
| Qualquer outro | Outros |

Campos verificados (nessa ordem): `utm_source`, `src`, `sck`, `utm_medium`.

### Métricas

| Métrica | Lógica |
|---|---|
| Compradores únicos | Emails distintos com ≥1 compra paid |
| Recompradores | Emails com ≥2 compras paid |
| Total recompras | Soma de (nº compras − 1) por recomprador |
| LTV médio | Σ Faturamento / total de compradores únicos |
| Dias até 2ª compra | Média de (data 2ª compra − data 1ª compra) em dias |
| Dias até última | Média de (data última compra − data 1ª compra) em dias |

---

## Atualização automática

O workflow `.github/workflows/update-data.yml` roda todo dia em todas as horas (cron `0 * * * *`), gera o `data/data.json` atualizado e faz commit automático no repositório. O dashboard lê o arquivo JSON ao carregar e a cada 1 hora no browser.

---

## Suporte

Em caso de dúvidas no setup do GCP ou GitHub, consulte a documentação ou entre em contato com o analista responsável.
