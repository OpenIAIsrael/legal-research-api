# Ajuste após validação no Render — 15/10/2026

A versão 4.2.0 foi publicada no commit a61d491360712036adcef6495a61f64ff1532982. getHealth autenticado confirmou a versão e o commit. Os índices TCU e STJ iniciaram a carga em segundo plano. O Infojuris CNJ respondeu HTTP 403 a partir do Render, embora a mesma pesquisa pública tenha funcionado na máquina de validação, com decisões individualizadas registradas em VALIDATION_4_2_REAL.json. Não foi contornado esse bloqueio.

A versão 4.2.1 acrescenta o canal de publicações de Informativos de Jurisprudência do próprio CNJ, vinculado por sua página de jurisprudência. O documento real recuperado na validação local foi o Informativo nº 9/2026, de 22/06/2026, PDF com 35.746 caracteres, disponível em https://atos.cnj.jus.br/files/original131140202608186a845a0cc4200.pdf e SHA-256 2cdddb734a475c88ea3ca3920490366f74b6daeb88b4e3b3fefa20a25a436846. Cabeçalho, número, ano e termos da pesquisa foram confirmados no PDF.

O próprio documento ressalva conter resumos não oficiais e condiciona sua conferência ao acórdão publicado no DJ-e. A API preserva essa distinção: class=informativo_jurisprudencia, content_nature=resumos_nao_oficiais_publicados_pelo_cnj, case_number=null, judgment_date=null, full_text_retrieved=false, bulletin_full_text_retrieved=true. Não atribui condição de precedente. A falha do Infojuris é mantida nos avisos. Somente dois PDFs da primeira página podem ser recuperados; isso não equivale à pesquisa de todos os julgados do CNJ.

Os limites totais de Infojuris e canal alternativo são 20 e 28 segundos. A carga inicial da íntegra STJ passa a ocorrer em paralelo à do TCU, em bancos separados; não altera o plano do Render nem contrata recursos.

65 testes passaram. A validação em produção do canal alternativo e dos índices concluídos deve ser registrada após a implantação. STF continua bloqueado por HTTP 403; sua recuperação documental não foi homologada.
