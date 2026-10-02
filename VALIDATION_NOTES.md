# Validação da alteração

## Testes isolados

A suíte cobre as seis ferramentas MCP, assinatura/emissor/audiência/escopo/sujeito OAuth, REST Bearer, comparação de normas, filtros, ausências, PDF alternativo, duplicação de acórdãos, prioridade da extração mais recente, redirecionamento não permitido, tamanho máximo e erro de gateway disfarçado de HTTP 200.

## Consultas externas reais

`LIVE_VALIDATION.json` contém a última matriz completa de chamadas externas. Foram recuperados:

- Lei 13.019/2014 nas consultas `Lei 13.019/2014`, `13.019` e `13019`.
- Lei 14.133/2021 em PDF oficial quando o HTML devolveu página de erro 504 com HTTP 200.
- Lei 15.210/2025, fora do catálogo local original.
- Nenhum resultado para a consulta aleatória de ausência.

### STJ: diferença entre as duas rodadas

Na primeira rodada real de 02/10/2026 (coletas a partir de 14:34 UTC), o conector recuperou e indexou lotes oficiais. A consulta `imunidade tributária entidades beneficentes` retornou, entre outros, **AgInt no REsp 2209237**, registro documental **1451433**, com ementa e os quatro termos correspondentes. A ementa recebida iniciava com “PROCESSUAL CIVIL. AGRAVO INTERNO NO RECURSO ESPECIAL. IMUNIDADE TRIBUTÁRIA DE ENTIDADES BENEFICENTES. CEBAS.” Houve falhas parciais em quatro lotes, corretamente informadas.

Após a retomada da sessão, tanto o catálogo CKAN quanto um lote individual apresentaram timeout, inclusive em consulta direta com 30 segundos. A última matriz registra STJ indisponível; não comprova funcionamento contínuo. O índice temporário da primeira sessão não está incluído no repositório nem é apresentado como cache atual.

A carga no Render precisa ser observada depois da publicação. A versão não será descrita como pesquisa exaustiva ou fonte continuamente disponível.

## Integrações pendentes

- LexML devolveu desafio de segurança. Parser SRU testado com fixture; consulta real não homologada.
- STF devolveu 403. Sem conector documental homologado.
- CNJ e TCU: sem recuperação documental implementada nesta entrega.
- Inteiro teor de acórdãos e cobertura histórica integral do STJ não fazem parte da implementação validada.

Essas limitações são expostas por `listSources`, `warnings`, `coverage` e `retrieval_status`.
