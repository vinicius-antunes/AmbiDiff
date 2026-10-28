"""Recuperação conservadora de ERR_ABORTED; não ignora TLS nem muda destinos."""
import time
from .core import permitido,url_limpa
from .security import url_diagnostica


def abrir(page,url,base,parar,metricas,eventos,ambiente,navegar):
    anterior=page.url
    try:return navegar(page,url)
    except Exception as exc:
        if 'ERR_ABORTED' not in str(exc):raise
        inicio=time.perf_counter()
        evento={'tipo':'NAVEGACAO_ABORTADA','ambiente':ambiente,'url':url_diagnostica(url),'destino_observado':url_diagnostica(page.url),'recuperada':False}
        eventos.append(evento);metricas.contagens['navegacoes_abortadas']+=1
        try:
            if hasattr(page,'is_closed') and page.is_closed():raise RuntimeError('Target page, context or browser has been closed após ERR_ABORTED') from exc
            # Não usa o DOM de uma página anterior que continuou aberta.
            if page.url!=anterior and permitido(page.url,base):
                try:
                    page.wait_for_load_state('domcontentloaded',timeout=5000)
                    pronto=page.evaluate("() => document.readyState!=='loading' && (document.body?.innerText?.trim().length||0)>=80")
                    if pronto:
                        evento.update(recuperada=True,recuperacao='DOM de navegação observada; destino continua sujeito à comparação normal')
                        metricas.contagens['navegacoes_recuperadas']+=1;return None
                except Exception:
                    if hasattr(page,'is_closed') and page.is_closed():raise RuntimeError('Target page, context or browser has been closed durante recuperação') from exc
            # Só repete o endereço originalmente autorizado, uma vez. Não segue
            # outra rota com base em aparência ou ignora uma falha TLS.
            if parar.is_set() or not permitido(url,base):raise exc
            url_limpa(url);metricas.contagens['tentativas_navegacao_adicionais']+=1
            response=navegar(page,url)
            evento.update(recuperada=True,recuperacao='Uma repetição controlada do endereço original')
            metricas.contagens['navegacoes_recuperadas']+=1
            return response
        finally:metricas.tempos['recuperacao_falhas']+=time.perf_counter()-inicio
