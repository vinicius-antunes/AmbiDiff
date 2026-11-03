"""Pareamento conservador e diagnóstico auditável com grafo exclusivamente fictício."""
import copy
import threading
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from ambidiff.core import Pagina
from ambidiff.paired import _link_pairs,_evidencia_semantica
from ambidiff.diagnostics import montar_diagnostico
from ambidiff import checkpoints as cp
from test_update18 import A,B,opcao,executar


def pagina(base,itens,titulo='Atendimento ao consumidor'):
    return Pagina(base,'',titulo,itens,['Página inicial'])


class PairingEfficiencyTests(unittest.TestCase):
    def test_menu_reorganizado_rota_mesma_pareia_sem_repetir_visita(self):
        def grafo(u):
            base=A if u.startswith(A) else B
            return [opcao('Atendimento',base+'servico','Menu lateral' if base==A else 'Rodapé',recurso='navegacao')] if u==base else []
        r,abertas,_=executar(grafo)
        self.assertEqual(r['andamento']['pares_comparados'],2)
        self.assertEqual(len(abertas),4)
        self.assertEqual(r['andamento']['pares_inconclusivos'],0)

    def test_ambiguidade_nao_associa_e_rotulos_distintos_nao_somem(self):
        a=pagina(A,[opcao('Consultar',A+'x','Menu'),opcao('Consultar',A+'x','Rodapé')])
        b=pagina(B,[opcao('Consultar',B+'x','Conteúdo')])
        self.assertEqual(_link_pairs(a,b,base_a=A,base_b=B),[])
        b.itens[0].nome='Outro serviço'
        self.assertEqual(_link_pairs(a,b,base_a=A,base_b=B),[])

    def test_query_liferay_identidade_preservada(self):
        a=pagina(A,[opcao('Consultar',A+'pagina?c=1&e=2','Menu')])
        b=pagina(B,[opcao('Consultar',B+'pagina?c=2&e=2','Rodapé')])
        self.assertEqual(_link_pairs(a,b,base_a=A,base_b=B),[])

    def test_semantica_nao_depende_so_de_titulo_nem_de_menu_global(self):
        def refs(base,local='Conteúdo principal'):
            return [opcao('Requerimentos',base+'requerimentos',local,recurso='navegacao'),opcao('Prazos',base+'prazos',local,recurso='navegacao')]
        self.assertTrue(_evidencia_semantica(pagina(A+'consumidor',refs(A)),pagina(B+'atendimento',refs(B)),A,B))
        self.assertFalse(_evidencia_semantica(pagina(A,[]),pagina(B,[]),A,B))
        self.assertFalse(_evidencia_semantica(pagina(A,refs(A)),pagina(B,refs(B)),A,B,['Atendimento ao consumidor']))
        self.assertFalse(_evidencia_semantica(pagina(A,refs(A,'Menu')),pagina(B,refs(B,'Menu')),A,B))
        self.assertFalse(_evidencia_semantica(pagina(A+'?c=1',refs(A)),pagina(B+'?c=2',refs(B)),A,B))

    def test_rotas_diferentes_corrobora_sem_apagar_divergencia(self):
        def grafo(u):
            base=A if u.startswith(A) else B
            if u==base:return [opcao('Consumidor',base+('consumidor' if base==A else 'atendimento'),'Menu lateral',recurso='navegacao')]
            if u in (A+'consumidor',B+'atendimento'):
                return [opcao('Requerimentos',base+'requerimentos',recurso='navegacao'),opcao('Prazos',base+'prazos',recurso='navegacao')]
            return []
        def extrair_pagina(u,chave,titulo,itens,trilha,**kw):
            return Pagina(u,chave,'Portal de teste' if u in (A,B) else 'Atendimento ao consumidor',itens,trilha,**kw)
        with patch('test_update18.Pagina',side_effect=extrair_pagina):r,abertas,_=executar(grafo)
        self.assertEqual(r['andamento']['pares_comparados'],4)
        self.assertTrue(any(x.get('elemento')=='Consumidor' and x['tipo']=='Redirecionamento' for x in r['divergencias']))
        d=next(x for x in r['diagnosticos_pares'] if x['criterio']=='candidato_semantico')
        self.assertTrue(d['evidencia_semantica']['aceita'])
        self.assertEqual(abertas.count(A+'consumidor'),1)

    def test_destinos_sem_correspondencia_interrompem_so_ramificacao(self):
        def grafo(u):
            base=A if u.startswith(A) else B
            if u==base:return [opcao('Consumidor',base+('x' if base==A else 'y'),'Menu',recurso='navegacao'),opcao('Serviço',base+'servico')]
            return []
        r,_,_=executar(grafo)
        self.assertEqual(r['andamento']['pares_comparados'],2)
        d=next(x for x in r['diagnosticos_pares'] if x['criterio']=='candidato_semantico')
        self.assertEqual(d['estado'],'redirecionamento');self.assertFalse(d['evidencia_semantica']['aceita'])

    def test_exclusiva_superficial_erro_http_ciclo_e_contagens(self):
        def grafo(u):
            if u==A:return [opcao('Notícia antiga',A+'noticias/1',recurso='navegacao'),opcao('ÁUDIOS',A+'audios',recurso='navegacao'),opcao('Falha',A+'erro')]
            if u==B:return [opcao('Falha',B+'erro')]
            return [opcao('Voltar',A,recurso='navegacao')]
        r,abertas,_=executar(grafo,falhas=(A+'erro',))
        self.assertTrue(any(d['elemento']=='ÁUDIOS' for d in r['divergencias']))
        self.assertEqual(r['andamento']['pares_exclusivamente_inspecionados'],2)
        self.assertEqual(r['andamento']['pares_com_falha'],1)
        rec=r['cobertura']['reconciliacao']
        self.assertEqual(rec['total_admitido'],sum(rec['terminais'].values())+rec['pendentes']+rec['em_processamento'])
        self.assertEqual(rec['total_admitido'],rec['html_reservado']+rec['nao_html_observado'])
        self.assertEqual(len({d['id_par'] for d in r['diagnosticos_pares']}),len(r['diagnosticos_pares']))
        self.assertEqual(montar_diagnostico(r)['diagnosticos_pares'],r['diagnosticos_pares'])
        from ambidiff.reports import exportar
        with tempfile.TemporaryDirectory() as pasta:
            paths=exportar(copy.deepcopy(r),Path(pasta),'fixture',formatos=('html',))
            html=Path(paths['html']).read_text(encoding='utf-8')
        self.assertIn('Fila processada não significa conteúdo integralmente comparado',html)
        self.assertIn('inspeções unilaterais sem contraparte: 2',html)


    def test_inspecao_superficial_nao_prepara_nem_expande_abas(self):
        from ambidiff.paired import _extrair_page
        raw={'title':'Notícia antiga','itens':[{'tipo':'Opção','chave':'x','nome':'Arquivo','destino':A+'arquivo'}],'links':[]}
        page=NS(evaluate=lambda _:raw)
        with patch('ambidiff.paired._preparar_conteudo') as preparar, patch('ambidiff.paired.coletar_aba') as abas, patch('ambidiff.adaptive.sondar',return_value={}):
            p=_extrair_page(page,A,['Notícias'],lambda _:None,profunda=False)
        preparar.assert_not_called();abas.assert_not_called()
        self.assertFalse(p.coleta['inspecao_profunda']);self.assertEqual(p.itens[0].nome,'Arquivo')

    def test_nao_html_conta_separado_sem_presumir_as_oito_entradas(self):
        def grafo(u):
            base=A if u.startswith(A) else B
            return [opcao('Recurso',base+'recurso')] if u==base else []
        r,_,_=executar(grafo,mimes={A+'recurso':'application/pdf',B+'recurso':'application/pdf'})
        rec=r['cobertura']['reconciliacao']
        self.assertEqual(rec['total_admitido'],2);self.assertEqual(rec['html_reservado'],1)
        self.assertEqual(rec['nao_html_observado'],1)

    def test_sondagem_com_falha_preserva_outro_ramo(self):
        def grafo(u):
            base=A if u.startswith(A) else B
            if u==base:return [opcao('Consumidor',base+('x' if base==A else 'y'),'Menu',recurso='navegacao'),opcao('Serviço',base+'servico')]
            if u==A+'x':raise RuntimeError('Extração simulada indisponível')
            return []
        r,_,_=executar(grafo)
        self.assertEqual(r['andamento']['pares_comparados'],2)
        self.assertEqual(r['andamento']['pares_com_falha'],1)
        d=next(d for d in r['diagnosticos_pares'] if d['estado']=='falha')
        self.assertIn('simulada',d['erros'][0]['erro'])

    def test_externo_e_invalido_nao_navegam_e_preservam_servico(self):
        def grafo(u):
            base=A if u.startswith(A) else B
            return [opcao('Inválido','http://[invalido',recurso='navegacao'),opcao('Externo','https://externo.invalid/fora',recurso='navegacao'),opcao('Serviço',base+'servico')] if u==base else []
        r,abertas,_=executar(grafo)
        self.assertEqual(r['andamento']['pares_comparados'],2)
        self.assertEqual(len(abertas),4)
        self.assertTrue(all(u.startswith((A,B)) for u in abertas))

    def test_checkpoint_preserva_ids_e_compatibilidade_sem_campo_novo(self):
        stop=threading.Event();snaps=[]
        def grafo(u):
            base=A if u.startswith(A) else B
            if u not in (A,B):stop.set()
            return [opcao('Serviço',base+'1')] if u==base else []
        executar(grafo,parar=stop,checkpoint=lambda s:snaps.append(copy.deepcopy(s)))
        estado=cp.validar(snaps[-1]['retomada']);ids={tuple(x['par']):x['id_par'] for x in estado['diagnosticos_pares']}
        r,_,_=executar(lambda u:[],retomada=snaps[-1]['retomada'])
        self.assertTrue(all(ids[tuple(d['par'])]==d['id_par'] for d in r['diagnosticos_pares']))
        legado=copy.deepcopy(estado);legado.pop('diagnosticos_pares')
        r,_,_=executar(lambda u:[],retomada=cp.empacotar(legado))
        self.assertEqual(r['andamento']['pares_pendentes'],0)
