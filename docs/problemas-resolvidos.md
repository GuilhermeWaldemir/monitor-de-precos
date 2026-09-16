# Problemas resolvidos

Formato: **Problema → Processo → Solução → Resultado**.

---

## 1. Mercado Livre mostra "tráfego suspeito" em vez da página do produto
*2026-09-14*

- **Problema:** ao baixar a página do produto (`/p/MLB18623867`), o Mercado Livre devolveu HTTP 200, mas o conteúdo era uma tela de verificação (`account-verification`, `suspicious`), sem nenhum bloco JSON-LD.
- **Processo:** o `robots.txt` do Mercado Livre permite páginas `/p/MLB...` para robôs em geral. Testei a API oficial: `/products/{id}` respondeu **401** (exige login) e `/products/{id}/items` respondeu **403** (bloqueado por política). A pesquisa mostrou vários desenvolvedores com o mesmo 403 desde 2025.
- **Solução:** não tentar burlar (nada de fingir ser navegador, proxy ou captcha). O site mostra o motivo da falha e permite **informar o preço manualmente**. Esse preço fica marcado como "informado por você" no histórico.
- **Resultado:** o card continua comparando as três lojas. A página de bloqueio foi salva em `tests/fixtures/mercadolivre_bot_check.html` e há um teste garantindo que ela vira um erro claro, e não um preço errado.

## 2. Terabyte recusou o primeiro teste (403), mas funcionou com `requests`
*2026-09-14*

- **Problema:** o primeiro teste, feito com `urllib` (biblioteca padrão do Python), recebeu **HTTP 403** da Terabyte, até no `robots.txt`.
- **Processo:** o programa final usa `requests` com os mesmos cabeçalhos honestos (User-Agent identificando o projeto, `Accept`, `Accept-Language`). Com ele a página veio normalmente. A proteção da loja (Cloudflare) provavelmente trata as duas bibliotecas de forma diferente.
- **Solução:** usar `requests`. Continua valendo a regra: se voltar a bloquear, o erro aparece no card e o preço pode ser informado manualmente.
- **Resultado:** a Terabyte é lida automaticamente. Página salva em `tests/fixtures/terabyte_kf432c16bb1-16.html`.

## 3. KaBuM! não respondia a tempo
*2026-09-14*

- **Problema:** a primeira requisição à KaBuM! estourou o tempo limite (*timeout*).
- **Processo:** repeti a requisição mandando os cabeçalhos que qualquer cliente HTTP comum manda (`Accept` e `Accept-Language`), mantendo o User-Agent do projeto.
- **Solução:** esses cabeçalhos ficaram fixos em `monitor/fetcher.py`, e toda requisição tem timeout de 5 s para conectar e 20 s para ler.
- **Resultado:** a página respondeu com HTTP 200 e JSON-LD completo (nome, foto, preço, estoque).

## 4. Preço lido como `float` do JSON
*2026-09-14*

- **Problema:** no JSON-LD da KaBuM! o preço é um número (`"price": 929.99`). O `json.loads` padrão transforma isso em `float`, que não representa centavos com exatidão.
- **Processo:** o `json.loads` aceita `parse_float`, uma função chamada para cada número decimal do texto.
- **Solução:** `json.loads(texto, parse_float=Decimal)`. O número vai direto do texto para `Decimal`, sem passar por `float`. No banco, o preço é guardado em **centavos inteiros** (`92999`), porque o SQLite não tem tipo decimal.
- **Resultado:** teste `test_price_is_never_float` garante isso.

## 5. "Mesma memória RAM" com códigos quase iguais
*2026-09-14*

- **Problema:** na busca apareceram duas memórias Kingston Fury Beast 16GB 3200MHz com nomes quase idênticos: **KF432C16BB1/16** e **KF432C16BB/16**. São produtos diferentes. Comparar pelo nome daria resultado errado.
- **Processo:** cada loja escreve o nome de um jeito. A KaBuM! põe o código no nome. A Terabyte não põe no nome, mas publica no campo `mpn` (*Manufacturer Part Number*) do JSON-LD.
- **Solução:** todo produto é cadastrado com o **código do fabricante**. A conferência (`monitor/matching.py`) usa o `mpn` quando existe; senão procura o código como **palavra inteira** no nome. Se a página não mostra código nenhum, o site avisa "código não confirmado". Se o código é diferente, a oferta **nunca** vira "melhor preço".
- **Resultado:** testes cobrem o caso `BB1/16` × `BB/16`, maiúsculas/minúsculas, separadores e o `mpn` da Terabyte.

## 6. Magazine Luiza bloqueia qualquer acesso automático
*2026-09-14*

- **Problema:** a página da mesma memória na Magazine Luiza respondeu **HTTP 403**, e o `robots.txt` também.
- **Processo:** o bloqueio vem antes de qualquer conteúdo, então não há o que ler. Burlar (fingir ser navegador, usar proxy) vai contra as regras do projeto.
- **Solução:** a Magazine Luiza entra como fonte com **preço manual**. O card mostra o erro e o botão "informar preço".
- **Resultado:** a loja aparece na comparação e o motivo fica visível para o usuário.

## 7. Amazon não publica JSON-LD e muda o layout entre acessos
*2026-09-14*

- **Problema:** a página `/dp/B097K2MRS3` não tem bloco JSON-LD. Pior: a mesma URL veio com **dois layouts diferentes** em acessos seguidos. Em um aparecia o preço principal (R$ 1.855,02, "Em estoque"). No outro, só "Comparar outras 4 ofertas a partir de R$ 1.439,46", ofertas de outros vendedores que podem incluir produto usado.
- **Processo:** o `robots.txt` da Amazon permite `/dp/`. Inspecionei o HTML das duas versões com BeautifulSoup e achei os ids estáveis: `#productTitle`, `#corePrice_feature_div .a-offscreen`, `#availability`, `#landingImage`.
- **Solução:** criei um leitor específico (`monitor/amazon.py`) e um escolhedor por loja (`monitor/readers.py`). Quando só existem "outras ofertas", o leitor **não** usa o preço "a partir de": registra o erro "A Amazon não mostrou uma oferta principal", porque aquele preço não é equivalente.
- **Resultado:** as duas versões reais estão salvas como fixture e têm teste. Na verificação real, as duas situações aconteceram e o site mostrou cada uma corretamente.

## 8. Fixture da Amazon grande demais
*2026-09-14*

- **Problema:** a página da Amazon tem de 1 a 1,4 MB, quase tudo JavaScript e CSS. Guardar isso no Git deixa o repositório pesado.
- **Processo:** o leitor só usa o HTML, então scripts e estilos não fazem diferença para o teste.
- **Solução:** ao salvar a fixture, removi as tags `<script>`, `<style>`, `<noscript>`, `<svg>`, `<link>` e `<iframe>` com BeautifulSoup (`tag.decompose()`).
- **Resultado:** cerca de 330 KB por arquivo, e o teste continua lendo a página real.

## 9. Identificar "o mesmo produto" em perfumes e roupas
*2026-09-14*

- **Problema:** roupas e perfumes não têm um código de fabricante igual em todas as lojas, como a memória RAM tem.
- **Processo:** produtos vendidos no varejo têm **EAN** (os números do código de barras), publicado no JSON-LD como `gtin13`. Um mesmo código de barras pode vir como GTIN-14 com um zero na frente.
- **Solução:** o código virou **opcional** e aceita código do fabricante ou EAN. `code_matches` compara EAN com `gtin` (ignorando zeros à esquerda) e código do fabricante com `mpn`. Só diz "código diferente" quando compara códigos do mesmo tipo. Sem código, a oferta fica "não confirmada".
- **Resultado:** testes cobrem EAN igual, EAN com zero à esquerda, EAN diferente e produto sem código.

## 10. Testes de Configurações quebravam a cada opção nova
*2026-09-14*

- **Problema:** ao criar a opção "brilho nos cards", **11 testes antigos falharam** sem nenhum bug no código. Eles comparavam o resultado inteiro, por exemplo `load_settings(conn) == {"theme": "dark", "font": "default"}`. Com uma chave nova (`card_glow`), o dicionário deixou de ser igual.
- **Processo:** o que cada teste queria verificar era só "o tema mudou e o resto ficou no padrão", não a lista completa de opções. A lista completa só importa num único teste, o dos valores padrão.
- **Solução:** criei o auxiliar `defaults_with(**mudanças)`, que devolve `{**DEFAULTS, **mudanças}`. Os testes passaram a escrever `== defaults_with(theme="dark")`. Só `test_defaults_when_nothing_saved` continua listando tudo, de propósito.
- **Resultado:** os 205 testes passam, e as próximas opções (como a animação de categorias) não vão quebrar os testes antigos. Lição: um teste deve verificar o comportamento que importa, não detalhes que mudam por outros motivos.

## 11. Mudar uma regra `CHECK` de uma tabela que já tem dados
*2026-09-14*

- **Problema:** o favorito "Capturar preço" precisava gravar a origem `'capture'` em `price_checks`, mas a tabela tinha `CHECK (source IN ('auto', 'manual'))`. `CREATE TABLE IF NOT EXISTS` não altera tabelas existentes, e o SQLite **não permite alterar um `CHECK`** com `ALTER TABLE`. Apagar o banco não era mais opção: ele já tinha 21 verificações de preço e produtos cadastrados pelo Guilherme.
- **Processo:** segui a receita oficial do SQLite para mudar a estrutura de uma tabela: criar a tabela nova, copiar as linhas, apagar a antiga e renomear a nova. Tudo precisa acontecer numa transação, com as chaves estrangeiras desligadas durante a troca (senão o `DROP` apagaria o histórico em cascata).
- **Solução:** `db._migrate_allow_capture_source` roda no `init_db`. Se a tabela ainda não aceita `'capture'`, ela é reconstruída com `BEGIN` → `CREATE price_checks_new` → `INSERT ... SELECT` → `DROP` → `RENAME` → recriar o índice → `COMMIT`; se algo falha, `ROLLBACK`. Por fim, religa `PRAGMA foreign_keys`. Rodar de novo não faz nada. Um teste cria um banco no formato antigo, com histórico, e confere que as linhas, o índice e o `ON DELETE CASCADE` sobrevivem.
- **Detalhe que apareceu:** o servidor em modo `--debug` recarrega a cada arquivo salvo, e por isso a migração rodou no banco real assim que o `db.py` foi salvo, antes dos testes. Deu certo (21 linhas preservadas, sem erro de chave estrangeira), mas a lição fica: **fazer backup do banco antes de escrever uma migração**, não depois.
- **Resultado:** o banco real foi migrado sem perder dados, e existe um backup em `data/monitor-backup-antes-migracao.db`.

## 12. Lojas que bloqueiam robôs: o que fazer sem burlar nada
*2026-09-16*

- **Problema:** a maioria das lojas grandes (Mercado Livre, Magazine Luiza e, testada agora, a **Pichau**) devolve erro para qualquer programa que tente ler a página, mesmo se identificando honestamente. O pedido inicial foi "burlar de alguma maneira".
- **Processo:** burlar significaria fingir ser navegador, girar IPs por proxy ou resolver captcha (por exemplo, com os modos "stealth" do Scrapling). Isso viola os termos de uso, quebra a cada atualização da proteção e, num portfólio feito para vagas em e-commerce, depõe contra o candidato. Então a pergunta virou outra: **como obter o preço de um jeito que a loja aceite?**
- **Curiosidade da Pichau:** o `robots.txt` dela **permite** as páginas de produto (só proíbe `/api/`, `/checkout`, `/customer/` e URLs com `?`), e o próprio `robots.txt` é servido normalmente. Mesmo assim a página de produto responde **403**. Ou seja, a política escrita e a proteção automática não concordam entre si.
- **Solução:** três caminhos legítimos, em ordem de preferência:
  1. **API oficial**, quando existe — implementada para o Mercado Livre com OAuth (Etapa 15 do diário);
  2. **favorito "Capturar preço"**, em que a pessoa abre a página e captura o preço que ela mesma está vendo;
  3. **preço manual**, o caminho simples que sempre funciona.
- **Resultado:** o Mercado Livre saiu do grupo "bloqueado" e passou a ser lido oficialmente. Magazine Luiza e Pichau seguem pela captura, com o motivo documentado no card e aqui. Lojas que publicam os dados (KaBuM!, Terabyte, Amazon, promofarma) continuam automáticas.
