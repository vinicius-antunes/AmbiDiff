"""Prontidão visual e enquadramento das capturas no Chromium."""
import math
import time


JS_ESTADO_VISUAL = r'''() => {
    if (!window.__ambidiffCaptura) {
        const state = {versao: 0};
        const observer = new MutationObserver(() => state.versao++);
        observer.observe(document.documentElement, {
            subtree: true, childList: true, characterData: true, attributes: true
        });
        window.__ambidiffCaptura = state;
    }
    const pendentes = [...document.images].some(img => {
        if (img.complete) return false;
        if (img.loading !== 'lazy') return true;
        const box = img.getBoundingClientRect();
        return box.bottom > 0 && box.top < innerHeight && box.right > 0 && box.left < innerWidth;
    });
    const ocupado = !!document.querySelector('[aria-busy="true"],[role="progressbar"]');
    const dinamico = !!(document.scripts.length || document.getAnimations().length ||
        document.querySelector('iframe,frame,object,embed,video,canvas,animate,animateTransform,' +
            '[loading="lazy"],[data-src],[data-lazy-src],[role="tab"],[data-bs-toggle="tab"],' +
            '[onload],[onerror],[onscroll],meta[http-equiv="refresh" i]'));
    return {
        pronto: document.readyState === 'complete' && !pendentes && !ocupado &&
                document.fonts.status === 'loaded',
        dinamico,
        documento: performance.timeOrigin,
        versao: window.__ambidiffCaptura.versao,
        largura: innerWidth,
        altura: innerHeight,
        documento_altura: document.scrollingElement?.scrollHeight ?? document.documentElement.scrollHeight,
        escala: devicePixelRatio
    };
}'''

JS_ENQUADRAR = r'''y => {
    document.querySelectorAll('[data-ambidiff-outline]').forEach(el => {
        el.style.outline = el.dataset.ambidiffOutline;
        el.style.outlineOffset = el.dataset.ambidiffOffset;
        delete el.dataset.ambidiffOutline;
        delete el.dataset.ambidiffOffset;
    });
    if (window.scrollY !== y || window.scrollX !== 0)
        window.scrollTo({top: y, left: 0, behavior: 'instant'});
}'''


def estado_visual(page):
    return page.evaluate(JS_ESTADO_VISUAL)


def aguardar_visual(page, parar, *, alvo=None, janela_dinamica_ms=450, limite_ms=1500):
    """Espera recursos observáveis e preserva a janela de páginas dinâmicas."""
    inicio = time.monotonic()
    dinamico = False
    while not parar.is_set():
        estado = estado_visual(page)
        dinamico = dinamico or estado['dinamico']
        decorrido = (time.monotonic() - inicio) * 1000
        faltam = janela_dinamica_ms - decorrido if dinamico else 0
        if decorrido >= limite_ms:
            return estado
        if estado['pronto'] and faltam <= 0 and (not dinamico or alvo is None or alvo.is_visible()):
            return estado
        intervalo = min(75, limite_ms - decorrido)
        if estado['pronto'] and faltam > 0:
            intervalo = min(intervalo, faltam)
        page.wait_for_timeout(max(1, math.ceil(intervalo)))
    return None
