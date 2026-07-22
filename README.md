# ansr-sinistralidade

Dataset aberto e não-oficial de sinistralidade rodoviária em Portugal,
construído a partir dos relatórios públicos da ANSR (Autoridade Nacional
de Segurança Rodoviária). A ANSR não disponibiliza os seus dados em
formato aberto/API — apenas como PDFs e Excel avulsos numa página HTML —
por isso este projeto automatiza a recolha e normaliza o resultado em
CSV, para ser usado em análises, dashboards ou outras aplicações.

Não afiliado com a ANSR. Todos os pedidos feitos aos servidores da ANSR
usam um `User-Agent` identificável e um atraso entre pedidos.

## Estrutura

```
src/
  scraper.py       # gera o manifesto de todos os documentos publicados
  downloader.py    # descarrega os ficheiros do manifesto (resumível)
  parser_xlsx.py   # normaliza os anexos .xlsx (2020-2025) em CSV
  parser_continente_24h_pdf.py  # extrai a série Continente/24h de 2020-2022 dos PDFs (a ANSR só tem esses anos em Excel a partir de 2023)
  parser_pdf.py    # extrai tabelas dos relatórios nacionais em PDF (1999-2019)
  build_serie_anual_nacional.py  # extrai a série anual nacional 1975-2019 do dump do parser_pdf.py
  parser_pontos_negros.py  # extrai a lista de pontos negros (2019-2022) em PDF
  geocode_pontos_negros.py  # estima lat/lon por estrada+km, cruzando com os marcos quilométricos da IP (SIGIP)
  parser_distrito.py  # extrai sinistralidade por concelho dos relatórios por distrito
  parser_listagem.py  # extrai a listagem de acidentes individuais (mortos/feridos graves) dos mesmos relatórios
  build_concelhos_map.py  # gera o mapa coroplético (simplifica o GeoJSON, cruza com o CSV)
  build_listagem_dashboard_data.py  # pré-agrega a listagem de acidentes individuais para o dashboard
  build_serie_nacional_dashboard_data.py  # combina a série anual e mensal nacional para o dashboard
dashboard/
  pontos_negros.html      # dashboard filtrável dos pontos negros
  concelhos_map.html      # mapa coroplético por concelho
  listagem.html           # dashboard da listagem de acidentes individuais
  serie_nacional.html     # dashboard de tendências nacionais (anual + mensal)
data/
  raw/             # ficheiros descarregados (não versionado, ~290 MB)
  processed/       # CSVs gerados (versionado)
```

## Como correr

```powershell
.\.venv\Scripts\python.exe src\scraper.py       # -> data/processed/manifest.csv
.\.venv\Scripts\python.exe src\downloader.py    # -> data/raw/<ano>/...
.\.venv\Scripts\python.exe src\parser_xlsx.py   # -> data/processed/*.csv (2020-2025)
.\.venv\Scripts\python.exe src\parser_continente_24h_pdf.py  # -> acrescenta 2020-2022 a sinistralidade_mensal_continente_24h.csv (requer os 3 PDFs "24h" em data/raw/<ano>/, correr depois de parser_xlsx.py)
.\.venv\Scripts\python.exe src\parser_pdf.py    # -> data/processed/pdf_raw/*, pdf_tables_index.csv (1999-2019)
.\.venv\Scripts\python.exe src\build_serie_anual_nacional.py  # -> data/processed/serie_anual_nacional.csv (requer pdf_tables_index.csv)
.\.venv\Scripts\python.exe src\parser_pontos_negros.py  # -> data/processed/pontos_negros.csv (requer PDFs em data/raw/pontos_negros/PN_<ano>.pdf)
.\.venv\Scripts\python.exe src\geocode_pontos_negros.py  # -> acrescenta lat/lon/geocoding_precisao_km a pontos_negros.csv (consulta o SIGIP da IP, precisa de rede; correr depois de parser_pontos_negros.py)
.\.venv\Scripts\python.exe src\parser_distrito.py  # -> data/processed/sinistralidade_por_concelho.csv (2011-2018, cobertura parcial)
.\.venv\Scripts\python.exe src\parser_listagem.py  # -> data/processed/listagem_acidentes.csv (2004-2018 exceto 2010)
.\.venv\Scripts\python.exe src\build_concelhos_map.py  # -> data/processed/concelhos_map.json (requer data/ContinenteConcelhos.geojson, ver secção do mapa)
.\.venv\Scripts\python.exe src\build_listagem_dashboard_data.py  # -> data/processed/listagem_dashboard_data.json (dados agregados para dashboard/listagem.html)
.\.venv\Scripts\python.exe src\build_serie_nacional_dashboard_data.py  # -> data/processed/serie_nacional_dashboard_data.json (dados para dashboard/serie_nacional.html)
```

## O que existe na fonte (ANSR)

A página `Estatísticas > Relatórios de Sinistralidade` lista **490
documentos** (PDF e Excel) entre 1999 e 2025:

- **1999–2019**: relatórios anuais nacionais + relatórios anuais por
  distrito, só em PDF. Onde existem duas metodologias ("24 horas" e "30
  dias"), o `parser_pdf.py` usa sempre a variante "30 dias", pela mesma
  razão de consistência descrita abaixo para 2020+. Os relatórios por
  distrito não são processados (só o relatório nacional de cada ano).
- **2020–2024**: relatório anual em PDF + um anexo `.xlsx` com ~60
  tabelas de dados por ano (quadros 1.1 a 6.17).
- **2025**: passou a ter cadência mensal, com um layout de Excel mais
  simples (quadros combinados numa sheet só, ex. `'4 e 5'`). Já normalizado
  na série mensal (ver abaixo); só há uma edição, de setembro, até à data,
  por isso a deteção deste layout ainda não foi testada contra mais do
  que um exemplo.

Nota de qualidade dos dados da própria fonte: os nomes dos ficheiros têm
inconsistências duplicadas (`Cópia de Cópia de Anexo...2024.xlsx`), e a
partir de pelo menos 2010 a ANSR publica **dois relatórios/anexos por
ano com metodologias de contagem de vítimas mortais diferentes** — "24
horas" (norma internacional) vs "30 dias" (norma tradicional
portuguesa). `parser_pdf.py` usa sempre a variante "30 dias" (a mesma
razão vale para os anos 1999-2019). Para os anexos `.xlsx` 2020+,
`parser_xlsx.py` extrai **as duas**, mas em ficheiros separados, porque
descobrimos que a diferença não é só de metodologia — a variante "24h"
reporta **"Sinistralidade no Continente"** (exclui Açores/Madeira),
enquanto a "30 dias" reporta **"Sinistralidade em Portugal"** (país
inteiro). Ou seja, são duas séries com âmbito geográfico diferente, não
só janela de contagem diferente — não devem ser comparadas diretamente
sem ter isto em conta.

## Série anual nacional (1975-2019)

As ~4289 tabelas em `pdf_raw/` (ver "Outputs gerados") não estão
normalizadas, mas quase todos os 21 relatórios nacionais anuais
incluem, perto do início, uma tabela com a série histórica de
totais nacionais — não um retrato do próprio ano, mas uma janela
retrospetiva de 10 a 25 anos que cresce uma linha a cada edição. Como
essa janela se sobrepõe de edição para edição, quatro relatórios já
cobrem 1975-2019 entre si, com sobreposição para conferência cruzada,
sem ser preciso reconciliar o layout ligeiramente diferente de cada
uma das 21 edições:

- Relatório 1999: 1975-1999
- Relatório 2009: 1990-2009
- Relatório 2014: 2005-2014 (cobre 2010-2012, cujos próprios relatórios
  usam um layout de tabela incompatível — o mesmo problema que já
  levou `parser_distrito.py` a excluir esses anos ao nível de
  concelho)
- Relatório 2019: 2010-2019

`build_serie_anual_nacional.py` percorre as tabelas de todas as 21
edições à procura desta tabela recorrente (por palavras-chave no
cabeçalho, robustas à variação de fraseologia ao longo dos anos:
"Acidentes com mortos e/ou f. graves" nos anos 2000, abreviado para
"AcVM ou AcFG" em 2019), e para cada ano usa a edição **mais recente**
que o cobre. O layout de colunas é estável nas 21 edições apesar da
fraseologia do cabeçalho mudar: ano, seguido de 7 pares (valor, %
variação face ao ano anterior), terminando no índice de gravidade sem
% (16 colunas).

Uma complicação da extração: o `pdfplumber` às vezes deteta esta
tabela como uma linha por ano (célula do ano = "2010"), mas outras
vezes como a tabela inteira em 2-3 linhas em que cada célula é uma
string só, com todos os anos separados por quebras de linha (sem
linhas separadoras visíveis no PDF de origem para o `pdfplumber`
distinguir as linhas) — ambos os formatos são tratados, o segundo
detetado e reconstruído dividindo cada coluna por `\n` e recompondo
linha a linha.

**Cobertura: 1975-2019, sem lacunas.** Os números batem com o que é
publicamente sabido sobre a sinistralidade rodoviária portuguesa (pico
de vítimas mortais no início dos anos 90, declínio acentuado desde
então). 1975-1986 não têm a distinção "acidentes com mortos e/ou
feridos graves" nem "feridos graves" vs. "feridos leves" — a própria
ANSR não reportava essa distinção tão atrás no tempo, por isso ficam
vazios (não é uma falha da extração).

## Dashboard de tendências nacionais (dashboard/serie_nacional.html)

Combina `serie_anual_nacional.csv` (1975-2019) e `sinistralidade_mensal.csv`
(2020-2025) num só dashboard: vítimas mortais por ano, índice de
gravidade por ano, sazonalidade (média de acidentes por mês do ano,
2020-2024), e a série mensal contínua 2020-2025 — que deixa visível a
quebra de abril de 2020 (925 acidentes com vítimas nesse mês, menos de
metade da média sazonal de ~2364 para abril, coincidindo com o
confinamento geral). A série `sinistralidade_mensal_continente_24h.csv`
(2020-2024, âmbito e metodologia diferentes — ver secção "O que existe
na fonte") é mostrada à parte, como tabela, para não ser lida como
comparável às duas séries principais.

`build_serie_nacional_dashboard_data.py` combina as duas fontes num só
JSON (~15 KB) — pequeno o suficiente para não precisar de agregação
como o dashboard da listagem de acidentes individuais, mas mantido como
passo de pipeline scriptado (e não embutido à mão) pela mesma razão de
reprodutibilidade dos outros dashboards.

## Pontos Negros (troços perigosos)

A ANSR publica também, numa secção separada do site (`Segurança
Rodoviária > Pontos Negros Recomendações`, não em `Estatísticas`), PDFs
anuais com inspeções a "pontos negros" (troços rodoviários perigosos) e
as recomendações de segurança feitas às entidades gestoras das vias.

**Geolocalização**: a fonte identifica estes pontos por **estrada +
quilómetro** (ex.: "A28, Km 3,500 ao Km 3,600"), não por coordenadas
GPS. `geocode_pontos_negros.py` cruza isso com a camada pública de
**Marcos Quilométricos** da Infraestruturas de Portugal (SIGIP —
[sigip.infraestruturasdeportugal.pt](https://sigip.infraestruturasdeportugal.pt/pub/rest/services/MOBILE_DRR/EQUIVIA/MapServer/0),
~16 mil pontos a nível nacional, EPSG:3763): para o km médio de cada
registo, interpola linearmente entre os dois marcos mais próximos na
mesma via (números sem espaço, ex. `EN106`). A distância entre esses
dois marcos fica como `geocoding_precisao_km` — as coordenadas só são
escritas quando essa distância é ≤ 5 km, para não apresentar como
preciso um ponto interpolado ao longo de dezenas de km de uma via
sinuosa. Resultado: **54 dos 81 registos geocodificados**. Os 27 que
ficam de fora dividem-se em dois casos, ambos deixados em aberto de
propósito (ver limitações): vias não cobertas pelo SIGIP (autoestradas
concessionadas como a A2/A3/A5, e ainda a EN125/EN378/IC20, por razão
não indicada pela fonte), e troços onde os marcos mais próximos ficam
a mais de 5 km um do outro (A1, EN10, EN106, EN206) — nesses, uma
interpolação reta entre dois pontos tão distantes ao longo de uma via
com curvas dava uma posição pouco fiável.

Extração: `pdfplumber` não deteta as tabelas destes PDFs de forma
fiável — a estratégia de deteção por linhas perde silenciosamente
células de Entidade/Estrada/Km em algumas linhas, e a estratégia por
texto fragmenta as colunas de texto livre de forma instável. O
`parser_pontos_negros.py` usa antes as posições (x, y) de cada palavra
para reconstruir apenas os campos estruturados fiáveis (Entidade,
Estrada, Km, Data do relatório, Estado de intervenção), **descartando
deliberadamente** o texto livre de "Problemas identificados" e
"Recomendações" — juntar esse texto ao registo certo revelou-se
demasiado arriscado (risco de atribuir o problema de uma estrada a
outra). Resultado: 81 registos (2019-2022). Uma entrada com um texto de
estado invulgarmente longo (justificação em vez do habitual
"Implementadas"/"Não Implementadas") chegou a ficar partida em dois
pela heurística de quebra de página — corrigido detetando que a
continuação não trazia nenhum campo de identidade (Entidade/Estrada)
nas duas primeiras linhas da página nova, sinal de que era o mesmo
registo a continuar, não um novo (ver `parser_pontos_negros.py`).

## Sinistralidade por concelho (relatórios de distrito)

Cada distrito tem um relatório PDF anual próprio (ex. `Aveiro 2015.pdf`)
com uma tabela "Acidentes e vítimas segundo o concelho" — dados ao nível
do **concelho (município)**, ao contrário de tudo o resto neste projeto
(que é nacional ou, no máximo, por distrito). Isto é o que permite, em
princípio, um mapa coroplético real: nomes de concelho fazem match
direto com os limites administrativos oficiais.

**Cobertura real: 2004–2009 e 2011–2018, todos com 17-18 de 18
distritos** (2014 é o mais incompleto, com 15/18 — faltam Castelo
Branco, Viana do Castelo e Vila Real). Só falta **2010**, que usa um
layout de tabela diferente ("Vítimas segundo o concelho", sem o
prefixo "Acidentes e", com colunas 24h/30 dias lado a lado, sem secção
"UTENTES") não suportado por este parser. A cobertura de 2004-2009 foi
uma surpresa: inicialmente pensava-se (por analogia com 2010) que todo
o intervalo 2004-2010 usava esse layout antigo, mas afinal só 2010 o
usa — 2004-2009 já seguem o mesmo layout de 2013+.

Chegar a esta cobertura exigiu três correções sucessivas:

- **2011–2012**: o cabeçalho de coluna repetido ("Acidentes Vítimas
  Feridos Feridos Total Índice de" / "c/ vítimas mortais graves leves
  vítimas gravidade") só aparece **uma vez** no documento nesses dois
  anos, em vez de uma vez por tabela — sem essa repetição não há como
  distinguir a tabela de concelho das ~9 outras tabelas com o mesmo
  cabeçalho (por mês, por dia da semana, por hora do dia, ...) só pela
  posição. Resolvido com uma estratégia alternativa que ancora no
  título real da secção ("... segundo o concelho", distinguindo-o da
  entrada correspondente no índice, que tem pontos de preenchimento) e
  termina na secção seguinte, que em todos os anos verificados é
  sempre "Listagem dos acidentes com mortos e/ou feridos graves" —
  válido mesmo em anos que também têm uma secção "UTENTES" para outro
  efeito. A estratégia original (baseada em "UTENTES") não falha
  claramente nestes dois anos — encontra *um* bloco sem erro (o
  cabeçalho calha a aparecer uma vez, só que no sítio errado) — por
  isso a fila de tentativas só avança para a alternativa depois de
  reparar (via a validação de sanidade) que as linhas extraídas do
  primeiro bloco não são concelhos a sério.
- **2004–2009**: nomes de concelho com hífen ou compostos por duas
  palavras (ex. "Albergaria-a-Velha") aparecem no PDF partidos em duas
  linhas físicas, com os números da linha espremidos no meio (`
  Albergaria-a-` / 11 números / `Velha`) — a célula do nome é mais alta
  que uma linha de texto, mas os números ficam centrados verticalmente.
  Isto fazia com que ~30% das linhas desaparecessem silenciosamente
  (nem o fragmento de nome nem a linha de números batem com a regex
  sozinhos). Há ainda uma segunda variante do mesmo problema, mais
  traiçoeira: para nomes de 3+ palavras (ex. "Arruda dos Vinhos",
  "Vila Franca de Xira"), o ÚLTIMO fragmento do nome cai na MESMA linha
  que os números, e essa linha já bate certo sozinha com a regex — só
  que com um nome errado e truncado ("Vinhos", "Xira"), sem nenhum
  sinal de erro. `merge_wrapped_names` acumula todos os fragmentos de
  texto (sem dígitos) vistos antes de uma linha de dados, filtrando
  texto de cabeçalho pelo caminho, e só os liberta quando uma linha de
  dados real aparece — isto recuperou mais 71 concelhos corretamente
  nomeados no total (soma de todos os anos), sem regressões nos anos
  já bem cobertos (ver taxas por ano na secção do mapa, abaixo).
- Vários anos têm **dois ficheiros PDF não-"24h" para o mesmo
  distrito** (ex. `Aveiro 2015.pdf` e `Aveiro 2015 30d.pdf`) — sem
  deduplicação isto duplicava todas as linhas; o parser mantém só um
  ficheiro por (distrito, ano), preferindo o que tem "30" no nome.

## Listagem de acidentes individuais

Os mesmos relatórios PDF por distrito usados acima têm, como última
secção, uma tabela ao nível do **acidente individual**: "Listagem dos
acidentes com mortos e/ou feridos graves" — um registo por acidente,
com concelho, data/hora, nº de mortos, nº de feridos graves, via, km e
natureza (tipo de acidente, ex. "Despiste simples", "Colisão frontal").
`parser_listagem.py` extrai isto para
`data/processed/listagem_acidentes.csv`: **32488 registos, 2004-2018
exceto 2010**.

Ao contrário de `parser_distrito.py` (que trabalha sobre texto já
extraído), este parser trabalha sobre as coordenadas (x, y) de cada
palavra, porque duas coisas tornam a extração por texto pouco fiável
aqui:

- **Ordem das colunas e formato de data variam por ano**: 2011+ usa
  ordem "Via Km" com datas `DD-MM-YYYY`; 2004-2010 usa ordem "Km Via"
  com datas `YYYY:MM:DD`; 2008-2009 usa ainda um terceiro formato,
  `YYYY-MM-DD`. Em vez de assumir um layout fixo, tanto a ordem das
  colunas como o formato de data são detetados por página, a partir do
  próprio cabeçalho dessa página.
- **Campos de texto livre longos embrulham-se em várias linhas
  físicas** (nome da via, ou descrição da natureza do acidente), mas o
  renderizador do PDF mantém as outras células da mesma linha
  (concelho, data, mortos, feridos graves) centradas verticalmente
  contra a célula alta que embrulhou — por isso a linha com
  concelho/data/mortos/feridos graves pode aparecer entre dois
  fragmentos de texto embrulhado, não necessariamente como a primeira
  linha do grupo. O parser agrupa palavras em linhas físicas por
  posição vertical, identifica quais são início de registo (têm uma
  data) e atribui cada linha de continuação ao registo mais próximo —
  um parser ingénuo por linha de texto simples leria isto como lixo
  sem sentido.

Limitações conhecidas:

- **2010 excluído por completo**, pela mesma razão que
  `parser_distrito.py` já exclui este ano da tabela de concelho: aqui
  a inconsistência é ainda mais direta — mesmo dentro do mesmo
  ficheiro, algumas páginas usam o formato de data antigo (dois
  pontos) com uma **terceira coluna numérica** que nenhum cabeçalho
  documenta, enquanto outras páginas do mesmo ficheiro já usam o
  formato novo (traço) com as duas colunas habituais. Sem uma forma de
  linha única para tentar parsear, tratado como incompatível em vez de
  forçado.
- `2018/Lisboa 2018 30d.pdf` não tem esta secção — o próprio PDF fonte
  tem um erro de geração ("Out of object memory") exatamente onde a
  tabela deveria estar; falha da fonte, não do parser. Existe um
  `Lisboa 2018 24h.pdf` com a secção completa, mas deliberadamente não
  usado como reserva, para não misturar as duas metodologias de
  contagem (24h vs 30 dias) dentro do mesmo ficheiro de saída.
- `km` vazio em ~56% das linhas — esperado: só é preenchido quando o
  acidente ocorre numa via com marco quilométrico (estradas nacionais/
  municipais fora de povoações); acidentes em arruamentos urbanos não
  têm km.
- `natureza` vazio em ~1,9% das linhas — a maioria vem de um
  artefacto de renderização específico de alguns relatórios de
  2004/2011/2012, onde o texto aparece com cada letra como uma palavra
  separada ("D e s p i s t e" em vez de "Despiste"), o que impede o
  reconhecimento por palavra-chave usado para separar via/km/natureza.
  Não perseguido mais além: corrigir exigiria fundir sequências de
  tokens de letra única antes do resto do parsing, um risco
  desproporcional para menos de 2% das linhas.
- Dois registos têm contagens extremas de mortos/feridos graves
  (Castelo Branco 2007: 13 mortos; Castelo Branco 2013: 11 mortos/12
  feridos graves, ambos em autoestradas/itinerários complementares).
  Em ambos os casos a extração é de um único token limpo, sem
  ambiguidade posicional — não há forma de confirmar contra a fonte
  original se refletem acidentes multi-vítimas genuinamente graves ou
  um erro de publicação da própria ANSR, por isso ficam como estão.
- Um fragmento de linha embrulhada que caia na página **seguinte**
  (quebra de página a meio de um texto longo) não é ligado de volta ao
  seu registo — caso raro, aceite como limitação.

## Dashboard de acidentes individuais (dashboard/listagem.html)

Usa `listagem_acidentes.csv` para explorar os 32488 registos por
padrões que os datasets agregados por concelho/ano não mostram:
evolução anual de mortos vs. feridos graves, distribuição por hora do
dia e dia da semana, tipo de acidente e vítimas por distrito, mais uma
tabela com os 20 acidentes mais graves.

O dashboard **não embute os 32488 registos em bruto** — `src/build_
listagem_dashboard_data.py` pré-agrega tudo em Python (por ano, hora,
dia da semana, tipo de acidente, distrito, mais o top 20) para
`data/processed/listagem_dashboard_data.json`, ~7,7 KB, embutido no
HTML. O sinal interessante aqui está nos padrões agregados, não em
percorrer registo a registo — a mesma lógica já aplicada ao mapa
coroplético (que embute agregados por concelho/ano, não o texto bruto
dos PDFs).

O campo `natureza` do CSV é texto livre da ANSR com muitas variantes de
abreviatura por ano (ex. "Colisão frontal", "Col. frontal", "Colisão
lateral com outro veículo em movimento"); o script categoriza-o num
pequeno conjunto de tipos (Despiste, Atropelamento, Colisão frontal/
lateral/traseira/outra, Capotamento, Não especificado) por
correspondência de palavra-chave — uma categorização feita para este
dashboard, não um campo da fonte.

## Mapa coroplético (dashboard/concelhos_map.html)

Usa `sinistralidade_por_concelho.csv` para desenhar um mapa coroplético
real de Portugal continental, com seletor de ano e de indicador
(acidentes, vítimas mortais, feridos graves/leves, índice de
gravidade), tooltip por concelho, top 10, e tabela completa.

Como o dashboard é publicado como Artifact (sem acesso à rede em tempo
de execução — nada de tile servers como Leaflet/OpenStreetMap usariam),
o mapa não pode ser um mapa de "tiles": é construído a partir das
fronteiras administrativas oficiais (CAOP, via
[nmota/caop_GeoJSON](https://github.com/nmota/caop_GeoJSON),
`ContinenteConcelhos.geojson`, 278 concelhos), convertidas para paths
SVG estáticos por `build_concelhos_map.py`:

- As coordenadas do GeoJSON fonte **não são lon/lat** — apesar de ser
  GeoJSON válido, estão numa projeção nacional portuguesa em metros
  (valores como `-20560.75, 113803.91`). Simplificar com uma tolerância
  pensada em graus (o erro inicial) não fazia nada; corrigido para
  metros (~400m de tolerância) uma vez percebida a unidade real.
- Simplificação por Douglas-Peucker (implementação própria, sem
  shapely/pyproj) reduziu o ficheiro de 36,5 MB (geometria ao detalhe
  de precisão cadastral) para ~415 KB — adequado para embutir num
  Artifact.
- Nomes de concelho do CSV (extraídos de PDF, por vezes sem "de"/"da"
  ou com sufixos como "Lagoa (Algarve)") precisaram de um pequeno
  dicionário de aliases para bater certo com os nomes oficiais do CAOP.
  Isto cobre bem 2013 e 2015-2018 (277-278 de 278 concelhos casados
  por ano). Para os restantes, depois de generalizar
  `merge_wrapped_names` para nomes de 3+ palavras (ver secção acima),
  a taxa por ano é: 2004: 267/278, 2005: 232/278, 2006: 253/278,
  2007: 248/278, 2008: 249/278, 2009: 247/278, 2011: 242/278,
  2012: 251/278, 2014: 242/278. O que ainda falta nestes anos são,
  sobretudo, abreviaturas genuínas no próprio texto do PDF (ex.
  "V. N. Famalicão", "Miranda Douro" sem "de") que não têm forma de
  ser reconstruídas a partir do texto disponível — precisariam de um
  dicionário de aliases caso a caso, não perseguido mais além deste
  ponto por retorno decrescente. Os concelhos sem match não aparecem
  no mapa para esse ano (ficam sem cor, não errados) mas continuam
  presentes em `sinistralidade_por_concelho.csv` com o nome tal como
  extraído.
- O ficheiro `ContinenteConcelhos.geojson` de origem (36,5 MB) não é
  versionado — só o `concelhos_map.json` já simplificado e embutido no
  HTML.

## Outputs gerados

- `data/processed/manifest.csv` — catálogo de todos os 490 documentos
  (ano, título, url, nome de ficheiro, extensão).
- `data/processed/xlsx_tables_index.csv` — índice de todas as ~380
  tabelas extraídas dos anexos Excel (ano, id do quadro, título, caminho
  do CSV correspondente).
- `data/processed/xlsx_raw/<ano>/<quadro>.csv` — dump bruto de cada
  tabela, célula a célula, tal como está no Excel original.
- `data/processed/sinistralidade_mensal.csv` — série mensal, âmbito
  **Portugal** (país inteiro), metodologia "30 dias": 2020–2025 (69
  linhas: 60 de 2020-2024 + 9 de 2025 até setembro). Colunas:
  `report_year, scope, month, month_num, acidentes_com_vitimas,
  vitimas_mortais, feridos_graves, feridos_leves`.
- `data/processed/sinistralidade_mensal_continente_24h.csv` — a mesma
  estrutura, mas âmbito **Continente** (exclui Açores/Madeira),
  metodologia "24h": 2020–2024 (60 linhas). A ANSR só publicou o anexo
  "24h" em Excel (com uma tabela mensal equivalente à do anexo "30
  dias") a partir de 2023; 2020-2022 vêm de `parser_continente_24h_pdf.py`,
  que extrai a mesma tabela ("Sinistralidade no Continente por mês") do
  relatório "24h" anual em PDF desses anos (ver secção "Dashboard de
  tendências nacionais").
- `data/processed/pdf_tables_index.csv` — índice de **4289 tabelas**
  extraídas dos 21 relatórios nacionais de 1999–2019 (ano, ficheiro de
  origem, página, índice da tabela na página, nº de linhas/colunas,
  **`provavel_ruido`** (`True` se a tabela tem 1 linha ou 1 coluna — sinal
  de vir de um gráfico/legenda ou de um bloco de texto que o `pdfplumber`
  confundiu com uma tabela, não um critério para descartar; 1684 das 4289,
  ~39%), caminho do CSV, preview da primeira linha).
- `data/processed/pdf_raw/<ano>/p<página>_t<tabela>.csv` — dump bruto de
  cada tabela detetada pelo `pdfplumber`, célula a célula, tal como
  extraída do PDF (sem tentar interpretar o layout).
- `data/processed/serie_anual_nacional.csv` — série histórica nacional,
  1975-2019, sem lacunas (ver secção acima): `ano,
  acidentes_com_vitimas, acidentes_com_mortos_ou_feridos_graves,
  acidentes_com_mortos, vitimas_mortais, feridos_graves, feridos_leves,
  total_feridos, indice_gravidade, source_report_year`.
- `data/processed/pontos_negros.csv` — 81 registos de pontos negros (2019-2022):
  `year, entidade_gestora, estrada, km, relatorio_data,
  estado_intervencao, lat, lon, geocoding_precisao_km` — os últimos três
  ficam vazios nos 27 registos não geocodificados (ver secção "Pontos
  Negros" acima).
- `data/processed/sinistralidade_por_concelho.csv` — 3819 registos
  (distrito × ano × concelho), cobertura 2004-2009 e 2011-2018 (ver
  secção acima; só falta 2010): `distrito, ano, concelho,
  acidentes_com_vitimas, vitimas_mortais, feridos_graves, feridos_leves,
  total_vitimas, indice_gravidade, source_file`.
- `data/processed/concelhos_map.json` — 278 concelhos com path SVG
  simplificado + os dados de `sinistralidade_por_concelho.csv` por ano,
  já cruzados por nome (ver secção do mapa acima); é o que está embutido
  em `dashboard/concelhos_map.html`.
- `data/processed/listagem_acidentes.csv` — 32488 registos individuais
  de acidentes com mortos/feridos graves, cobertura 2004-2018 exceto
  2010 (ver secção acima): `distrito, ano, concelho, data, hora,
  mortos, feridos_graves, via, km, natureza, source_file`.
- `data/processed/listagem_dashboard_data.json` — agregados de
  `listagem_acidentes.csv` (por ano, hora, dia da semana, tipo de
  acidente categorizado, distrito, top 20 mais graves), ~7,7 KB; é o
  que está embutido em `dashboard/listagem.html` (ver secção acima).
- `data/processed/serie_nacional_dashboard_data.json` — combina
  `serie_anual_nacional.csv` e `sinistralidade_mensal.csv` (mais a
  sazonalidade mensal derivada e a série Continente/24h), ~15 KB; é o
  que está embutido em `dashboard/serie_nacional.html` (ver secção
  acima).

## Limitações conhecidas / próximos passos

- As ~4289 tabelas de `pdf_raw/` **não estão normalizadas** — o layout
  varia significativamente ao longo de 21 anos de relatórios (agências e
  metodologias diferentes), pelo que forçar um esquema único seria
  pouco fiável. Ficam como dump bruto pesquisável. Uma primeira série
  "tidy" já foi extraída deste dump — a série anual nacional 1975-2019
  (ver `build_serie_anual_nacional.py` e secção própria abaixo) — mas é
  só uma tabela entre milhares; extrair outras séries recorrentes do
  mesmo dump continua a ser um próximo passo natural, caso a caso.
- ~~pdfplumber também deteta ruído... o índice inclui tudo, sem filtrar
  por relevância~~ — resolvido: `pdf_tables_index.csv` tem agora a coluna
  `provavel_ruido` (tabela de 1 linha ou 1 coluna, tipicamente um
  gráfico/legenda ou um bloco de texto mal-detetado como tabela — 1684
  das 4289, ~39%). Continua tudo no dump, só marcado — quem quiser
  pesquisar só as tabelas "reais" filtra por `provavel_ruido == False`.
- O formato mensal de 2025 (`sheet '4 e 5'`) já está incluído na série
  mensal, mas a deteção deste layout ("Quadros" combinados numa sheet,
  ex. `'4 e 5'`) só foi validada contra um único ficheiro (setembro
  2025) — vale a pena confirmar quando sair a próxima edição mensal.
- ~~A série Continente/24h só tem 2023–2024~~ — resolvido: agora cobre
  2020-2024. Para 2020-2022 a ANSR só publicou o anexo "24h" em PDF, não
  em Excel (confirmado no manifesto); `parser_continente_24h_pdf.py`
  extrai a mesma tabela mensal diretamente do PDF por posição de
  palavra (a deteção de tabela do pdfplumber perde metade das linhas
  neste layout). As duas sobreposições entre relatórios consecutivos
  (2020 no relatório de 2020 vs. no de 2021; 2021 no de 2021 vs. no de
  2022) batem certo, número a número.
- `xlsx_raw/` e `pdf_raw/` guardam cada tabela tal como está na fonte
  (com cabeçalhos de várias linhas, células vazias, linhas de totais);
  útil para não perder informação, mas a maioria das tabelas ainda não
  tem uma versão "tidy" própria como a série mensal nacional.
- ~~`pontos_negros.csv` não tem geolocalização~~ — resolvido para 54 dos
  81 registos (ver secção "Pontos Negros" acima e `geocode_pontos_negros.py`);
  os restantes 27 ficam sem lat/lon de propósito (via não coberta pelo
  SIGIP da IP, ou marcos km longe demais para uma interpolação fiável).
  `pontos_negros.csv` não inclui o texto de "Problemas
  identificados"/"Recomendações" (descartado deliberadamente por risco de
  atribuição incorreta). Só cobre 2019-2022
  — reconfirmado em 2026-07-22 (re-scrape da página fonte): continua a só
  existir PDF "PN" detalhado (por troço) para esses 4 anos. Existe, porém,
  um novo ficheiro `.xlsx` de resumo ("PN JUN. 2026.xlsx", ainda não
  integrado neste projeto) com contagens agregadas por ano — inclui já
  2023 (40 pontos negros identificados), mas só ao nível de totais anuais
  (Nº PN, Nº ISSR, recomendações emitidas/implementadas), não ao nível de
  troço/estrada como o CSV atual — granularidade diferente, exigiria um
  parser próprio.
