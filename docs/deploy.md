# Colocar o site no ar

O site publicado roda em **modo demonstração**: produtos de exemplo já cadastrados e
ninguém consegue alterar nada. Os motivos estão no `monitor/demo.py` e na Etapa 19 do
diário — em resumo, as lojas bloqueiam servidores na nuvem, e um site aberto sem
trava seria apagado pelo primeiro visitante mal-humorado.

## Passo a passo (Render)

1. Entre em **[render.com](https://render.com)** e crie a conta com **"Sign in with GitHub"**
   (não pede cartão de crédito).
2. No painel: **New → Blueprint**.
3. Escolha o repositório **monitor-de-precos** e confirme (**Apply**).
   O Render lê o arquivo [`render.yaml`](../render.yaml) e já sabe o resto: instala as
   dependências, sorteia a `MONITOR_SECRET_KEY` e liga o `MONITOR_DEMO`.
4. Espere o primeiro build (uns 3 minutos). No fim aparece o endereço, algo como
   `https://monitor-de-precos.onrender.com`.
5. Abra o endereço e confira: a faixa **"Modo demonstração"** no topo, os quatro produtos
   de exemplo e nenhum botão de "Criar conta".

A partir daí, **todo `git push` na `main` publica sozinho** — é o mesmo push que já dispara
os testes no GitHub Actions.

## O que esperar do plano gratuito

- **O servidor dorme** depois de 15 minutos sem visitas. A primeira visita depois disso
  demora uns 50 segundos para abrir. Nas seguintes, é instantâneo.
  Se for mandar o link para alguém, abra você primeiro, para o site já estar acordado.
- **O disco é descartável.** Tudo que for gravado some quando o servidor reinicia — e é
  por isso que o banco da demonstração se reconstrói sozinho a cada partida.

## Trocar de hospedagem depois

O código não sabe em que servidor está rodando: tudo que muda de um lugar para outro
está em variáveis de ambiente. Para mudar, basta reproduzir em outro serviço:

| O que | Valor |
|---|---|
| Comando de instalação | `pip install -r requirements.txt` |
| Comando de partida | `gunicorn --bind 0.0.0.0:$PORT --workers 1 "monitor.app:create_app()"` |
| Variáveis | `MONITOR_DEMO=1`, `MONITOR_DB_PATH=/tmp/monitor.db`, `MONITOR_SECRET_KEY=<valor aleatório>` |

Exemplos de outros caminhos:

- **PythonAnywhere** (não dorme, mas o deploy é manual): usa um arquivo WSGI próprio do
  painel, onde se escreve `from monitor.app import create_app` e
  `application = create_app()`. As variáveis vão no mesmo arquivo, antes dessa linha.
- **Fly.io / Railway / qualquer serviço com Docker:** os mesmos dois comandos da tabela.

Nenhum desses casos exige mexer no Python. Só o `render.yaml` é específico do Render.

## Rodar o modo demonstração na sua máquina

Serve para ver exatamente o que o público vê, sem tocar no seu banco de verdade:

```powershell
$env:MONITOR_DEMO = "1"
$env:MONITOR_DB_PATH = "$env:TEMP\monitor-demo.db"
flask --app monitor.app run --port 5001
```

Depois, feche o terminal (as variáveis valem só nele) ou abra um novo para voltar ao normal.
