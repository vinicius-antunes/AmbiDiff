"""Navegação concorrente restrita às duas páginas do par corrente."""
import asyncio
import time

from . import core
from .browser import fechado
from .security import url_diagnostica


async def _abrir(page, url, parar):
    try:
        return await page.goto(url, wait_until='domcontentloaded', timeout=core.TEMPO_PAGINA_MS)
    except Exception as exc:
        if parar.is_set() or ('Timeout' not in type(exc).__name__ and 'Timeout' not in str(exc)):
            raise
        try:
            dados = await page.evaluate(core.JS_DOM_TIMEOUT)
            if core.url_limpa(dados['url']) == core.url_limpa(url) and dados['n'] >= 80:
                return None
        except Exception:
            pass
        if parar.is_set():
            raise
        return await page.goto(url, wait_until='commit', timeout=core.TEMPO_PAGINA_MS)


async def _navegar(page, url, base, ambiente, parar, metricas, eventos):
    anterior = page.url

    async def tentativa():
        metricas.contagens['navegacoes_html_tentadas'] += 1
        return await _abrir(page, url, parar)

    try:
        return await tentativa()
    except Exception as exc:
        if 'ERR_ABORTED' not in str(exc):
            raise
        inicio = time.perf_counter()
        evento = {'tipo': 'NAVEGACAO_ABORTADA', 'ambiente': ambiente, 'url': url_diagnostica(url),
                  'destino_observado': url_diagnostica(page.url), 'recuperada': False}
        eventos.append(evento)
        metricas.contagens['navegacoes_abortadas'] += 1
        try:
            if page.is_closed():
                raise RuntimeError('Target page, context or browser has been closed após ERR_ABORTED') from exc
            if page.url != anterior and core.permitido(page.url, base):
                try:
                    await page.wait_for_load_state('domcontentloaded', timeout=5000)
                    if await page.evaluate(core.JS_DOM_NAVEGACAO_ABORTADA):
                        evento.update(recuperada=True, recuperacao='DOM de navegação observada; destino continua sujeito à comparação normal')
                        metricas.contagens['navegacoes_recuperadas'] += 1
                        return None
                except Exception:
                    if page.is_closed():
                        raise RuntimeError('Target page, context or browser has been closed durante recuperação') from exc
            if parar.is_set() or not core.permitido(url, base):
                raise
            core.url_limpa(url)
            metricas.contagens['tentativas_navegacao_adicionais'] += 1
            response = await tentativa()
            evento.update(recuperada=True, recuperacao='Uma repetição controlada do endereço original')
            metricas.contagens['navegacoes_recuperadas'] += 1
            return response
        finally:
            metricas.tempos['recuperacao_falhas'] += time.perf_counter() - inicio


async def navegar_par(paginas, urls, bases, ambientes, parar, metricas, eventos):
    """Conclui ou drena as duas tarefas antes de a fila voltar a progredir."""
    if parar.is_set():
        return None

    resultados = [None, None]

    async def lado(indice, page, url, base, ambiente):
        inicio = time.perf_counter()
        metricas.contagens['operacoes_navegacao'] += 1
        try:
            resposta = await _navegar(page, url, base, ambiente, parar, metricas, eventos)
            resultados[indice] = (resposta, None)
        except Exception as erro:
            resultados[indice] = (None, erro)
        finally:
            metricas.tempos[f'navegacao_lado_{indice}_segundos'] += time.perf_counter() - inicio

    inicio_par = time.perf_counter()
    tarefas = [asyncio.create_task(lado(i, *args)) for i, args in enumerate(zip(paginas, urls, bases, ambientes))]
    try:
        pendentes = set(tarefas)
        while pendentes and not parar.is_set():
            _, pendentes = await asyncio.wait(pendentes, timeout=0.05, return_when=asyncio.FIRST_COMPLETED)
            if any(r and r[1] and fechado(r[1]) for r in resultados):
                # O outro lado pode estar recebendo o mesmo fechamento. Dá
                # ao transporte uma passagem curta para entregar disconnected.
                if pendentes and not parar.is_set():
                    await asyncio.wait(pendentes, timeout=0.1)
                break
        return None if parar.is_set() else resultados
    finally:
        for tarefa in tarefas:
            if not tarefa.done():
                tarefa.cancel()
        await asyncio.gather(*tarefas, return_exceptions=True)
        metricas.tempos['navegacao'] += time.perf_counter() - inicio_par
