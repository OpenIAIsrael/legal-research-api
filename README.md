# Legal Research API 4.2.1

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
5. **STJ:** espelhos têm `full_text_retrieved=false`. Um segundo índice recupera textos nos três lotes diários JSON/ZIP mais recentes do conjunto oficial de íntegras. Só apresenta íntegra quando `SeqDocumento` corresponde ao arquivo TXT presente no ZIP. `source_record_locator` informa lote, membro e ID. Metadados sem TXT não são apresentados como texto recuperado. A resposta pode conter trecho truncado da íntegra, com contagem e truncamento explícitos. As duas janelas não cobrem todo o histórico.
6. `precedent_only` exige campos estruturados `tema` e `teseJuridica` no próprio registro; não confirma superação/modulação posterior. A [ajuda oficial do STJ](https://centraldeajuda.stj.jus.br/cat_perguntas/jurisprudencia/page/3/) descreve Tese Jurídica como tese firmada em repetitivo ou IAC.
7. **CNJ:** pesquisa pública do Infojuris, seguida de recuperação de até dez registros individuais com processo, relator, data, ementa e certidão. Sem login, sem operação de edição e sem alegar íntegra ou precedente qualificado. O redirecionamento HTTP emitido pelo formulário só é aceito para o caminho público conhecido do mesmo host após promovê-lo a HTTPS; nunca há requisição em HTTP.

   No Render, o Infojuris apresentou HTTP 403 mesmo estando acessível na máquina de validação. Em caso de falha, o conector usa a publicação pública de Informativos em atos.cnj.jus.br: no máximo dois PDFs, selecionados dentre os assuntos da primeira página e conferidos por número, ano e termos presentes no texto. São publicações do CNJ contendo **resumos não oficiais**, conforme ressalva do próprio PDF, e não acórdãos individualizados. `class=informativo_jurisprudencia`, `content_nature=resumos_nao_oficiais_publicados_pelo_cnj`, `full_text_retrieved=false` e `bulletin_full_text_retrieved=true` preservam essa distinção. O número de processo fica nulo; não se infere precedente qualificado. A falha do Infojuris permanece nos avisos. Infojuris e canal alternativo têm limites totais de 20 e 28 segundos, respectivamente.
8. **TCU:** CSV oficial de acórdãos do ano corrente, mais respostas a consultas e súmulas. Acórdãos recuperam campos ACORDAO, DECISAO, RELATORIO e VOTO, sem usar o campo de resumo gerado por IA. Consultas/súmulas são identificadas como enunciados e excertos, sem alegar íntegra. Súmula só satisfaz `precedent_only` quando a fonte informa VIGENTE; isso não a transforma em precedente vinculante do CPC nem verifica superação posterior. Anos anteriores ficam fora da cobertura padrão.
9. **STF:** canal oficial de teses é consultado para diagnóstico de disponibilidade; enquanto não há acesso automatizado permitido e formato documental homologado, retorna vazio com falha explícita. Não contorna 403, desafios de segurança ou autenticação. Não confundir teste de disponibilidade com conector de pesquisa homologado.
10. Filtro `area` em jurisprudência não retorna documentos sem classificação equivalente confirmada. Em legislação, apenas classificações do catálogo de apoio podem satisfazer o filtro.
11. `source_last_modified` reproduz metadado da fonte quando disponível; `retrieved_at` é a coleta; `response_generated_at` é a resposta. Nenhuma dessas datas certifica vigência.
12. Trechos longos podem ser truncados de forma declarada. Confira os documentos oficiais antes de uso jurídico.

## Implantação no Render existente

Mantenha o comando de instalação `pip install -r requirements.txt` e o comando de inicialização atual (`uvicorn main:app --host 0.0.0.0 --port $PORT`, quando esse for o configurado). Não altere as variáveis OAuth nem `API_KEY`.

Os índices iniciam em segundo plano: espelhos STJ verificam lotes a cada hora; TCU e íntegra STJ a cada dia. A carga TCU usa download gradual em disco e leitura CSV por registro; o arquivo de acórdãos de 2026 mede aproximadamente 323 MB. A construção ocorre fora do ciclo de atendimento HTTP. Índices novos são substituídos atomicamente após validação; falha preserva o índice anterior e informa cache. A primeira carga leva minutos; `getHealth` expõe `stj_index_status`, `court_indexes` e commit. A instância pode reiniciar/dormir e reconstruir o cache. Não há garantia de disponibilidade contínua.

Variáveis opcionais:

| Variável | Padrão | Efeito |
|---|---|---|
| `LEGAL_INDEX_PATH` | `/tmp/legal-research-index.sqlite3` | Local do índice. Sem disco persistente ele é reconstruído após reinícios; isso é esperado. |
| `STJ_RESOURCES_PER_DATASET` | `2` | Entre 1 e 12 lotes recentes por conjunto. Maior cobertura consome mais disco, rede e tempo. |
| `LEGAL_INDEX_BACKGROUND` | `1` | `0` desliga a atualização em segundo plano, usado apenas em testes. |
| `COURT_INDEX_DIR` | Diretório temporário do sistema | Índices derivados de TCU e íntegra STJ; requer espaço temporário para CSV e construção atômica. |

Não há contratação automática de recursos. Recomenda-se um único worker para evitar coleta duplicada. TCU admite download de até 400 MB, 60 mil registros e banco derivado de até 450 MB; a substituição pode manter temporariamente CSV, banco antigo e banco novo. É necessário conferir o espaço e a memória da instância antes de ampliar cobertura. STJ admite ZIP de até 16 MB, 30 MB descomprimidos por lote, 2 MB por membro e 40 milhões de caracteres pesquisáveis na janela; nenhum membro é extraído para um caminho de disco fornecido pelo ZIP. Falhas desses limites são expostas e não produzem documentos fictícios.

## Verificação

```bash
pip install -r requirements.txt pytest
python -m pytest -q
# Opt-in: acessa os serviços oficiais e grava evidências resumidas, sem segredos.
LEGAL_INDEX_BACKGROUND=0 python scripts/validate_live.py
LEGAL_INDEX_BACKGROUND=0 python scripts/validate_courts.py
```

Os testes isolados simulam fontes para validar identidade, filtros, autenticação, PDF alternativo e falhas. `LIVE_VALIDATION.json` registra consultas reais e não deve ser confundido com os testes simulados. Não contém credenciais nem dados privados.

## Segurança

URLs e redirecionamentos passam por lista fechada de hosts oficiais HTTPS, sem credenciais e portas arbitrárias. Downloads e cache são limitados. Desafios de segurança não são contornados. O cliente externo não envia tokens do usuário. A verificação OAuth mantém emissor, audiência, assinatura RS256, escopo e sujeito proprietário.

## Reversão

Se a nova versão falhar, publique no Render o commit anteriormente saudável `aa83f6002c37746fae6fb5c3cb6c7d1561aa79e6`. Ele preserva OAuth e diagnóstico de rede, mas retorna à cobertura anterior (Câmara e espelhos STJ). Os índices derivados podem ser reconstruídos; não há migração de dados privados.

## Ajuste 4.1.1 após teste no Render

O leitor PDF usa PDFium com mutex obrigatório para evitar chamadas nativas concorrentes. A extração da Lei 14.133/2021 excedia o prazo com o leitor Python no servidor; o processamento nativo reduz esse custo. A tabela de busca STJ usa `rowid` para exclusão/substituição eficiente, evitando varredura completa por acórdão. O índice derivado é migrado automaticamente sem apagar os registros-fonte.
