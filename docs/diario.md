# Diário do projeto: Monitor de Preços

Registro, em ordem, de tudo o que foi construído: o que cada etapa acrescentou, por que foi feito, o que se aprendeu e o que falta.

**Legenda:** ✅ concluído · 🔍 em revisão · ⏳ próximo · 💡 ideia futura

Os problemas citados (ex.: *Problema 7*) estão detalhados em [problemas-resolvidos.md](problemas-resolvidos.md).

---

## Linha do tempo

```
Etapa 0  Planejamento ........................ ✅
Etapa 1  Base: site, banco e leitura de preço  ✅   61 testes
Etapa 2  Categorias, tela do produto, gráfico  ✅  140 testes
Etapa 3  Barra de pesquisa ................... ✅  161 testes
Etapa 4  Configurações + tema ................ ✅  173 testes
Etapa 5  Fontes nas Configurações ............ ✅  185 testes
Etapa 6  Ícones para categorias .............. ✅  198 testes
Etapa 7  Brilho suave nos cards .............. ✅  205 testes
Etapa 8  Animação de pontinhos nas categorias  🔍  210 testes
Etapa 9  Slider de preço ..................... 🔍  217 testes
Etapa 10 Favorito "Capturar preço" ........... 🔍  245 testes
Etapa 11+ ver "Próximos passos"
```

---

## Etapa 0: Planejamento ✅
*2026-09-14*

**Objetivo:** decidir o que o projeto faz antes de escrever código.

**O que foi feito**
- Criado o `CLAUDE.md` com o objetivo (projeto de portfólio), as regras técnicas e o roteiro.
- Pesquisa de como comparadores de preço funcionam (Buscapé, Zoom, Google Shopping) e de onde vêm os dados: página da loja, API oficial, agregador pago, API de afiliados.
- Primeira ideia considerada: o usuário pesquisa **pelo nome** e o programa busca nas lojas. **Decisão final:** o usuário **cola os links**. Casar "o mesmo produto" entre lojas diferentes é difícil demais para o começo.

**Aprendizados**
- A API de busca do Mercado Livre passou a devolver 403 para muitos desenvolvedores desde 2025.
- Muitas lojas publicam os dados do produto num bloco **JSON-LD** (padrão schema.org).

---

## Etapa 1: A base (site, banco e leitura de preço) ✅
*2026-09-14 · 61 testes*

**Objetivo:** cadastrar um produto com os links de várias lojas, ler os preços e mostrar o mais barato.

**Produto de teste:** memória Kingston Fury Beast 16GB DDR4 3200MHz, código **KF432C16BB1/16**, na KaBuM!, na Terabyte e no Mercado Livre.

**O que foi adicionado**
| Parte | Arquivo | O que faz |
|---|---|---|
| Preços | `monitor/prices.py` | Converte "R$ 1.299,90" ↔ `Decimal` ↔ centavos |
| Download | `monitor/fetcher.py` | Baixa a página com User-Agent honesto, timeout e erros claros |
| Leitura | `monitor/jsonld.py` | Lê nome, preço, foto e estoque do JSON-LD |
| Mesmo produto | `monitor/matching.py` | Confere o código do fabricante na página |
| Lojas | `monitor/stores.py` | Descobre a loja pela URL |
| Banco | `monitor/db.py` | SQLite: `products` → `links` → `price_checks` (histórico) |
| Verificação | `monitor/checker.py` | Verifica todos os links; uma loja falhar não derruba as outras |
| Comparação | `monitor/compare.py` | Ordena as lojas e escolhe o melhor preço |
| Site | `monitor/app.py` + templates | Flask: lista de cards, formulário, "Verificar preços", preço manual |

**Situação das lojas**
- **KaBuM!** e **Terabyte:** leitura automática.
- **Mercado Livre:** bloqueia robôs, então o preço é informado manualmente.

**Conceitos para explicar em entrevista**
- **`Decimal` em vez de `float`**: o `float` não representa centavos com exatidão.
- **Preço em centavos inteiros no SQLite**, porque o SQLite não tem tipo decimal.
- **Histórico sem sobrescrever:** cada verificação é uma linha nova.
- **Isolamento de falhas:** um `try/except` por loja.
- **Testes sem internet:** HTML real salvo em `tests/fixtures/` e uma função `fetch` falsa (injeção de dependência).

**Problemas resolvidos:** 1 (anti-robô do Mercado Livre), 2 (403 na Terabyte), 3 (timeout na KaBuM!), 4 (JSON lido como float), 5 (códigos quase iguais: `BB1/16` × `BB/16`).

**Commit sugerido:** `feat: add web app, SQLite storage and JSON-LD price checks for KaBuM!, Terabyte and Mercado Livre`

---

## Etapa 2: Categorias, tela do produto, gráfico e novas lojas ✅
*2026-09-14 · 140 testes*

**Objetivo:** organizar muitos produtos sem poluir a tela, e mostrar a evolução do preço.

**O que foi adicionado**

1. **Categorias**
   - Barra lateral com Eletrônicos, Vestuário e Perfumes.
   - O usuário cria, renomeia e exclui categorias. Categoria com produtos não pode ser excluída.
   - Nova tabela `categories`; cada produto aponta para uma categoria (chave estrangeira).
2. **Grade de cards**
   - Cards pequenos, só com foto e nome. Clicar abre a tela do produto.
3. **Tela do produto**
   - Melhor preço em destaque.
   - Fontes e preços, com os botões "Adicionar fonte" e "remover".
   - **Gráfico de linhas** com a variação de preço (Chart.js), mais uma tabela com os mesmos dados.
   - **Produtos parecidos** já cadastrados.
4. **Evitar duplicados**
   - Código repetido é bloqueado.
   - Nome parecido pede "Salvar mesmo assim".
   - A semelhança entre nomes usa a **similaridade de Jaccard** (`monitor/similar.py`).
5. **Código opcional**
   - Aceita código do fabricante ou **EAN** (código de barras), pensando em perfumes e roupas.
6. **Novas lojas**
   - **Amazon:** leitor próprio por HTML (`monitor/amazon.py`).
   - **Magazine Luiza:** preço manual, porque bloqueia robôs.
   - `monitor/readers.py` escolhe o leitor certo para cada loja.
7. **Design**
   - Estilo minimalista, modo claro e escuro, ícones SVG, foco visível no teclado, layout para celular.

**Conceitos para explicar em entrevista**
- **Chave estrangeira** e `ON DELETE RESTRICT`/`CASCADE`.
- **`LEFT JOIN` + `COUNT`** para contar produtos por categoria, incluindo as vazias.
- **Similaridade de Jaccard:** palavras em comum ÷ total de palavras diferentes.
- **Padrão "um leitor por loja"** (`reader_for`): adicionar uma loja = um arquivo novo.
- **Dados do gráfico preparados no Python** e enviados como JSON para o JavaScript.

**Problemas resolvidos:** 6 (Magazine Luiza 403), 7 (Amazon sem JSON-LD e com dois layouts), 8 (fixture da Amazon grande demais), 9 (identificar perfumes e roupas por EAN).

**Commit sugerido:** `feat: add categories, product page with price history chart, similar products and Amazon/Magalu sources`

---

## Etapa 3: Barra de pesquisa ✅
*2026-09-14 · 161 testes*

**Objetivo:** achar rápido um produto já cadastrado.

**O que foi adicionado**
- **Barra de pesquisa** no topo de todas as páginas.
  - Lupa, botão × para limpar e atalho da tecla `/`.
  - Anel verde ao focar.
  - No celular, ocupa uma linha inteira.
- **Busca** (`monitor/search.py`):
  - ignora maiúsculas e acentos;
  - aceita parte da palavra ("king" acha "Kingston");
  - exige todas as palavras;
  - ignora palavras pequenas ("de", "para");
  - também busca pelo código do fabricante ou EAN.
- **Página de resultados** (`/search?q=...`), com a mesma grade de cards e uma mensagem quando nada é encontrado.
- **Reorganização:** `normalize_text` foi separada em `monitor/similar.py`, para servir à busca e aos produtos parecidos.

**Conceitos para explicar em entrevista**
- **Normalização Unicode (NFKD)** para remover acentos.
- **Formulário `GET`:** a busca vira uma URL que dá para compartilhar ou salvar nos favoritos.
- **CSS sem JavaScript para mostrar o ×:** o seletor `:placeholder-shown` sabe se o campo tem texto.

**Commit sugerido:** `feat: add product search bar (name, partial words, code/EAN)`

---

## Etapa 4: Configurações + tema ✅
*2026-09-14 · 173 testes*

**Objetivo:** dar ao usuário uma tela de Configurações para escolher o tema do site (Automático, Claro ou Escuro), mantendo "seguir o sistema" como comportamento padrão.

**O que foi adicionado**
- **Tabela `settings`** no SQLite: uma linha por opção (`key`, `value`). Hoje só existe `theme`; opções futuras (fonte, cor de destaque...) entram como novas linhas, sem mudar a tabela.
- **`monitor/settings.py`**: as regras de cada opção (`CHOICES`, `DEFAULTS`, rótulos em português), separadas do SQL. `load_settings` devolve os padrões combinados com o que foi salvo, ignorando chaves desconhecidas e valores salvos que não são mais válidos. `save_settings` valida tudo antes de gravar qualquer coisa (nada é salvo se um valor for inválido).
- **Página `/settings`**: um `fieldset` com três cartões (Automático, Claro, Escuro), cada um com uma pré-visualização em miniatura, rótulo e descrição. O cartão inteiro é clicável (é um `<label>`), mas o campo de rádio continua visível e acessível pelo teclado.
- **Pré-visualização ao vivo**: um JavaScript pequeno muda `data-theme` no `<html>` assim que o rádio muda, antes mesmo de salvar. Salvar (POST) grava no banco e vale para as próximas visitas.
- **Link "Configurações"** na barra lateral, com ícone de engrenagem, separado das categorias por uma linha (também funciona no layout de "chips" do celular).
- **CSS:** os tokens de tema escuro agora existem em dois blocos idênticos — um para `data-theme="dark"` (escolha explícita) e outro dentro de `@media (prefers-color-scheme: dark)` para `data-theme="auto"` (segue o sistema). Um teste (`tests/test_css.py`) garante que os dois nunca fiquem diferentes.

**Conceitos para explicar em entrevista**
- **UPSERT** (`INSERT ... ON CONFLICT DO UPDATE`): grava ou atualiza a configuração em uma única instrução, sem precisar checar antes se a linha já existe.
- **`data-*` attribute + CSS custom properties:** o Python decide o valor (`auto`/`light`/`dark`) e escreve no HTML; o CSS reage a esse atributo trocando as variáveis de cor. Não precisa de JavaScript para o tema já vir certo no primeiro carregamento da página.
- **Padrão PRG (Post/Redirect/Get):** salvar as configurações faz um POST, mas a resposta é um redirect para um GET em `/settings` — atualizar a página (F5) não reenvia o formulário.
- **Por que o padrão é "automático":** o site já seguia o sistema antes de existir uma tela de Configurações; esse comportamento não pode mudar sozinho, por isso `DEFAULTS["theme"] = "auto"`, e não `"light"`.
- **Separar regra de SQL:** `monitor/settings.py` não conhece `sqlite3` — só chama `db.get_settings_rows` e `db.save_setting`. Adicionar uma opção nova (fonte, cor) não vai exigir tocar na camada de banco.

**Commit sugerido:** `feat: add settings page with theme choice (auto/light/dark) saved in SQLite`

---

## Etapa 5: Fontes ✅
*2026-09-14 · 185 testes*

**Objetivo:** deixar o usuário escolher a combinação de fontes do site nas Configurações, mantendo a fonte do sistema ("Padrão") como comportamento atual, sem depender de internet.

**O que foi adicionado**
- **Fontes baixadas e guardadas no próprio projeto** (`monitor/static/fonts/`), do mesmo jeito que o Chart.js já ficava em `static/vendor/`: Nunito Sans, Oswald (peso variável), Bowlby One e Indie Flower (peso 400), subconjunto **latin** (cobre os acentos do português). Licença **SIL Open Font License 1.1** para todas — ficou documentado em `monitor/static/fonts/LICENSES.md`.
- **Três opções em Configurações → Fonte**: Padrão (fonte do sistema), Nunito Sans + Bowlby One (títulos marcantes, texto arredondado) e Oswald + Indie Flower (títulos condensados, texto manuscrito). Cada cartão mostra sua própria combinação ("Aa" + título + frase de exemplo), igual ao cartão de tema mostrar claro/escuro mesmo sem estar selecionado.
- **`monitor/settings.py`** ganhou a chave `"font"` em `CHOICES`/`DEFAULTS` e os rótulos/descrições em português — sem tocar em `monitor/db.py` além do necessário.
- **Salvar tema e fonte é uma transação só:** `db.save_settings_rows` grava todas as chaves com um único `executemany` dentro de um `with conn:`. Se um valor for inválido, `settings.save_settings` já rejeita antes de chamar o banco, então nada fica salvo pela metade. A função antiga `save_setting` (uma chave por vez) foi removida — não tinha mais uso.
- **CSS com `@font-face`** (`font-display: swap`) e tokens novos (`--font-body`, `--font-heading`, `--heading-weight`, `--font-body-size`), trocados por `:root[data-font="..."]`. A opção "Padrão" não referencia nenhuma fonte baixada, então o navegador não baixa arquivo nenhum ao escolhê-la.
- **JavaScript da pré-visualização generalizado:** antes só existia para o tema; agora um único trecho lê `data-preview="theme"`/`data-preview="font"` de cada `<fieldset>` e aplica o atributo certo em `<html>`, sem duplicar código.

**Conceitos para explicar em entrevista**
- **`@font-face` e self-hosting:** declarar uma fonte a partir de um arquivo `.woff2` guardado no próprio projeto, em vez de carregar de um Google Fonts/CDN — funciona offline e não depende de terceiros no ar.
- **`font-display: swap`:** o texto aparece na hora com a fonte reserva (`--font-system`) e troca para a fonte baixada assim que ela chega, em vez de ficar invisível esperando.
- **Fonte variável (*variable font*):** um único arquivo (Nunito Sans, Oswald) cobre uma faixa inteira de pesos (`font-weight: 200 1000`), em vez de um arquivo por peso.
- **CSS custom properties por `data-*` attribute:** o mesmo padrão da Etapa 4 (tema), agora reaproveitado para fonte — o Python escreve `data-font` no HTML, o CSS troca as variáveis.
- **Transação tudo-ou-nada (`with conn:` + `executemany`):** salvar duas configurações de uma vez não pode deixar só uma delas gravada se a conexão cair no meio.

**Commit sugerido:** `feat: add self-hosted font pairing choice to settings (single-transaction save)`

---

## Etapa 6: Ícones para categorias ✅
*2026-09-14 · 198 testes*

**Objetivo:** permitir escolher um ícone ao criar uma categoria, e trocá-lo depois. Antes, toda categoria nova recebia a mesma etiqueta.

**O que foi adicionado**
- **Lista fixa de 20 ícones universais** em `monitor/icons.py` (`CATEGORY_ICONS`): Geral, Eletrônicos, Celulares, Áudio, Games, Roupas, Perfumes, Beleza, Casa, Cozinha, Móveis, Ferramentas, Automotivo, Esportes, Livros, Bebês, Pets, Presentes, Relógios, Favoritos.
  - Os desenhos foram copiados do **Lucide** (licença ISC) para `_icons.html`.
- **Validação no servidor:** `create_category` e `update_category` (que substitui `rename_category`) só aceitam ícones da lista. Qualquer outro valor recebe o erro "Escolha um ícone da lista."
- **Seletor de ícones** (`_icon_picker.html`), usado em dois lugares:
  - no formulário **Nova categoria** da barra lateral (com "Geral" já marcado);
  - no botão **Editar** da página da categoria (que antes era "Renomear"), com nome e ícone.
  - Rota nova: `POST /categories/<id>/edit`.
- **Acessibilidade:** cada ícone é um botão de rádio escondido visualmente, mas que continua funcionando com teclado (setas) e leitor de tela. O rótulo em português aparece como dica ao passar o mouse. O ícone escolhido fica em verde e o foco do teclado tem contorno visível.
- **Testes:**
  - ícone válido, inválido e padrão;
  - edição de nome e ícone;
  - um teste que confere se **cada ícone da lista tem desenho próprio** em `_icons.html`, para ninguém adicionar um nome e esquecer o desenho.

**Conceitos para explicar em entrevista**
- **Fonte única da verdade:** a mesma lista (`CATEGORY_ICONS`) alimenta o formulário e a validação.
- **Lista de permitidos (*allow-list*) no servidor:** o navegador pode mandar qualquer texto, então o servidor só aceita valores conhecidos. Por isso o ícone não é texto livre.
- **Grupo de rádios acessível:** o `<input>` fica escondido com `.sr-only` (não com `display: none`, que o tiraria do teclado) e o `<label>` mostra o estado com `input:checked + label` e `input:focus-visible + label`.

**Commit sugerido:** `feat: let users pick an icon for each category`

---

## Etapa 7: Brilho suave nos cards ✅
*2026-09-14 · 205 testes*

**Objetivo:** dar um toque de interação aos cards de produto (uma luz fraca que segue o mouse), com a opção de desligar nas Configurações.

**O que foi adicionado**
- **Efeito "spotlight"** inspirado no componente do 21st.dev (@jahed), **reescrito sem React** e bem mais suave:
  - `::before` desenha um anel fino de luz na borda do card, no ponto onde está o mouse;
  - `::after` põe um brilho quase transparente dentro do card;
  - as duas camadas usam a cor de destaque do tema e têm `pointer-events: none`, então nunca atrapalham o clique.
- **`static/js/card-glow.js`:** poucas linhas. Só calcula a posição do mouse em relação ao card e grava em `--glow-x`/`--glow-y`. O desenho e a decisão de mostrar ficam no CSS.
- **Só aparece quando faz sentido:** com mouse (`hover: hover`), com a opção ligada (`data-card-glow="on"`) e sem "reduzir movimento" no sistema.
- **Configurações → Animações:**
  - nova seção com o interruptor **"Brilho nos cards"** (ligado por padrão);
  - um card de exemplo para testar ali mesmo;
  - pré-visualização ao vivo ao ligar e desligar;
  - a seção já está pronta para o interruptor da animação da Tarefa 8.
- **Interruptor acessível:** é um checkbox de verdade (`role="switch"`), só com visual novo.
- **Testes mais resistentes:** os testes de Configurações passaram a comparar "padrões + mudanças" (`defaults_with(...)`), então uma opção nova não quebra testes antigos (*Problema 10*).

**Conceitos para explicar em entrevista**
- **Checkbox desmarcado não é enviado:** por isso existe um campo escondido `off` antes dele. Quando o checkbox está marcado, chegam os dois valores, e o servidor usa o último (`request.form.getlist(key)[-1]`).
- **Pseudo-elementos (`::before`/`::after`) e `mask-composite`:** "pintar a caixa inteira e recortar o miolo" deixa só a borda iluminada.
- **Separar comportamento de visual:** o JavaScript só informa números, e o CSS decide o que desenhar e quando.
- **Media queries de capacidade e preferência:** `(hover: hover)` detecta mouse, e `prefers-reduced-motion` respeita quem pediu menos movimento.

**Problemas resolvidos:** 10 (testes que quebravam a cada opção nova).

**Commit sugerido:** `feat: add subtle glow on product cards with on/off switch in settings`

---

## Etapa 8: Animação de pontinhos nas categorias 🔍
*2026-09-14 · 210 testes*

**Objetivo:** ao abrir uma categoria, mostrar uma faixa em que uma grade de pontinhos forma o ícone da categoria, com a opção de desligar.

**O que foi adicionado**
- **Faixa no topo** da página de cada categoria e de "Todos" (que usa o ícone de grade). A busca não tem faixa.
  - Os pontos crescem a partir da linha do meio até formar o ícone, que fica parado.
  - Clicar na faixa repete a animação.
- **`static/js/dot-transition.js`:** o componente React "Dot Transition" (21st.dev/@hyperiux) **portado para JavaScript puro**, com a mesma lógica:
  1. o SVG do ícone (o mesmo da barra lateral, vindo de um `<template>`) vira uma imagem branca;
  2. a imagem é desenhada num canvas minúsculo, **com um pixel por pontinho**, e a transparência de cada pixel vira a "máscara";
  3. a cada quadro, uma faixa que se abre do centro faz os pontos cobertos pelo ícone crescerem e acenderem.
  - Simplificações em relação ao original: sem ciclo de várias imagens, sem pausa por visibilidade (a animação dura só 1,4 s e para sozinha) e sem React.
- **Configurações → Animações:** interruptor **"Animação das categorias"** (ligado por padrão). Desligado, a faixa e o script nem são enviados para a página.
- **Acessibilidade:** a faixa é decorativa (`aria-hidden`). Com "reduzir movimento", o ícone aparece pronto, sem animação.

**Conceitos para explicar em entrevista**
- **Canvas 2D e `requestAnimationFrame`:** desenhar quadro a quadro, sincronizado com a tela, e parar o loop quando termina.
- **Máscara por *downsampling*:** reduzir a imagem ao tamanho da grade e ler o canal alfa com `getImageData`.
- **Suavização (`smoothstep`/`smootherstep`) e interpolação (`lerp`):** matemática simples para movimentos que não parecem mecânicos.
- **`devicePixelRatio`:** o canvas é criado com mais pixels em telas de alta densidade, para não ficar borrado.
- **Escopo de variáveis no Jinja:** um `{% set %}` dentro de um bloco não é visível em outro bloco, por isso `show_dot_banner` fica no topo do template.

**Commit sugerido:** `feat: add dot animation forming the category icon (vanilla JS port, toggle in settings)`

---

## Etapa 9: Slider de preço 🔍
*2026-09-14 · 217 testes*

**Objetivo:** filtrar a grade de produtos por um limite de preço ("Preço até R$ X"), sem mostrar preço nos cards.

**O que foi adicionado**
- **Melhor preço de cada produto calculado no servidor** (`compare.best_prices`), com as mesmas regras da tela do produto (sem estoque e código diferente não contam). O valor vai para o HTML como `data-price` em cada item da grade, e o card continua só com foto e nome.
- **Limites do slider** (`compare.price_range`): do menor preço arredondado para baixo até o maior arredondado para cima. Se todos os produtos têm o mesmo preço, o slider começa em R$ 0, para ter por onde se mover.
- **Slider acima da grade** na página inicial, nas categorias e na busca:
  - mostra "Qualquer preço" quando está no máximo, ou o valor formatado em reais;
  - mostra os limites embaixo e o contador "Mostrando X de Y" (lido por leitores de tela com `aria-live`);
  - quando nada sobra, aparece uma mensagem.
- **`static/js/price-filter.js`:** filtra na hora, sem recarregar. **Produtos sem preço somem quando há limite** e aparecem de novo com o slider no máximo.
- **Visual:** trilho com a parte preenchida na cor de destaque (`--fill`), bolinha com anel ao passar o mouse ou focar pelo teclado. As setas do teclado movem o slider.
- **Pequena refatoração:** as três páginas de grade passaram a usar um único `render_grid`, em vez de repetir o mesmo `render_template`.

**Conceitos para explicar em entrevista**
- **Dados para o JavaScript via `data-*`:** o servidor calcula, o HTML carrega e o JavaScript só lê. Não precisou de API nova.
- **`Decimal` no servidor, `Number` só na tela:** o JavaScript converte o preço apenas para comparar com o slider. O valor exato continua sendo o do servidor.
- **Estilizar `<input type="range">`:** cada navegador tem pseudo-elementos próprios (`::-webkit-slider-thumb`, `::-moz-range-thumb`), mas continua sendo um controle nativo e acessível.
- **Arredondamento com `math.floor`/`math.ceil`** para limites que sempre incluem todos os preços.

**Commit sugerido:** `feat: add price limit slider to filter the product grid by best price`

---

## Etapa 10: Favorito "Capturar preço" 🔍
*2026-09-14 · 245 testes*

**Objetivo:** depender menos do preço digitado à mão nas lojas que bloqueiam robôs (Mercado Livre, Magazine Luiza), **sem burlar nenhuma proteção**.

**Como funciona**
1. Em **Configurações → Capturar preço do navegador**, o usuário arrasta o botão para a barra de favoritos.
2. Na loja, ele abre a página do produto normalmente e clica no favorito.
3. O favorito (`static/js/bookmarklet.js`) roda **dentro da página que o usuário já está vendo**. Ele lê nome, preço, foto, código do fabricante e EAN, primeiro pelo JSON-LD e depois por metadados de preço ou pelo preço visível da Amazon, e abre `/capture` no site local numa aba nova.
4. A página `/capture` **não salva nada**. Ela mostra o que foi lido e reconhece se a página já é fonte de algum produto, mesmo com o link escrito de outro jeito. Também confere o código.
5. O usuário confere e clica em **Salvar preço**. O preço entra no histórico com a origem `capture` ("capturado da página") e passa a valer para o melhor preço e o gráfico. Se a página ainda não é fonte, dá para escolher um produto ou **cadastrar um novo** com os dados já preenchidos.

**O que foi adicionado**
- `monitor/capture.py`:
  - `bookmarklet_href` monta o link `javascript:` a partir do arquivo `.js`, com o endereço do site;
  - `read_captured` valida o que chega (link http(s), preço, foto só `http(s)`, textos com no máximo 300 caracteres).
- `stores.link_key`: a mesma página escrita de formas diferentes gera a mesma chave (ASIN da Amazon, `MLB…` do Mercado Livre, `/p/<id>/` da Magazine Luiza; nas outras lojas, ignora `www`, `?…`, `#…` e `/` final).
- `db.find_links_for_url` e **migração** da tabela `price_checks` para aceitar a origem `capture`, sem perder o histórico (*Problema 11*).
- Rotas `GET /capture` (só mostra) e `POST /capture` (salva e confere se o link escolhido é mesmo a página capturada). O formulário de novo produto aceita dados preenchidos pela URL.
- Testes: link do favorito, validação, `link_key`, migração a partir de um banco antigo e as rotas. O JavaScript do favorito foi executado no Edge em modo invisível, em duas páginas de loja simuladas.

**Conceitos para explicar em entrevista**
- **Bookmarklet:** um favorito cujo endereço é `javascript:…`. Ele roda no contexto da página aberta, por isso lê o que o usuário vê, sem robô.
- **GET não altera dados, POST sim:** abrir `/capture` nunca grava nada; só a confirmação (POST) grava.
- **Dados de terceiros são não confiáveis:** tudo é validado de novo no servidor, e o Jinja escapa o HTML automaticamente.
- **Migração de esquema no SQLite:** a receita "criar nova, copiar, apagar, renomear" dentro de uma transação.
- **Normalização de URL** para reconhecer a mesma entidade escrita de formas diferentes.

**Limitação conhecida:** o site não tem proteção CSRF (vale para todas as rotas POST, não só esta). Para uso local isso é aceitável, mas precisa entrar antes de publicar o site na internet.

**Problemas resolvidos:** 11 (mudar um `CHECK` numa tabela com dados).

**Commit sugerido:** `feat: add "Capturar preço" bookmarklet with confirmation page and price_checks migration`

---

## Próximos passos

Tarefas do arquivo `mudanças`, feitas **uma por vez**, com revisão entre elas:

| # | Etapa | Status |
|---|---|---|
| 4 | **Configurações + tema** (Automático, Claro, Escuro), salvo no SQLite | ✅ |
| 5 | **Fontes** nas Configurações (Padrão · Nunito Sans + Bowlby One · Oswald + Indie Flower) | ✅ |
| 6 | **Ícones** para escolher ao criar uma categoria | ✅ |
| 7 | **Brilho suave nos cards** (spotlight), que pode ser desligado | ✅ |
| 8 | **Animação de pontinhos** formando o ícone ao trocar de categoria, que pode ser desligada | 🔍 |
| 9 | **Slider de preço** para filtrar a grade ("Até R$ X"); produtos sem preço somem com o filtro | 🔍 |
| 10 | **Favorito "Capturar preço"** (bookmarklet) para não depender de preço manual, sem burlar proteção | 🔍 |

Todas as tarefas do arquivo `mudanças` estão implementadas. Falta a revisão das etapas 8, 9 e 10.

Roteiro geral do projeto (depois das tarefas acima):

| Etapa | Status |
|---|---|
| Instalar o Git e fazer os commits | ✅ 2026-09-14: 6 commits por área (configuração, leitura de preços, banco e lógica, site, testes, documentação) |
| Criar o repositório no GitHub e enviar (`git push`) | ⏳ |
| Verificação agendada (algumas vezes por dia) | 💡 |
| Alerta de queda de preço (e-mail ou Telegram) | 💡 |
| Testes no GitHub Actions (CI) | 💡 |
| Deploy com modo demonstração | 💡 |
| README bilíngue com GIF | 💡 |
