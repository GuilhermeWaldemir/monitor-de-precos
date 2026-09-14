# Monitor de Preços

Compara o preço do **mesmo produto** em várias lojas online brasileiras, guarda o histórico e destaca o melhor preço.

> Projeto em construção. README completo (PT/EN, GIF de demonstração) virá na fase final.

## Como funciona

1. Você organiza os produtos em **categorias** (Eletrônicos, Vestuário, Perfumes ou as que criar).
2. Cadastra um produto com o link dele em cada loja e, se quiser, um **código do fabricante ou EAN** (ex.: `KF432C16BB1/16`).
3. O programa baixa cada página e lê preço, foto e estoque: pelo bloco **JSON-LD** (padrão schema.org) ou, na Amazon, pelo HTML.
4. Ele confere se cada página é mesmo aquele produto, comparando o código.
5. Cada verificação vai para o histórico no **SQLite**. A tela do produto mostra as lojas do mais barato ao mais caro, um **gráfico de linhas** com a variação de preço e os **produtos parecidos** que você já cadastrou.
6. Se uma loja bloquear o acesso automático, o erro aparece e você pode informar o preço manualmente.

| Loja | Leitura |
|---|---|
| KaBuM!, Terabyte | automática (JSON-LD) |
| Amazon | automática (HTML) |
| Mercado Livre, Magazine Luiza | manual (bloqueiam robôs) |

## Como rodar

Requer Python 3.13.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

flask --app monitor.app run --debug   # abre em http://127.0.0.1:5000
pytest                                # testes (não acessam a internet)
```

O banco é criado automaticamente em `data/monitor.db`, já com as três categorias iniciais.

## Estrutura

```
monitor/
├── app.py          # site (Flask): rotas e páginas
├── fetcher.py      # baixa as páginas, com timeout e erros claros
├── readers.py      # escolhe o leitor de cada loja
├── jsonld.py       # lê nome, preço, foto, estoque e códigos do JSON-LD
├── amazon.py       # lê a página da Amazon pelo HTML
├── matching.py     # confere código do fabricante / EAN
├── similar.py      # encontra produtos parecidos (similaridade de Jaccard)
├── history.py      # prepara os dados do gráfico
├── prices.py       # Decimal, centavos e formato "R$ 1.299,90"
├── stores.py       # descobre a loja pela URL
├── db.py           # SQLite: categorias, produtos, links e histórico
├── checker.py      # verifica os links; uma loja falhar não derruba as outras
├── compare.py      # monta a comparação e escolhe o melhor preço
├── templates/      # HTML (Jinja2)
└── static/         # CSS, JS do gráfico e Chart.js
tests/
└── fixtures/       # páginas reais salvas das lojas
```

## Diário e problemas resolvidos

- [docs/diario.md](docs/diario.md): o que foi construído em cada etapa e o que vem a seguir.
- [docs/problemas-resolvidos.md](docs/problemas-resolvidos.md): problemas reais e como foram resolvidos.
