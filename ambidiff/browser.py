"""Recursos do Chromium oculto: recuperação limitada, sem partilhar sessões."""
import shutil


def fechado(erro):
    texto=str(erro).lower()
    return any(t in texto for t in ('target closed','browser has been closed','target page, context or browser has been closed'))


class Navegador:
    MAX_RECUPERACOES=3
    def __init__(self,pw,configurar,preparar=None,diagnostico=None):
        self.pw=pw;self.configurar=configurar;self.preparar=preparar
        self.diagnostico=diagnostico or (lambda _:None)
        self.browser=None;self.contextos=[None,None];self.paginas=[None,None]
        self.contextos_fechados=[False,False];self.recuperacoes=0;self.limpando=False
    def _fechar(self,obj,tipo):
        if obj is None:return
        try:obj.close()
        except Exception as ex:self.diagnostico({'tipo':'LIMPEZA_RECURSO','recurso':tipo,'erro':type(ex).__name__,'resultado':'Limpeza continuou; erro original preservado'})
    def iniciar(self):
        try:self.browser=self.pw.chromium.launch(headless=True)
        except Exception:
            executable=shutil.which('chromium') or shutil.which('chromium-browser')
            if not executable:raise
            self.browser=self.pw.chromium.launch(headless=True,executable_path=executable,args=['--no-sandbox'])
        self._contexto(0);self._contexto(1)
        if self.preparar:self.preparar(*self.contextos)
    def _contexto(self,lado):
        self._fechar(self.contextos[lado],'contexto')
        ctx=self.browser.new_context(locale='pt-BR',viewport={'width':1366,'height':850},service_workers='block',accept_downloads=False)
        self.contextos[lado]=ctx;self.contextos_fechados[lado]=False
        def fechado_ctx(*_):
            if self.contextos[lado] is ctx:self.contextos_fechados[lado]=True
        ctx.on('close',fechado_ctx);self.configurar(ctx)
        if hasattr(ctx,'set_default_timeout'):ctx.set_default_timeout(12000)
        self.paginas[lado]=ctx.new_page()
    def estado(self,lado=None):
        def observar(obj,metodo):
            try:return getattr(obj,metodo)()
            except Exception:return None
        return {'navegador_conectado':observar(self.browser,'is_connected'),
                'contextos_fechados':list(self.contextos_fechados),
                'paginas_fechadas':[observar(p,'is_closed') for p in self.paginas],
                'ambiente_indice':lado,'limpeza_solicitada':self.limpando}
    def recuperar(self,lado=None):
        if self.recuperacoes>=self.MAX_RECUPERACOES:raise RuntimeError('Limite de três recuperações de recursos; checkpoint preservado para retomada.')
        self.recuperacoes+=1
        antes=self.estado(lado)
        if antes['navegador_conectado'] is False:
            for ctx in self.contextos:self._fechar(ctx,'contexto')
            self._fechar(self.browser,'navegador');self.contextos=[None,None]
            self.iniciar();nivel='navegador'
        else:
            for i in ((lado,) if lado is not None else (0,1)):
                page=self.paginas[i]
                if self.contextos_fechados[i]:self._contexto(i)
                else:
                    self._fechar(page,'página');self.paginas[i]=self.contextos[i].new_page()
            if self.preparar:self.preparar(*self.contextos)
            nivel='página/contexto'
        self.diagnostico({'tipo':'RECUPERACAO_RECURSOS','tentativa':self.recuperacoes,'nivel':nivel,'estado_anterior':antes,'resultado':'Novos recursos; nenhum par concluído foi descartado'})
    def fechar(self):
        self.limpando=True
        for ctx in self.contextos:self._fechar(ctx,'contexto')
        self._fechar(self.browser,'navegador')
