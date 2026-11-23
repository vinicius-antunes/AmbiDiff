"""Ponte experimental para as operações Playwright usadas pelo scanner."""
import asyncio
from contextlib import contextmanager
from functools import partial
from inspect import isawaitable

from playwright.async_api import async_playwright


def _comando(nome, converter=None):
    """Executa um comando no loop proprietário e devolve o resultado ao scanner."""
    async def chamar(objeto, args, kwargs):
        valor = getattr(objeto, nome)(*args, **kwargs)
        return await valor if isawaitable(valor) else valor

    def executar(self, *args, **kwargs):
        valor = self._loop.run(chamar(self._objeto, args, kwargs))
        return converter(self._loop, valor) if converter else valor
    return executar


class _Recurso:
    def __init__(self, loop, objeto):
        self._loop = loop
        self._objeto = objeto


class _Elemento(_Recurso):
    evaluate = _comando('evaluate')
    is_visible = _comando('is_visible')
    click = _comando('click')


class _Localizador(_Elemento):
    count = _comando('count')
    get_attribute = _comando('get_attribute')
    inner_text = _comando('inner_text')
    scroll_into_view_if_needed = _comando('scroll_into_view_if_needed')
    element_handles = _comando('element_handles', lambda loop, handles: [_Elemento(loop, h) for h in handles])

    @property
    def first(self):
        return _Localizador(self._loop, self._objeto.first)

    def nth(self, indice):
        return _Localizador(self._loop, self._objeto.nth(indice))


class _Pagina(_Recurso):
    close = _comando('close')
    goto = _comando('goto')
    evaluate = _comando('evaluate')
    wait_for_load_state = _comando('wait_for_load_state')
    wait_for_timeout = _comando('wait_for_timeout')
    screenshot = _comando('screenshot')

    @property
    def url(self):
        return self._objeto.url

    def is_closed(self):
        return self._objeto.is_closed()

    def locator(self, seletor):
        return _Localizador(self._loop, self._objeto.locator(seletor))

    on = _comando('on')


class _DecisaoRota:
    """O callback síncrono escolhe a ação, que o Playwright aguarda no loop."""
    def __init__(self, rota):
        self.request = rota.request
        self.acao = rota.abort
        self._rota = rota

    def abort(self, *args, **kwargs):
        self.acao = partial(self._rota.abort, *args, **kwargs)

    def continue_(self, *args, **kwargs):
        self.acao = partial(self._rota.continue_, *args, **kwargs)

    def fulfill(self, *args, **kwargs):
        self.acao = partial(self._rota.fulfill, *args, **kwargs)


class _Contexto(_Recurso):
    close = _comando('close')
    new_page = _comando('new_page', _Pagina)
    add_cookies = _comando('add_cookies')
    cookies = _comando('cookies')

    set_default_timeout = _comando('set_default_timeout')

    on = _comando('on')

    def route(self, padrao, callback):
        async def tratar(rota):
            decisao = _DecisaoRota(rota)
            try:
                callback(decisao)
            except Exception:
                await rota.abort()
                raise
            await decisao.acao()

        self._loop.run(self._objeto.route(padrao, tratar))


class _Navegador(_Recurso):
    close = _comando('close')
    new_context = _comando('new_context', _Contexto)

    def is_connected(self):
        return self._objeto.is_connected()


class _Chromium(_Recurso):
    launch = _comando('launch', _Navegador)


class Sessao:
    """Mantém scanner e Playwright na mesma thread, com um loop por varredura."""
    def __init__(self, loop, playwright):
        self._loop = loop
        self.chromium = _Chromium(loop, playwright.chromium)

    def navegar_par(self, paginas, urls, bases, ambientes, parar, metricas, eventos):
        from .navigation_async import navegar_par
        return self._loop.run(navegar_par(
            tuple(p._objeto for p in paginas), urls, bases, ambientes, parar, metricas, eventos
        ))


@contextmanager
def playwright_assincrono():
    with asyncio.Runner() as loop:
        playwright = loop.run(async_playwright().start())
        try:
            yield Sessao(loop, playwright)
        finally:
            loop.run(playwright.stop())
