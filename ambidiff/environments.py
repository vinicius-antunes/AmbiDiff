"""Identidade por posição, independente do tipo PRD, sem alterar o comparador."""


def identificar(a,b,desatualizado=''):
    if (a in ('PRD_A','PRD_B') or b in ('PRD_A','PRD_B')) and (a,b)!=('PRD_A','PRD_B'):
        raise ValueError('Identificadores PRD incompatíveis com os lados A e B.')
    if a==b:
        if a!='PRD':raise ValueError('Use nomes de ambientes diferentes; somente PRD × PRD é permitido.')
        a,b='PRD_A','PRD_B'
    if desatualizado in ('A','B'):desatualizado=a if desatualizado=='A' else b
    if desatualizado not in ('',a,b):
        raise ValueError('Escolha um ambiente válido para a base desatualizada; PRD isolado é ambíguo em PRD × PRD.')
    return a,b,desatualizado


def metadados(a,b,url_a,url_b):
    if (a,b)!=('PRD_A','PRD_B'):return {}
    return {campo:{'identificador':identificador,'tipo':'PRD','posicao':lado,
                   'funcao':funcao,'url':url,'rotulo':rotulo}
        for campo,identificador,lado,funcao,url,rotulo in (
            ('ambiente_a',a,'A','base',url_a,'PRD (A) — Base'),
            ('ambiente_b',b,'B','comparado',url_b,'PRD (B) — Comparado'))}


def identidades(dados):
    nomes=list(dados.get('ambientes',{}))
    if set(nomes)=={'PRD_A','PRD_B'}:
        return metadados('PRD_A','PRD_B',dados['ambientes']['PRD_A'],dados['ambientes']['PRD_B'])
    return {}


def rotulo(nome,dados):
    if not isinstance(nome,str):return nome
    labels={m['identificador']:m['rotulo'] for m in identidades(dados).values()}
    return ' / '.join(labels.get(n,n) for n in nome.split(' / '))
