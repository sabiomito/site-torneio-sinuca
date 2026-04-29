# Site Torneio de Sinuca — versão serverless AWS

Esta versão troca Flask + SQLite por uma arquitetura serverless:

- **Frontend estático** em `frontend/`.
- **API Python** em `backend/app.py`, rodando em AWS Lambda.
- **Banco DynamoDB** com cobrança sob demanda.
- **S3 privado + CloudFront HTTPS** para publicar o site.
- **API também pelo CloudFront em /api** para evitar erro de CORS/preflight no admin.
- **Infraestrutura como código** em `template.yaml` com AWS SAM/CloudFormation.
- **Deploy automático pelo GitHub Actions** em `.github/workflows/deploy.yml`.

Depois da configuração inicial, qualquer alteração feita por commit na branch `main` atualiza o site, a Lambda, a tabela e novos recursos declarados no `template.yaml`.

---

## O que já está implementado

- Página inicial pública com placar por divisão.
- Link do jogador para ver partidas dele.
- Lista pública de jogos por data e local.
- Filtros no público e no admin por data, local, competidor e divisão.
- Admin protegido por senha.
- Criação completa do torneio com quantidade de divisões configurável.
- Jogadores por divisão.
- Locais de jogo.
- Datas com horário inicial por data.
- Tempo estimado por partida, padrão 30 minutos.
- Recalcular calendário sem precisar recriar tudo.
- Todos contra todos dentro de cada divisão.
- Evita jogador em dois jogos ao mesmo tempo.
- Evita deslocamento entre locais no mesmo dia, exceto se houver pelo menos 30 minutos depois do fim da partida anterior.
- Vitória vale 3 pontos.
- Ao escolher vencedor, o vencedor recebe automaticamente 7 bolas.
- Saldo de bolas é usado como desempate.
- Configuração de promovidos e rebaixados por divisão.
- Linhas verdes para quem sobe e vermelhas para quem cai.
- Seções recolhíveis no admin.
- Ao salvar resultado, a tela não volta para o topo.

---

## Estrutura dos arquivos

```text
.
├── backend/
│   ├── app.py
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── admin.html
│   ├── player.html
│   ├── config.example.js
│   ├── css/style.css
│   └── js/
│       ├── api.js
│       ├── public.js
│       ├── player.js
│       └── admin.js
├── infra/
│   └── bootstrap-github-oidc.yaml
├── .github/workflows/deploy.yml
└── template.yaml
```

---

# Passo a passo para subir na AWS

## 1. Criar um repositório no GitHub

Crie um repositório, por exemplo:

```text
site-torneio-sinuca
```

No seu computador:

```bash
git init
git add .
git commit -m "versao serverless do torneio de sinuca"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/site-torneio-sinuca.git
git push -u origin main
```

---

## 2. Criar a role de deploy na AWS uma única vez

Na AWS, vá em:

```text
CloudFormation > Create stack > With new resources > Upload a template file
```

Envie o arquivo:

```text
infra/bootstrap-github-oidc.yaml
```

Preencha os parâmetros:

```text
GitHubOrg  = seu usuário ou organização do GitHub
GitHubRepo = nome do repositório
Branch     = main
```

Exemplo:

```text
GitHubOrg  = christianwillian
GitHubRepo = site-torneio-sinuca
Branch     = main
```

Marque a confirmação de criação de recursos IAM e crie a stack.

Quando terminar, abra a aba **Outputs** e copie o valor de:

```text
RoleArn
```

Esse ARN será usado pelo GitHub Actions para fazer deploy sem precisar guardar chave de acesso fixa.

> Observação: se sua conta AWS já tiver o provedor OIDC do GitHub criado por outro projeto, essa stack pode reclamar que o provider já existe. Nesse caso, dá para criar apenas uma role nova reaproveitando o provider existente. Me envie o erro exato que eu ajusto o bootstrap para sua conta.

---

## 3. Configurar variáveis no GitHub

No GitHub, vá no repositório:

```text
Settings > Secrets and variables > Actions
```

Crie estas **Variables**:

```text
AWS_ROLE_ARN = valor RoleArn copiado do CloudFormation
AWS_REGION   = sa-east-1
STACK_NAME   = torneioSinucaApp
```

Crie estes **Secrets**:

```text
ADMIN_PASSWORD = senha do admin do torneio
SECRET_KEY     = uma chave grande aleatória
```

Exemplo de `SECRET_KEY`:

```text
sinuca-2026-chave-grande-com-varios-caracteres-938475
```

Não use essa chave de exemplo em produção; crie uma sua.

---

## 4. Rodar o primeiro deploy

Depois que as variáveis e secrets estiverem configuradas, faça um novo commit ou rode manualmente:

```text
GitHub > Actions > Deploy serverless na AWS > Run workflow
```

O workflow vai:

1. Fazer build com AWS SAM.
2. Criar/atualizar CloudFormation.
3. Criar Lambda, DynamoDB, S3 e CloudFront.
4. Pegar os outputs da stack.
5. Gerar `frontend/config.js` automaticamente apontando a API para `/api`.
6. Subir o frontend para o S3.
7. Limpar o cache do CloudFront.
8. Mostrar a URL final do site.

No final do log, procure:

```text
Site publicado em: https://xxxxxxxx.cloudfront.net
```

Essa é a URL do torneio.

---

# Como atualizar depois

Depois da primeira configuração, basta editar os arquivos e commitar:

```bash
git add .
git commit -m "ajustes no torneio"
git push
```

O GitHub Actions faz o deploy sozinho.

Se no futuro precisarmos criar outra Lambda, outra tabela, domínio, permissões, etc., basta alterar o `template.yaml` e commitar. O CloudFormation aplica a mudança no deploy.

---

# Como trocar a senha do admin

No GitHub:

```text
Settings > Secrets and variables > Actions > Secrets > ADMIN_PASSWORD
```

Atualize a senha e rode novamente o workflow.

---

# Como apagar tudo da AWS

Se quiser remover todos os recursos principais:

```text
CloudFormation > Stacks > site-torneio-sinuca > Delete
```

Isso remove Lambda, DynamoDB, S3 e CloudFront criados pela stack principal.

A stack de bootstrap do GitHub OIDC é separada. Se quiser remover também:

```text
CloudFormation > Stacks > nome-da-stack-bootstrap > Delete
```

---

# Atenção sobre custo

Essa arquitetura foi escolhida para baixo acesso:

- DynamoDB usa modo sob demanda.
- Lambda só roda quando alguém chama a API.
- S3 guarda arquivos estáticos.
- CloudFront entrega o site em HTTPS.

Mesmo sendo uma arquitetura de custo muito baixo para pouco acesso, monitore o **Billing** da AWS, porque Free Tier, tráfego, logs e recursos podem gerar cobrança dependendo da conta, região e uso.

---

# Onde alterar o sistema

- Regras da API: `backend/app.py`
- Tela inicial: `frontend/index.html` e `frontend/js/public.js`
- Tela admin: `frontend/admin.html` e `frontend/js/admin.js`
- Estilo visual: `frontend/css/style.css`
- Infraestrutura AWS: `template.yaml`
- Deploy automático: `.github/workflows/deploy.yml`

---

# Correções importantes desta versão

## Aparência

O CSS voltou para o visual escuro da versão Flask original, com fundo escuro, cards arredondados, destaque verde, hero no placar e painel administrativo com a mesma identidade visual.

## Admin com `Failed to fetch`

Esta versão evita que o navegador chame a Lambda diretamente por outro domínio. Agora o CloudFront encaminha qualquer chamada iniciada por `/api` para a Lambda Function URL. Assim, o frontend chama a API no mesmo domínio do site:

```text
https://seu-cloudfront.cloudfront.net/api/...
```

O `frontend/config.js` do deploy fica assim:

```js
window.APP_CONFIG = {
  API_BASE_URL: "/api"
};
```

Também foi mantido suporte para chamar a Lambda diretamente, mas o caminho recomendado é via `/api`.

## Rotas amigáveis

Foi adicionada uma CloudFront Function para permitir acesso direto a:

```text
/admin
/player?id=...
```

Ela reescreve internamente para `admin.html` e `player.html`.

## Nome da stack

Mantenha stacks separadas:

```text
Bootstrap/OIDC: torneioSinucaBootstrap
Aplicação:      torneioSinucaApp
```

Não use a mesma stack para bootstrap e aplicação.
