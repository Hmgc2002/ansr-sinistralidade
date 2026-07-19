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
  parser_xlsx.py   # normaliza os anexos .xlsx em CSV
data/
  raw/             # ficheiros descarregados (não versionado, ~290 MB)
  processed/       # CSVs gerados (versionado)
```

## Como correr

```powershell
.\.venv\Scripts\python.exe src\scraper.py       # -> data/processed/manifest.csv
.\.venv\Scripts\python.exe src\downloader.py    # -> data/raw/<ano>/...
.\.venv\Scripts\python.exe src\parser_xlsx.py   # -> data/processed/*.csv
```

## O que existe na fonte (ANSR)

A página `Estatísticas > Relatórios de Sinistralidade` lista **490
documentos** (PDF e Excel) entre 1999 e 2025:

- **1999–2019**: relatórios anuais nacionais + relatórios anuais por
  distrito (só PDF, sem dados tabulares extraíveis sem OCR/parsing de PDF).
- **2020–2024**: relatório anual em PDF + um anexo `.xlsx` com ~60
  tabelas de dados por ano (quadros 1.1 a 6.17).
- **2025**: passou a ter cadência mensal, com um layout de Excel mais
  simples e ainda por confirmar como estável (só há uma edição, de
  setembro, até à data).

Nota de qualidade dos dados da própria fonte: os nomes dos ficheiros têm
inconsistências duplicadas (`Cópia de Cópia de Anexo...2024.xlsx`), e a
partir de 2020 a ANSR publica **dois anexos por ano com metodologias de
contagem de vítimas mortais diferentes** — "24 horas" (norma
internacional) vs "30 dias" (norma tradicional portuguesa). Este projeto
usa consistentemente a série "30 dias" para a série mensal nacional,
porque é a que aparece em todos os anos 2020–2024; isto deve ser tido em
conta em qualquer comparação com estatísticas internacionais.

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

## Limitações conhecidas / próximos passos

- PDFs de 1999–2019 ainda não são convertidos em tabelas (precisa de
  `pdfplumber`/`camelot`, já está no `requirements.txt` mas por usar).
- O formato mensal de 2025 (`sheet '4 e 5'`) ainda não é normalizado —
  só está no dump bruto.
- Os anexos "24 horas" (2020–2024) ainda não são extraídos para a série
  mensal — só os "30 dias".
- `xlsx_raw/` guarda cada tabela tal como está no Excel (com cabeçalhos
  de 2 linhas, células vazias, linha de totais); útil para não perder
  informação, mas a maioria das ~380 tabelas ainda não tem uma versão
  "tidy" própria como a série mensal nacional.
