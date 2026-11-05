"""Diferenças bidirecionais; fato observado separado de causa e defeito."""
from .models import finding,normalized
from .matching import match_elements
from .policy import equivalent_url,classify_resource


def compare_pages(a,b,roots,config=None):
    config=config or {};result=match_elements(a,b,roots)
    findings=[];diagnostics=list(result['ambiguous'])
    by_a={e.id:e for e in a.elements};by_b={e.id:e for e in b.elements}
    limiting={'TIMEOUT','DOM_UNAVAILABLE','AUTHENTICATION','AUTHENTICATION_REQUIRED','NON_HTML','NAVIGATION_ERROR','EXTRACTION_ERROR','BROWSER_CLOSED','ACCESS_DENIED','CERTIFICATE','DNS','NAVIGATION_INTERRUPTED','DOCUMENT_DOWNLOAD','AUTOMATION_ERROR','INVALID_URL','OUT_OF_SCOPE','STOPPED','INCOMPLETE_LOADING','EMPTY_DOM','HTTP_ERROR'}
    limited=a.status==0 or b.status==0 or a.status>=400 or b.status>=400 or any(str(d.get('code','')).upper() in limiting for d in a.diagnostics+b.diagnostics if isinstance(d,dict))
    ambiguous_a={x['a'] for x in result['ambiguous']}
    ambiguous_b={bid for x in result['ambiguous'] for bid in x['candidates_b']}
    for side,page,other,ids,by,ambiguous in (
        ('a',a,b,result['unmatched_a'],by_a,ambiguous_a),('b',b,a,result['unmatched_b'],by_b,ambiguous_b)):
        for eid in ids:
            e=by[eid]
            nature='editorial' if e.editorial else 'estrutural'
            confidence='inconclusivo' if eid in ambiguous or limited else 'possivel' if e.editorial else 'confirmado'
            findings.append(finding('opcao_nao_identificada','documento' if classify_resource(e.url,e.attrs) in ('document','document_reference') else nature,e.name,a.url,b.url,
                impact='baixo' if e.editorial else 'alto',confidence=confidence,section=e.section,
                observed_a='Presente' if side=='a' else 'Não identificado',observed_b='Presente' if side=='b' else 'Não identificado',
                evidence={side:e.attrs.get('screenshot','')},
                cause='Atualização desigual pode explicar conteúdo editorial; não comprova base desatualizada.' if e.editorial else '',
                recommendation='Conferir correspondências e limitações da coleta; não presume qual ambiente está correto.',
                element_id=e.id,environment=side))
    for match in result['matches']:
        x,y=by_a[match['a']],by_b[match['b']]
        common={'element':x.name,'page_a':a.url,'page_b':b.url,'section':x.section,'evidence':{'a':x.attrs.get('screenshot',''),'b':y.attrs.get('screenshot','')}}
        if match['confidence']=='intermediaria':
            diagnostics.append({'element_a':x.id,'element_b':y.id,'status':'possivel_correspondencia',
                                'reason':match['criteria'],'next':'Corroborar estrutura do destino ou comportamento; não é validação funcional.'})
        if normalized(x.name)!=normalized(y.name):
            findings.append(finding('rotulo_diferente','editorial' if x.editorial and y.editorial else 'estrutural',**common,
                impact='baixo',confidence='confirmado',observed_a=x.name,observed_b=y.name,
                recommendation='Rótulos podem representar a mesma finalidade; revisar clareza e consistência.'))
        if x.url and y.url and not equivalent_url(x.url,y.url,roots):
            resource_a,resource_b=classify_resource(x.url,x.attrs),classify_resource(y.url,y.attrs)
            nature='documento' if any(r in ('document','document_reference') for r in (resource_a,resource_b)) else 'editorial' if x.editorial and y.editorial else 'navegacao'
            findings.append(finding('destinos_diferentes',nature,**common,confidence='confirmado',
                observed_a=x.url,observed_b=y.url,recommendation='Diferença de referência observada; não comprova link quebrado nem ambiente correto.'))
        if x.enabled!=y.enabled:
            findings.append(finding('habilitacao_diferente','funcional',**common,confidence='confirmado',
                observed_a=str(x.enabled),observed_b=str(y.enabled),recommendation='Estado DOM observado; execução funcional ainda precisa de teste.'))
    # Ordem é opcional e só compara conjuntos inteiramente correspondentes.
    # Reorganização de HTML não significa ausência, nem mudança relevante por si.
    if config.get('compare_menu_order'):
        mapped={m['a']:m['b'] for m in result['matches']}
        groups={}
        for x in a.elements:
            if x.id in mapped and x.url:groups.setdefault(x.section,[]).append(x)
        for section,items in groups.items():
            if len(items)<2:continue
            expected=[mapped[x.id] for x in items]
            counterpart_sections={by_b[eid].section for eid in expected}
            if len(counterpart_sections)!=1:continue
            other=[y.id for y in b.elements if y.section in counterpart_sections and y.id in set(expected)]
            if len(other)==len(expected) and other!=expected:
                findings.append(finding('ordem_opcoes_diferente','estrutural','Opções de '+section,a.url,b.url,
                    confidence='confirmado',impact='baixo',section=section,
                    observed_a=' → '.join(x.name for x in items),observed_b=' → '.join(by_b[y].name for y in other),
                    recommendation='Mesmas opções em ordem diferente; relevância da ordem foi solicitada na configuração.'))
    if a.final_url and b.final_url and not equivalent_url(a.final_url,b.final_url,roots):
        findings.append(finding('redirecionamento_diferente','redirecionamento','Página',a.url,b.url,confidence='confirmado',
            observed_a=a.final_url,observed_b=b.final_url,chains={'a':a.redirects,'b':b.redirects},
            recommendation='Verificar finalidade dos destinos; rotas diferentes não significam falha de acesso.'))
    for side,page in (('a',a),('b',b)):
        if page.status>=400:
            findings.append(finding('resposta_http_erro','navegacao','Página',a.url,b.url,confidence='confirmado',
                observed_a=str(page.status) if side=='a' else '',observed_b=str(page.status) if side=='b' else '',environment=side,
                recommendation='Status observado; investigar disponibilidade e rota sem atribuir correção ao outro ambiente.'))
    return {'matches':result['matches'],'findings':findings,'diagnostics':diagnostics}


def compare_functions(obs_a,obs_b,element='',page_a='',page_b='',section=''):
    """Uma ação sem resposta só é candidata a falha se outra produz efeito.

    Observação inconclusiva/segurança nunca equivale a funcionalidade correta.
    """
    findings=[];diagnostics=[]
    if any(x.get('status')!='executed' for x in (obs_a,obs_b)):
        diagnostics.append({'element':element,'status':'funcionalidade_nao_testada',
            'reason':'Pelo menos uma ação não foi executada com segurança ou observação suficiente.','a':obs_a,'b':obs_b})
    elif obs_a.get('changed')!=obs_b.get('changed'):
        findings.append(finding('resposta_funcional_diferente','funcional',element,page_a,page_b,
            confidence='possivel',impact='alto',section=section,
            observed_a=obs_a.get('observation',str(obs_a.get('changed'))),observed_b=obs_b.get('observation',str(obs_b.get('changed'))),
            evidence={'a':obs_a.get('evidence',{}),'b':obs_b.get('evidence',{})},
            recommendation='Repetir manualmente; ausência de alteração observável não prova defeito isoladamente.'))
    elif not obs_a.get('changed'):
        diagnostics.append({'element':element,'status':'inconclusivo','reason':'Nenhuma alteração observável em ambos; não comprova funcionamento.'})
    return {'findings':findings,'diagnostics':diagnostics}
