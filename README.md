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
  parser_pdf.py    # extrai tabelas dos relatórios nacionais em PDF (1999-2019)
  parser_pontos_negros.py  # extrai a lista de pontos negros (2019-2022) em PDF
data/
  raw/             # ficheiros descarregados (não versionado, ~290 MB)
  processed/       # CSVs gerados (versionado)
```

## Como correr

```powershell
.\.venv\Scripts\python.exe src\scraper.py       # -> data/processed/manifest.csv
.\.venv\Scripts\python.exe src\downloader.py    # -> data/raw/<ano>/...
.\.venv\Scripts\python.exe src\parser_xlsx.py   # -> data/processed/*.csv (2020-2025)
.\.venv\Scripts\python.exe src\parser_pdf.py    # -> data/processed/pdf_raw/*, pdf_tables_index.csv (1999-2019)
.\.venv\Scripts\python.exe src\parser_pontos_negros.py  # -> data/processed/pontos_negros.csv (requer PDFs em data/raw/pontos_negros/PN_<ano>.pdf)
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

## Pontos Negros (troços perigosos)

A ANSR publica também, numa secção separada do site (`Segurança
Rodoviária > Pontos Negros Recomendações`, não em `Estatísticas`), PDFs
anuais com inspeções a "pontos negros" (troços rodoviários perigosos) e
as recomendações de segurança feitas às entidades gestoras das vias.

**Importante para quem queira um mapa**: estes pontos são identificados
por **estrada + quilómetro** (ex.: "A28, Km 3,500 ao Km 3,600"), não por
coordenadas GPS. Não há geolocalização pronta a usar — construir um mapa
exigiria geocodificar estes pares estrada/km, o que precisaria de uma
fonte adicional (ex.: dados abertos da Infraestruturas de Portugal/IMT
com referenciação geográfica da rede rodoviária), não explorada neste
projeto.

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
outra). Resultado: 82 registos (2019-2022), dos quais 2 (a mesma
entrada, partida por uma quebra de página) ficaram incompletos (falha
visível, não silenciosa — ver limitações).

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
  metodologia "24h": só 2023–2024 (24 linhas) — é a única janela de anos
  em que a ANSR publicou o anexo "24h" já com uma tabela mensal
  equivalente à do anexo "30 dias".
- `data/processed/pdf_tables_index.csv` — índice de **4289 tabelas**
  extraídas dos 21 relatórios nacionais de 1999–2019 (ano, ficheiro de
  origem, página, índice da tabela na página, nº de linhas/colunas,
  caminho do CSV, preview da primeira linha).
- `data/processed/pdf_raw/<ano>/p<página>_t<tabela>.csv` — dump bruto de
  cada tabela detetada pelo `pdfplumber`, célula a célula, tal como
  extraída do PDF (sem tentar interpretar o layout).
- `data/processed/pontos_negros.csv` — 82 registos de pontos negros (2019-2022):
  `year, entidade_gestora, estrada, km, relatorio_data,
  estado_intervencao` (ver secção "Pontos Negros" acima).

## Limitações conhecidas / próximos passos

- As ~4289 tabelas de `pdf_raw/` **não estão normalizadas** — o layout
  varia significativamente ao longo de 21 anos de relatórios (agências e
  metodologias diferentes), pelo que forçar um esquema único seria
  pouco fiável. Ficam como dump bruto pesquisável; extrair uma série
  "tidy" (ex.: total nacional anual de acidentes/vítimas 1999-2019) é um
  próximo passo natural, mas exige verificar a tabela certa caso a caso.
- pdfplumber também deteta ruído (tabelas de 1 linha/coluna vindas de
  gráficos ou blocos de texto) — o índice inclui tudo o que foi
  encontrado, sem filtrar por relevância.
- O formato mensal de 2025 (`sheet '4 e 5'`) já está incluído na série
  mensal, mas a deteção deste layout ("Quadros" combinados numa sheet,
  ex. `'4 e 5'`) só foi validada contra um único ficheiro (setembro
  2025) — vale a pena confirmar quando sair a próxima edição mensal.
- A série Continente/24h só tem 2023–2024: para 2020-2022 a ANSR só
  publicou o anexo `.xlsx` "30 dias" (confirmado no manifesto — não há
  um anexo "24h" em Excel para esses anos, só em PDF, que não é
  processado por este parser).
- `xlsx_raw/` e `pdf_raw/` guardam cada tabela tal como está na fonte
  (com cabeçalhos de várias linhas, células vazias, linhas de totais);
  útil para não perder informação, mas a maioria das tabelas ainda não
  tem uma versão "tidy" própria como a série mensal nacional.
- `pontos_negros.csv` não tem geolocalização (ver secção acima) e não
  inclui o texto de "Problemas identificados"/"Recomendações" (descartado
  deliberadamente por risco de atribuição incorreta). 2 dos 82 registos
  (ano 2021, mesma entrada EN106) ficaram partidos em dois — essa entrada
  tem um texto de estado invulgarmente longo (justificação em vez do
  habitual "Implementadas"/"Não Implementadas") que atravessa uma quebra
  de página, e a heurística "novo registo começa numa página nova" corta
  o texto ao meio. Fica visível no CSV (uma linha com todos os campos de
  identidade vazios) para quem quiser juntar à mão. Só cobre 2019-2022 —
  não encontrei PDFs "PN" para 2023+ na página da fonte à data da
  recolha.
