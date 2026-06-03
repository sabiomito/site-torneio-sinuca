# Segundo campeonato municipal de sinuca de Entre Folhas — Serverless

Versão serverless do site do torneio:

- Frontend estático em S3 + CloudFront.
- API em AWS Lambda Function URL, acessada pelo CloudFront em `/api`.
- Banco em DynamoDB sob demanda.
- Deploy automático por GitHub Actions + AWS SAM.

## O que mudou nesta versão

O torneio agora é montado em etapas:

1. **Configurações iniciais**
   - quantidade de divisões;
   - tempo por jogo;
   - quantidade de chaves por divisão;
   - quantidade que sobe/marca verde por chave;
   - quantidade que cai/marca vermelho por chave.

2. **Competidores**
   - nome;
   - divisão;
   - chave.

3. **Rodadas**
   - nome/local da rodada;
   - divisão;
   - chave;
   - data;
   - horário inicial;
   - criação automática ou manual dos confrontos.

4. **Partidas e resultados**
   - filtros por data, rodada, local, competidor, divisão e chave;
   - vencedor recebe automaticamente 7 bolas;
   - vitória vale 3 pontos;
   - saldo de bolas é critério de desempate.

## Regras das rodadas

- Os jogos acontecem apenas entre competidores da mesma divisão e da mesma chave.
- Cada rodada tenta colocar todos os jogadores da chave para jogar uma vez.
- Se a chave tiver número ímpar de jogadores, um jogador fica de folga na rodada.
- Um confronto nunca é repetido dentro da mesma divisão/chave.
- Ao criar rodada automática, o sistema escolhe confrontos ainda não usados.
- Ao criar rodada manual, o admin escolhe os confrontos; o backend valida repetição e jogador duplicado.
- Resultados já salvos ficam preservados mesmo se uma rodada for excluída.
- Ao excluir uma rodada, partidas pendentes são removidas; partidas finalizadas permanecem no histórico.

## Limpeza do banco no próximo deploy

Esta versão inclui a variável de ambiente:

```text
DATABASE_RESET_VERSION=v7-rodadas-20260530-01
```

No primeiro acesso após o deploy, a Lambda limpa o DynamoDB antigo e grava esse marcador. Depois disso, não apaga de novo enquanto o valor não mudar.

Também existe um botão vermelho no admin para limpar o banco manualmente, com dupla confirmação.

## Deploy

Depois de substituir os arquivos no repositório:

```bash
git add .
git commit -m "reestrutura torneio por rodadas e chaves"
git push
```

O GitHub Actions executa o deploy automaticamente.

## Variáveis do GitHub

Em **Settings > Secrets and variables > Actions > Variables**:

```text
AWS_ROLE_ARN
AWS_REGION
STACK_NAME
```

Em **Settings > Secrets and variables > Actions > Secrets**:

```text
ADMIN_PASSWORD
SECRET_KEY
```

## Alterações da versão v8

- A tela pública não mostra mais a legenda antiga; no lugar foi adicionada a imagem de propaganda em `frontend/img/banner-tacos-sinuca.png`.
- No placar, a coluna Situação agora mostra `Classificado` e `Rebaixado`.
- O botão `Atualizar pelo admin` foi removido do card do placar geral, mantendo apenas o link `Admin` no topo.
- A montagem manual da rodada agora usa linhas de jogos: um combobox à esquerda, um `x` no meio e outro combobox à direita.
- Ao escolher um competidor em qualquer combobox da rodada manual, ele deixa de aparecer nos outros combobox da mesma rodada.
- Os cards colapsáveis do admin continuam começando fechados após login.

## Alterações da versão v9

- A rodada manual agora avisa quando algum confronto escolhido já aconteceu ou já está cadastrado.
- Se o administrador confirmar, a rodada é criada ignorando apenas esses jogos conflitantes.
- O status de rodadas mostra jogos/confrontos pendentes e informa quando a rodada pendente está incompleta.
- É possível editar o nome/local de uma rodada já cadastrada pela lista de rodadas. A alteração também atualiza as partidas vinculadas à rodada.

## Alterações da versão v10

- Em cada tabela pública de classificação foi adicionado um botão **Compartilhar**.
- O botão gera uma imagem vertical 1080x1920 pronta para Instagram/Status do WhatsApp com:
  - título `2° campeonato municipal de sinuca`;
  - divisão e chave, quando houver mais de uma chave;
  - posição, jogador abreviado, pontos, vitórias, jogos e saldo de bolas;
  - linhas verdes para classificados e vermelhas para rebaixados;
  - fundo estilizado com elementos de sinuca.
- Ao lado de **Limpar filtros** foi adicionado o botão **Imprimir/PDF**.
- A impressão gera uma página própria com os jogos filtrados, cerca de 24 jogos por folha.
- Jogos com resultado aparecem preenchidos; jogos pendentes aparecem com espaço para preencher manualmente depois de impresso.
- O botão de impressão foi adicionado na tela pública e também no admin para usar os filtros atuais de partidas.


## Atualização visual de compartilhamento e impressão

- A imagem de compartilhamento agora usa `frontend/img/share-bg-base.png` como fundo principal.
- A lista de impressão foi ajustada para caber corretamente em A4 com até 24 jogos por página.
