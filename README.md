# Legal Research API 4.1.1

Serviço FastAPI com as seis ferramentas MCP autenticadas por OAuth/Auth0. As rotas REST continuam exigindo o Bearer legado. Nenhuma credencial é armazenada neste repositório.

## O que mudou

- Identificadores normativos são comparados por número, espécie e ano, sem correspondência por fragmentos. `13.019` não corresponde a `132` nem a `14133`.
- Descoberta de normas federais na busca oficial da Câmara, seguida de leitura da página da norma e do texto HTML ou PDF. Inclui documentos fora do catálogo local.
- Conector SRU do LexML com tratamento explícito de respostas não XML e desafios de segurança. O acesso estava bloqueado na validação; o conector não é declarado homologado em produção.
- Índice SQLite FTS5 de espelhos efetivamente publicados nos dados abertos do STJ. Ementa, dispositivo, relator, órgão, processo e datas vêm do registro oficial.
- Filtros não são silenciosamente substituídos. Não há criação de decisões, classificação de precedentes pela vontade do solicitante nem datas artificiais de verificação.

## Limites que fazem parte do contrato

1. **Legislação:** Câmara federal, até cinco candidatos recuperados por consulta. O catálogo serve apenas à resolução de aliases e à recuperação dirigida do Planalto. Busca temática não constitui pesquisa exaustiva.
2. **Vigência:** `only_current=true` admite a situação documental “Não consta revogação expressa” e não garante eficácia, validade constitucional ou vigência de cada dispositivo. `vigente=null` e `vigency_verified=false` preservam essa distinção. Situação desconhecida é separada em `unverified_results`.
3. `only_current=true` com `include_revoked=true` é uma combinação inválida. Para incluir revogadas use `only_current=false, include_revoked=true`.
4. **STJ:** por padrão, dois lotes JSON mais recentes de cada conjunto Espelhos (Corte Especial, seções e turmas). A data do lote é de extração, não necessariamente de julgamento. Não cobre todo o histórico. `coverage.resources` informa exatamente o que foi carregado e as falhas.
5. Resultados do STJ são espelhos com ementa e decisão; **não são o inteiro teor**. A URL é do lote oficial, acompanhada de `record_id`. O link processual, quando presente, é identificado separadamente. Não se inventa URL individual do acórdão.
6. `precedent_only` exige campos estruturados `tema` e `teseJuridica` no próprio registro; não confirma superação/modulação posterior. A [ajuda oficial do STJ](https://centraldeajuda.stj.jus.br/cat_perguntas/jurisprudencia/page/3/) descreve Tese Jurídica como tese firmada em repetitivo ou IAC.
7. **STF, CNJ e TCU:** recuperação documental pendente. A consulta retorna vazio com a limitação explícita; não devolve portal genérico como decisão. O portal STF respondeu 403 na validação.
8. Filtro `area` em jurisprudência retorna `unsupported_filter`: os lotes não fornecem classificação equivalente. Em legislação, apenas classificações do catálogo de apoio podem satisfazer o filtro.
9. `source_last_modified` reproduz metadado da fonte quando disponível; `retrieved_at` é a coleta; `response_generated_at` é a resposta. Nenhuma dessas datas certifica vigência.
10. Trechos longos podem ser truncados de forma declarada. Confira os documentos oficiais antes de uso jurídico.

## Implantação no Render existente

Mantenha o comando de instalação `pip install -r requirements.txt` e o comando de inicialização atual (`uvicorn main:app --host 0.0.0.0 --port $PORT`, quando esse for o configurado). Não altere as variáveis OAuth nem `API_KEY`.

O índice inicia em segundo plano e verifica novos lotes a cada hora. O processo utiliza apenas recursos públicos; não exige assinatura externa. A primeira carga pode levar minutos. Consultas durante a carga informam a cobertura parcial. `getHealth` expõe `stj_index_status` e o commit do Render.

Variáveis opcionais:

| Variável | Padrão | Efeito |
|---|---|---|
| `LEGAL_INDEX_PATH` | `/tmp/legal-research-index.sqlite3` | Local do índice. Sem disco persistente ele é reconstruído após reinícios; isso é esperado. |
| `STJ_RESOURCES_PER_DATASET` | `2` | Entre 1 e 12 lotes recentes por conjunto. Maior cobertura consome mais disco, rede e tempo. |
| `LEGAL_INDEX_BACKGROUND` | `1` | `0` desliga a atualização em segundo plano, usado apenas em testes. |

Não é necessário contratar disco para a configuração padrão. Aumentar cobertura ou introduzir persistência requer avaliar capacidade e custo. O índice local de validação inicial ocupou aproximadamente 110 MB; o consumo varia por lote. Recomenda-se um único worker para evitar coleta duplicada.

## Verificação

```bash
pip install -r requirements.txt pytest
python -m pytest -q
# Opt-in: acessa os serviços oficiais e grava evidências resumidas, sem segredos.
LEGAL_INDEX_BACKGROUND=0 python scripts/validate_live.py
```

Os testes isolados simulam fontes para validar identidade, filtros, autenticação, PDF alternativo e falhas. `LIVE_VALIDATION.json` registra consultas reais e não deve ser confundido com os testes simulados. Não contém credenciais nem dados privados.

## Segurança

URLs e redirecionamentos passam por lista fechada de hosts oficiais HTTPS, sem credenciais e portas arbitrárias. Downloads e cache são limitados. Desafios de segurança não são contornados. O cliente externo não envia tokens do usuário. A verificação OAuth mantém emissor, audiência, assinatura RS256, escopo e sujeito proprietário.

## Reversão

Se a nova versão falhar, publique no Render o commit anteriormente saudável `f311c6afb9976e7083adc092a21973263abfa5f9`. Esse retorno restaura também as limitações de pesquisa da versão 4.0. O índice pode ser reconstruído; não há migração de dados privados.

## Ajuste 4.1.1 após teste no Render

O leitor PDF usa PDFium com mutex obrigatório para evitar chamadas nativas concorrentes. A extração da Lei 14.133/2021 excedia o prazo com o leitor Python no servidor; o processamento nativo reduz esse custo. A tabela de busca STJ usa `rowid` para exclusão/substituição eficiente, evitando varredura completa por acórdão. O índice derivado é migrado automaticamente sem apagar os registros-fonte.
