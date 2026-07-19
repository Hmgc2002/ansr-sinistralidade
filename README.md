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
  simples e ainda por confirmar como estável (só há uma edição, de
  setembro, até à data).

Nota de qualidade dos dados da própria fonte: os nomes dos ficheiros têm
inconsistências duplicadas (`Cópia de Cópia de Anexo...2024.xlsx`), e a
partir de pelo menos 2010 a ANSR publica **dois relatórios/anexos por
ano com metodologias de contagem de vítimas mortais diferentes** — "24
horas" (norma internacional) vs "30 dias" (norma tradicional
portuguesa). Este projeto usa consistentemente a série "30 dias" em
ambos os parsers, porque é a que aparece de forma mais consistente ao
longo dos anos; isto deve ser tido em conta em qualquer comparação com
estatísticas internacionais.

## Outputs gerados

- `data/processed/manifest.csv` — catálogo de todos os 490 documentos
  (ano, título, url, nome de ficheiro, extensão).
- `data/processed/xlsx_tables_index.csv` — índice de todas as ~380
  tabelas extraídas dos anexos Excel (ano, id do quadro, título, caminho
  do CSV correspondente).
- `data/processed/xlsx_raw/<ano>/<quadro>.csv` — dump bruto de cada
  tabela, célula a célula, tal como está no Excel original.
- `data/processed/sinistralidade_mensal.csv` — série mensal nacional
  2020–2024 (60 linhas), já normalizada: `report_year, month, month_num,
  acidentes_com_vitimas, vitimas_mortais, feridos_graves, feridos_leves`.
- `data/processed/pdf_tables_index.csv` — índice de **4289 tabelas**
  extraídas dos 21 relatórios nacionais de 1999–2019 (ano, ficheiro de
  origem, página, índice da tabela na página, nº de linhas/colunas,
  caminho do CSV, preview da primeira linha).
- `data/processed/pdf_raw/<ano>/p<página>_t<tabela>.csv` — dump bruto de
  cada tabela detetada pelo `pdfplumber`, célula a célula, tal como
  extraída do PDF (sem tentar interpretar o layout).

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
- O formato mensal de 2025 (`sheet '4 e 5'`) ainda não é normalizado —
  só está no dump bruto do `parser_xlsx.py`.
- Os anexos "24 horas" (2020–2024) ainda não são extraídos para a série
  mensal — só os "30 dias".
- `xlsx_raw/` e `pdf_raw/` guardam cada tabela tal como está na fonte
  (com cabeçalhos de várias linhas, células vazias, linhas de totais);
  útil para não perder informação, mas a maioria das tabelas ainda não
  tem uma versão "tidy" própria como a série mensal nacional.
