"""Benchmark local real: dois motores, portais idênticos e verdade conhecida.

Executar dentro de ambidiff-next: python scripts/benchmark_comparative.py --program both
O executável Chromium pode ser configurado por AMBIDIFF_NEXT_CHROMIUM. O benchmark
não oferece parâmetro URL e nunca inicia acesso aos portais institucionais reais.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import threading
import time
import unicodedata
from urllib.parse import urlsplit

NEXT_ROOT=Path(__file__).resolve().parents[1]
REPOSITORY=NEXT_ROOT.parent
sys.path[:0]=[str(NEXT_ROOT),str(NEXT_ROOT/'tests'),str(REPOSITORY)]
from benchmark_portals import PortalPair, TRUTH, NEGATIVES, VIEWPORT


def normalized(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD',str(value or '')).casefold() if not unicodedata.combining(c)).split())


def nature(value):
    text=normalized(value)
    for category,words in (
        ('editorial',('editorial','dados')),
        ('automacao',('automacao','automation','falha de acesso')),
        ('documento',('document','arquivo')),
        ('funcional',('funcion','functional','clique','click')),
        ('visual',('visual','imagem','aparencia','icone','pixel','layout')),
        ('redirecionamento',('redirecion','redirect','destino','navega','navigation')),
        ('estrutural',('estrut','struct','opcao','menu','campo','botao','ausen','missing')),
    ):
        if any(word in text for word in words):return category
    return 'outro'


def canonical_observations(report,program):
    """Adapter explícito; não trata o legado como ground truth.

    Editorial e falhas da automação não são defeitos confirmados. Diferenças
    registradas como possíveis continuam candidatas, reportadas separadamente.
    """
    rows=report.get('occurrences',report.get('findings',[])) if program=='next' else report.get('divergencias',[])
    result=[]
    for row in rows:
        category=nature(row.get('nature') or (str(row.get('categoria',''))+' '+str(row.get('tipo',''))))
        if category in ('editorial','automacao'):continue
        label=normalized(row.get('element',row.get('elemento','')))
        confidence=normalized(row.get('confidence',row.get('grau_confianca','possivel')))
        result.append({'nature':category,'element':label,'page_a':row.get('page_a',row.get('url_presente','')),
                       'page_b':row.get('page_b',row.get('url_comparada','')),
                       'confidence':confidence,'source_id':row.get('id')})
    return result


def evaluate(observations,truth=TRUTH):
    """Um TP por entidade de verdade; duplicatas não multiplicam precisão/recall.

    São candidatos de diferença detectados, não um atestado de defeito. Detecções
    sem vínculo à verdade controlada são FP candidatos e precisam de revisão.
    """
    found=set();unmatched=set();matched_observations=[]
    for observation in observations:
        hits=[]
        for item in truth:
            if observation.get('nature')!=item['nature']:continue
            same_label=normalized(item['element'])==normalized(observation.get('element'))
            # O legado dá o título da página ao detectar o redirect após goto.
            same_redirect_path=item.get('path') and any(urlsplit(observation.get(k,'')).path==item['path'] for k in ('page_a','page_b'))
            if same_label or same_redirect_path:hits.append(item['id'])
        if len(hits)==1:
            found.add(hits[0]);matched_observations.append({'truth_id':hits[0],**observation})
        else:unmatched.add((observation.get('nature'),observation.get('element'),observation.get('page_a'),observation.get('page_b')))
    expected={item['id'] for item in truth};missing=expected-found
    tp=len(found);fp=len(unmatched);fn=len(missing)
    return {'true_positives':tp,'false_positives':fp,'false_negatives':fn,
            'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
            'detected_truth_ids':sorted(found),'missing_truth_ids':sorted(missing),
            'unmatched_observations':[dict(zip(('nature','element','page_a','page_b'),key)) for key in sorted(unmatched)],
            'matched_observations':matched_observations,
            'note':'Métricas sobre candidatos de diferença nas fixtures; FP adicionais exigem revisão do manifesto e das evidências. Não medem precisão universal.'}


def qualify_gain(legacy,next_result):
    """Velocidade sem cobertura não é melhoria; desconhecido não vira zero."""
    reasons=[]
    before=legacy.get('quality',{});after=next_result.get('quality',{})
    if set(before.get('detected_truth_ids',[]))-set(after.get('detected_truth_ids',[])):
        reasons.append('Next perdeu divergências relevantes detectadas pelo legado')
    if after.get('false_negatives',len(TRUTH)):
        reasons.append('Restam divergências conhecidas não detectadas pelo Next')
    if after.get('false_positives',0)>before.get('false_positives',0):
        reasons.append('Next aumentou candidatos falsos positivos nas fixtures')
    for key in ('elements_checked','functional_executed','visual_compared'):
        old=legacy.get('metrics',{}).get(key);new=next_result.get('metrics',{}).get(key)
        if old is None or new is None:
            reasons.append('Cobertura não comparável/indisponível: '+key)
        elif new<old:reasons.append('Cobertura reduzida: '+key)
    if legacy.get('status')!='completed' or next_result.get('status')!='completed':
        reasons.append('Uma execução não terminou normalmente')
    old_time=legacy.get('seconds') or 0;new_time=next_result.get('seconds') or 0
    reduction=100*(old_time-new_time)/old_time if old_time>0 else None
    if reduction is None or reduction<=0:reasons.append('Não houve redução de tempo total')
    return {'experimental_target_percent':[30,50],'observed_time_reduction_percent':reduction,
            'qualified_improvement':not reasons,'reasons':reasons,
            'target_achieved_experimentally':not reasons and reduction>=30,
            'real_portal_gain_proven':False,
            'note':'Meta experimental, não garantia; tempos sintéticos não comprovam ganho em INDEA, SEMA ou outros portais.'}


def tree_size(root):
    files=[p for p in root.rglob('*') if p.is_file()]
    return {'files':len(files),'bytes':sum(p.stat().st_size for p in files)}


def run_next(roots,folder,capacity=80):
    from ambidiff_next.store import Store
    from ambidiff_next.engine import Engine
    store=Store(folder/'state.sqlite3')
    config={'roots':list(roots),'labels':['PRD','HOMOL'],'name':'Benchmark local fictício',
            'outdated':'HOMOL','capacity':capacity,'editorials_per_template':2,
            'viewport':VIEWPORT,'functional':True,'visual':True,'max_component_captures':80}
    if os.environ.get('AMBIDIFF_NEXT_CHROMIUM'):config['executable_path']=os.environ['AMBIDIFF_NEXT_CHROMIUM']
    run_id=store.create_run(config);started=time.perf_counter()
    Engine(store,folder/'evidence').run(run_id,threading.Event())
    seconds=time.perf_counter()-started;report=store.report(run_id)
    run=report.get('run',{});metrics=run.get('metrics',{})
    return {'program':'next','seconds':seconds,'status':'completed' if run.get('status') in ('completed','concluido','finished') else run.get('status'),
            'metrics':{k:metrics.get(k) for k in ('navigations','elements_checked','functional_executed','functional_inconclusive','visual_compared')},
            'phase_seconds':{k.removesuffix('_seconds'):v for k,v in metrics.items() if k.endswith('_seconds') and isinstance(v,(int,float))},'coverage':metrics.get('coverage',run.get('coverage',{})),
            'observations':canonical_observations(report,'next'),'artifacts':tree_size(folder),'run_id':run_id,
            'reported_metrics':metrics}


def run_legacy(roots,folder):
    from ambidiff.paired import executar_pareado
    from ambidiff.checkpoints import gravar
    folder.mkdir(parents=True,exist_ok=True)
    stop=threading.Event();started=time.perf_counter()
    report=executar_pareado(*roots,'PRD','HOMOL',stop,lambda _:None,lambda _:None,
        site_nome='Benchmark local fictício',evidencias_dir=folder/'evidence',
        verificar_cliques=True,varredura_inteligente=True,ambiente_desatualizado='HOMOL',
        checkpoint=lambda state:gravar(folder/'checkpoint.json',state))
    seconds=time.perf_counter()-started
    m=report.get('metricas',{});counts=m.get('contagens',{});functional=report.get('resultados_funcionais',[])
    # The legacy supplies link counts, not a true number of verified components.
    # Counting links as components would inflate apparent legacy coverage.
    metrics={'navigations':counts.get('operacoes_navegacao'), 'elements_checked':None,
             'functional_executed':2*sum(bool(r.get('conclusivo')) for r in functional),
             'functional_inconclusive':2*sum(not r.get('conclusivo') for r in functional),
             'visual_compared':None}
    return {'program':'legacy','seconds':seconds,'status':'completed' if report.get('estado_execucao')=='finalizado' else report.get('estado_execucao'),
            'metrics':metrics,'phase_seconds':m.get('tempos_segundos',{}),
            'coverage':report.get('cobertura',{}),'observations':canonical_observations(report,'legacy'),
            'artifacts':tree_size(folder),'reported_metrics':m,
            'metric_limitations':['O legado não publica contagem equivalente de componentes verificados nem de comparações reais de pixels. Valores indisponíveis são null.']}


def benchmark(program='both',news=8,repeats=1,output=None):
    output=Path(output or NEXT_ROOT/'data'/'benchmarks'/time.strftime('%Y%m%d_%H%M%S'))
    output.mkdir(parents=True,exist_ok=True);results=[]
    with PortalPair(news=news) as portals:
        for repeat in range(repeats):
            # Alternate order to reduce consistent warm-cache ordering bias.
            order=('legacy','next') if repeat%2==0 else ('next','legacy')
            for name in order:
                if program!='both' and program!=name:continue
                folder=output/f'{name}-{repeat+1}';folder.mkdir()
                portals.reset()
                try:result=(run_legacy if name=='legacy' else run_next)(portals.roots,folder)
                except Exception as error:
                    result={'program':name,'status':'failed','error':type(error).__name__+': '+str(error),'seconds':None,'metrics':{},'observations':[]}
                result['server_observation']=portals.snapshot();result['repeat']=repeat+1
                result['quality']=evaluate(result.pop('observations'))
                result['metrics']['html_requests_observed']=result['server_observation']['counts'].get('html_requests',0)
                results.append(result)
        comparison=None
        if program=='both':
            aggregate={}
            for name in ('legacy','next'):
                values=[r for r in results if r['program']==name]
                aggregate[name]=dict(values[0])
                durations=[r['seconds'] for r in values if r.get('seconds') is not None]
                aggregate[name]['seconds']=statistics.median(durations) if durations else 0
                aggregate[name]['status']='completed' if all(r.get('status')=='completed' for r in values) else 'failed'
                aggregate[name]['metrics']={key:(min if name=='next' else max)(r['metrics'][key] for r in values) if all(r['metrics'].get(key) is not None for r in values) else None for key in ('navigations','elements_checked','functional_executed','functional_inconclusive','visual_compared')}
                # Conservative across repetitions: worst quality, no unstable TP credit.
                common=set.intersection(*(set(r['quality']['detected_truth_ids']) for r in values))
                aggregate[name]['quality']={**values[0]['quality'],'detected_truth_ids':sorted(common),
                    'false_negatives':len(TRUTH)-len(common),'false_positives':max(r['quality']['false_positives'] for r in values)}
            comparison=qualify_gain(aggregate['legacy'],aggregate['next'])
    payload={'schema_version':1,'fixture':'local-services-v1','viewport':VIEWPORT,'news_per_portal':news,
        'legacy_reference':'1f79c55c0b187a5a159d54c84344f6dcd98ff342','truth':TRUTH,'negative_cases':NEGATIVES,
        'repetitions':repeats,'results':results,'comparison':comparison,
        'scope':'Somente loopback fictício. INDEA/SEMA não foram acessados; exigem autorização posterior.',
        'limitations':['Tempo das fases pode se sobrepor; não somar fases aninhadas.',
            'O total inclui evidências/checkpoints de cada produto; as capacidades não são idênticas.',
            'html_requests_observed inclui recargas de testes e evidências; redirects estão em contador separado.',
            'Amostragem editorial é explícita; páginas amostradas não validam outras páginas.',
            'Nenhum ganho qualificado é declarado quando cobertura obrigatória não é comparável.']}
    target=output/'summary.json';target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    return payload,target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--program',choices=('both','next','legacy'),default='both')
    parser.add_argument('--news',type=int,default=8)
    parser.add_argument('--repeats',type=int,default=1)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not 1<=args.news<=100 or not 1<=args.repeats<=5:parser.error('news: 1–100; repeats: 1–5')
    result,path=benchmark(args.program,args.news,args.repeats,args.output)
    print(json.dumps({'summary':str(path),'comparison':result['comparison'],
        'results':[{'program':r['program'],'status':r['status'],'seconds':r['seconds'],'quality':r['quality']} for r in result['results']]},ensure_ascii=False,indent=2))
    return 0 if all(r['status'] in ('completed','partial') for r in result['results']) else 1

if __name__=='__main__':raise SystemExit(main())
