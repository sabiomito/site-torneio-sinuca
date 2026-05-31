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
