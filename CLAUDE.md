# Monitor de Preços

## O que é
Um **site que compara o preço do mesmo produto em várias lojas online brasileiras**, guarda o histórico e destaca o melhor preço (depois: avisa quando o preço cair).

Exemplo de uso: o Guilherme quer comprar uma memória RAM. Ele cadastra o produto com o **código do fabricante** (`KF432C16BB1/16`) e cola o link dela na KaBuM!, na Terabyte e no Mercado Livre. O site lê os preços, confere se as três páginas são mesmo o mesmo produto e mostra um card com foto, o melhor preço e uma barra de preço por loja.

Referências de produto (inspiração, não cópia): **Buscapé** e **Zoom** (comparação + histórico + lojas verificadas), **Keepa/CamelCamelCamel** (gráfico de histórico).

## Por que existe
É um **projeto de portfólio** para conseguir estágio ou vaga júnior (veja o CLAUDE.md global). Ele conversa com empresas de e-commerce como o Mercado Livre e precisa mostrar: resolução de problemas, código organizado, SQL, testes e tratamento de erros. **Qualidade e clareza importam mais do que quantidade de funcionalidades.**

## Como trabalhar neste projeto (importante)
O Guilherme está no 2º semestre e **precisa conseguir explicar cada linha em entrevista**. Por isso:
- **Passos pequenos.** Uma coisa de cada vez, na ordem do roteiro abaixo. Não pule fases nem adiante funcionalidades.
- **Explique antes de fazer.** Antes de escrever código, diga em português simples o que vai fazer e por quê. Quando aparecer um conceito novo (ex.: parsing de HTML, SQL, mock, Decimal, template), explique em poucas frases.
- **Ele precisa entender o que foi feito.** Ao fim de cada passo, resuma o que mudou e pergunte se ficou claro antes de seguir.
- **Explique antes de instalar dependência.** Diga o que a biblioteca faz e por que ela é necessária.
- **Sugira um commit ao fim de cada passo**, com mensagem clara.
- **Registre os problemas.** Sempre que algo der errado e for resolvido (site bloqueou, formato de preço estranho, teste falhando), anote em `docs/problemas-resolvidos.md` no formato **Problema → Processo → Solução → Resultado**. Isso vira seção do README e assunto de entrevista.
- **Atualize o diário.** Ao terminar cada etapa, acrescente uma seção em `docs/diario.md` (objetivo, o que foi adicionado, conceitos para entrevista, problemas, número de testes, commit sugerido) e atualize a linha do tempo e os próximos passos.

## Decisões de escopo
- **O usuário cadastra os links manualmente**, um por loja (decidido de novo em 2026-09-14, depois de considerar busca por nome). O programa **não** busca o produto sozinho nas lojas. A busca por nome continua como ideia futura, só depois que o resto estiver pronto.
- **O mesmo produto é garantido por um código, não pelo nome.** O código é **opcional** e aceita código do fabricante ou **EAN** (código de barras, útil em perfumes e roupas). Códigos parecidos são produtos diferentes (`KF432C16BB1/16` ≠ `KF432C16BB/16`). A conferência compara EAN com `gtin` e código do fabricante com `mpn` do JSON-LD; senão procura o código como palavra inteira no nome. Oferta com código diferente **nunca** vira melhor preço. Sem código, a oferta fica "não confirmada".
- **Categorias:** barra lateral com Eletrônicos, Vestuário e Perfumes (criadas no banco). O usuário cria, edita (nome e ícone) e exclui pelo site; categoria com produtos não pode ser excluída. O ícone é escolhido numa **lista fixa de ícones universais** (`monitor/icons.py`, desenhos do Lucide em `_icons.html`), validada no servidor.
- **Telas** (decisão de 2026-09-14): grade de cards pequenos só com foto e nome; o card abre a **tela do produto**, com fontes e preços, botão "Adicionar fonte", gráfico de linhas do histórico e produtos parecidos. Ao cadastrar, código repetido é bloqueado e nome parecido pede confirmação ("Salvar mesmo assim").
- **Site desde já:** interface web simples com Flask. Sem CLI por enquanto.
- **Configurações:** tema (Automático/Claro/Escuro, padrão "Automático") e fonte (Padrão · Nunito Sans + Bowlby One · Oswald + Indie Flower, padrão "Padrão") ficam salvos no SQLite (tabela `settings`, uma linha por opção), gravados juntos numa transação só. O padrão de cada um é sempre o que o site já fazia antes de existir a tela de Configurações (tema segue o sistema; fonte é a do sistema).
- **Animações:** cada animação tem um interruptor liga/desliga em Configurações → Animações (hoje: brilho nos cards, ligado por padrão). Nenhuma aparece com "reduzir movimento" do sistema. Componentes de referência em React (21st.dev) são **reescritos em CSS/JS puro**, sem adicionar React/Tailwind ao projeto.
- **Loja bloqueou = capturar ou digitar o preço.** Se a leitura automática falhar, o card mostra o motivo. O usuário pode usar o **favorito "Capturar preço"** (bookmarklet que lê a página que ele mesmo abriu e só salva após confirmação; origem `capture`) ou informar o preço à mão (origem `manual`). **Nunca burlar proteções** (nada de fingir navegador, proxy, captcha ou modos "stealth" de bibliotecas como o Scrapling). Pedido de novo em 2026-09-16 e recusado de novo: os caminhos legítimos são **API oficial** (feita para o Mercado Livre), o favorito "Capturar preço" e adicionar lojas que publicam os dados.
- **Verificação agendada:** todo dia às **12:30** (horário de Brasília), pelo Agendador de Tarefas do Windows chamando `scripts/verificacao-diaria.cmd`. Pausa de 3 s entre produtos e log em `data/verificacao-diaria.log`.
- **Mudança de esquema com dados reais:** escrever migração em `db.py` (ex.: `_migrate_allow_capture_source`), testada a partir de um banco no formato antigo. **Fazer backup de `data/monitor.db` antes**, porque o servidor em `--debug` roda o `init_db` a cada arquivo salvo.
- **Contas (2026-09-16):** o site tem cadastro e login (tabela `users`, senha só como *hash*). **Visitante vê, mas não mexe:** todo POST e as telas que só servem para mudar dados exigem login. Os **produtos continuam compartilhados** entre as contas; cada conta serve para entrar e receber os alertas de preço no e-mail dela.
- **Alerta de preço:** e-mail quando o melhor preço de um produto cair **4% ou mais** em relação ao último melhor preço conhecido; depois de avisar, o preço novo vira a referência (não repetir aviso). O envio usa **SMTP** (`smtplib`), com as credenciais no `.env` (veja `.env.example`); se o e-mail falhar, o site continua funcionando e o alerta fica sem `emailed_at` para tentar depois. Nos testes, `create_app` recebe um `send_email` falso.
- **Sem estoque não vira melhor preço**, mas continua aparecendo.
- **Sem IA ou LLM** no núcleo.

## Situação das lojas (testado em 2026-09-14)
| Loja | Leitura automática | Observação |
|---|---|---|
| KaBuM! | ✅ JSON-LD | Precisa de `Accept`/`Accept-Language`; sem eles dá timeout. Código do fabricante vem no nome |
| Terabyte | ✅ JSON-LD | Com `urllib` deu 403; com `requests` funciona. Código vem no campo `mpn` |
| Amazon | ✅ HTML (`monitor/amazon.py`) | Sem JSON-LD. A mesma URL alterna entre layout com oferta principal e só "outras ofertas"; no segundo caso o leitor registra erro em vez de usar o preço "a partir de" |
| Mercado Livre | ✅ API oficial (`monitor/mercadolivre.py`) | A página bloqueia robôs. A leitura usa a **API oficial com OAuth**: crie a aplicação em developers.mercadolivre.com.br, ponha App ID/Secret no `.env` e conecte em Configurações. Sem conexão, cai no antigo bloqueio e usa preço manual/captura |
| Magazine Luiza | ❌ | 403 até no `robots.txt`. Usar preço manual |

## Stack
- **Python 3.13.** No Windows desta máquina, o comando é `py` (`python` não funciona).
- `requests` para baixar as páginas.
- `beautifulsoup4` para achar o JSON-LD no HTML.
- `sqlite3` (já vem no Python) para produtos, links e histórico.
- **Flask** para o site: templates HTML (Jinja2) e cliente de teste já incluídos. Escolhido no lugar do FastAPI porque o site gera páginas HTML com formulários e precisa de menos peças.
- CSS próprio, sem framework (estilo minimalista, tokens em `:root`, modo claro/escuro, ícones SVG no estilo Lucide, nunca emoji). Barras de preço feitas com CSS.
- **Chart.js 4.5.1** para o gráfico de histórico, salvo em `monitor/static/vendor/` (funciona offline, versão fixa).
- **Fontes self-hosted** (Nunito Sans, Oswald, Bowlby One, Indie Flower) em `monitor/static/fonts/`, licença **SIL Open Font License 1.1** (ver `LICENSES.md` na mesma pasta) — mesmo motivo do Chart.js: funciona offline, sem depender de um CDN de terceiros.
- `pytest` para os testes.
- **GitHub Actions** (`.github/workflows/tests.yml`): roda o `pytest` no Ubuntu com Python 3.13 a cada push na `main` e em pull requests. Selo no README.

Comece com o mínimo e só adicione biblioteca quando houver necessidade real.

## Arquitetura
```
monitor-de-precos/
├── monitor/
│   ├── app.py          # Flask: create_app(), rotas, context_processor da barra lateral
│   ├── fetcher.py      # baixa páginas (User-Agent honesto, timeout, FetchError)
│   ├── readers.py      # escolhe o leitor pela loja (Amazon -> amazon.py, resto -> jsonld.py)
│   ├── jsonld.py       # extrai nome, preço (Decimal), foto, estoque, mpn e gtin
│   ├── amazon.py       # leitor por HTML da Amazon
│   ├── matching.py     # confere código do fabricante / EAN
│   ├── similar.py      # produtos parecidos (similaridade de Jaccard entre nomes)
│   ├── history.py      # dados do gráfico de linhas (datas x lojas)
│   ├── prices.py       # "R$ 1.299,90" <-> Decimal <-> centavos
│   ├── stores.py       # domínio da URL -> nome da loja
│   ├── db.py           # schema SQLite e consultas
│   ├── settings.py     # regras das Configurações (opções válidas, padrão, rótulos); sem SQL
│   ├── icons.py        # lista fixa de ícones que uma categoria pode usar (fonte única da verdade)
│   ├── checker.py      # verifica um link ou todos; uma falha não derruba as outras
│   ├── compare.py      # monta a comparação, escolhe o melhor preço e os limites do slider
│   ├── capture.py      # favorito "Capturar preço": gera o link javascript: e valida o que ele envia
│   ├── search.py       # barra de pesquisa (nome sem acentos, parte da palavra, código/EAN)
│   ├── auth.py         # contas: regras de e-mail/senha, cadastro, login (hash do Werkzeug)
│   ├── alerts.py       # regra da queda de 4% (preço de referência por produto), histórico e texto do e-mail
│   ├── emailer.py      # envio por SMTP (smtplib); configuração vem do .env
│   ├── mercadolivre.py # API oficial do Mercado Livre (OAuth, tokens, leitura de anúncio/catálogo)
│   ├── daily_check.py  # verificação agendada: roda sozinha, avisa por e-mail e grava log
│   ├── config.py       # leitor do .env (segredos fora do Git)
│   ├── templates/      # base (layout+barra lateral), index (grade), product, product_form, settings, parciais _*.html
│   └── static/         # style.css, js/product-chart.js, vendor/chart.umd.min.js, fonts/ (self-hosted, OFL)
├── tests/
│   ├── helpers.py      # URLs de exemplo, ids das categorias e read_fixture()
│   ├── conftest.py     # fixture `conn` (banco temporário)
│   └── fixtures/       # HTML real salvo: KaBuM!, Terabyte, Amazon (2 layouts, sem script/style), bloqueio do Mercado Livre
├── data/monitor.db     # banco local (fora do Git)
└── docs/problemas-resolvidos.md
```

**Banco (SQLite):** `categories` (nome único, ícone) → `products` (categoria, nome, código opcional, foto) → `links` (loja, URL) → `price_checks` (uma linha por verificação: `price_cents`, `in_stock`, `source` auto/manual/capture, `page_title`, `page_code`, `page_gtin`, `error`). `price_alerts` guarda cada queda de 4%+ (preço antigo, novo, loja, `emailed_at`), e `products.alert_reference_cents` é o preço de referência do alerta. Nada é sobrescrito: `price_checks` é o histórico. Preço em **centavos inteiros** porque o SQLite não tem decimal. `settings` (`key`, `value`) guarda as Configurações do site (tema, fonte, animações), uma linha por opção; todas as opções de um POST são gravadas juntas com UPSERT, numa única transação.

**Testes sem internet:** `checker.check_product` e `create_app` recebem uma função `fetch`. Nos testes, ela devolve HTML salvo em vez de acessar as lojas.

## Roteiro (fazer em ordem)
1. ✅ **Ambiente:** ambiente virtual, Git instalado e primeiros commits (2026-09-14).
2. ✅ **Base do site, banco e leitura de preço** (2026-09-14): cadastro de produto com links, leitura via JSON-LD, SQLite, card com melhor preço, preço manual, 61 testes.
3. ✅ **Categorias, tela do produto, gráfico e novas fontes** (2026-09-14): barra lateral com categorias, grade de cards, tela do produto com gráfico de linhas (Chart.js), produtos parecidos, adicionar/remover fonte, Amazon (leitor HTML) e Magazine Luiza (manual), código opcional/EAN, 140 testes.
4. **Mais lojas:** testar outras lojas (Pichau, lojas de perfume e roupa); adaptador específico só quando o JSON-LD genérico não servir.
5. **Verificação agendada:** checar todos os produtos algumas vezes por dia, sem abrir o site.
6. **Alerta:** avisar quando o preço cair (e-mail ou Telegram).
7. **CI:** testes rodando no GitHub Actions.
8. **Deploy:** site no ar com **modo demonstração** (dados salvos), porque servidores na nuvem costumam ser bloqueados pelas lojas.
9. **README bilíngue (PT/EN):** o que faz, GIF da demonstração, como rodar, decisões e problemas resolvidos.
10. *(Futuro, opcional)* **Busca por nome** do produto nas lojas.

## Regras técnicas
- **Dinheiro é sempre `Decimal`, nunca `float`.** Ler JSON com `json.loads(..., parse_float=Decimal)`. Guardar em centavos.
- **Testes nunca acessam a internet.** Use HTML salvo em `tests/fixtures/` e a função `fetch` falsa.
- **Espere falhas de rede e de site** (erro 403, captcha, página mudou, loja fora do ar). Toda requisição tem timeout. Uma loja falhar **não pode derrubar** a verificação das outras: registre o erro no histórico, mostre no card e siga.
- **Mudou o schema do banco?** `CREATE TABLE IF NOT EXISTS` não altera tabela existente. Enquanto não houver dados importantes, apagar `data/monitor.db`; depois, criar migração.
- **Código em inglês** (nomes de variáveis, funções e commits). Textos do site e explicações ao Guilherme em português.

## Uso responsável (scraping)
- Frequência baixa: no máximo algumas verificações por dia por produto.
- Só páginas públicas. Nunca páginas que exigem login.
- Respeite o `robots.txt` e identifique o programa com um User-Agent (`MonitorDePrecos/0.1`). Não fingir ser navegador.
- Uso pessoal. Não redistribuir dados das lojas. Fotos: usar o link da imagem da própria loja, sem baixar.
- Se uma loja bloquear, **documente o motivo e siga com as outras** (preço manual), sem tentar burlar proteções.

## Comandos
```powershell
py -m venv .venv                      # criar ambiente virtual (uma vez)
.venv\Scripts\Activate.ps1            # ativar
pip install -r requirements.txt       # instalar dependências
flask --app monitor.app run --debug   # site em http://127.0.0.1:5000
pytest                                # rodar testes
py -m monitor.daily_check             # rodar a verificação diária à mão
schtasks /Query /TN "Monitor de Precos - Verificacao diaria" /V /FO LIST   # conferir o agendamento
```

## Observações do ambiente
- Pasta dentro do **OneDrive**: a `.venv` tem milhares de arquivos e deixa a sincronização lenta. `.venv/` e `data/` já estão no `.gitignore`. Se a sincronização incomodar, considere mover o projeto para fora do OneDrive.
- **Git 2.55** instalado em 2026-09-14 (via `winget`). Branch `main`, autor configurado só no repositório. Remoto: **https://github.com/GuilhermeWaldemir/monitor-de-precos** (`origin`), com login salvo pelo Git Credential Manager. Se `git` não for reconhecido num terminal antigo, use `"$env:ProgramFiles\Git\cmd\git.exe"` ou abra um terminal novo.
- O arquivo `mudanças` (lista pessoal de pedidos) fica fora do Git (`.gitignore`).
- No PowerShell 5.1, mensagens de commit com aspas duplas quebram o `git commit -m`; use `git commit -F arquivo.txt`.
- Para ver o site pelo terminal sem abrir navegador: `msedge --headless=new --screenshot=arquivo.png --window-size=1100,900 http://127.0.0.1:5000/` (largura mínima real ~500px).
