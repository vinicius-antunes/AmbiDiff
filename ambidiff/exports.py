"""Nomes públicos do download e conversão PDF exclusivamente local."""
from datetime import datetime
from pathlib import Path
import re
import subprocess
import sys
import unicodedata


def nome_amigavel(site,ext,escopo,run_id):
    texto=unicodedata.normalize('NFKD',re.sub(r'https?://\S+|\S+@\S+|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b','',str(site or 'Portal'))).encode('ascii','ignore').decode()
    texto=re.sub(r'\b\d{11,}\b','identificador',texto)
    texto=re.sub(r'[^A-Za-z0-9_-]+','_',texto).strip('_. ')[:64] or 'Portal'
    if texto.upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(10)],*[f'LPT{i}' for i in range(10)]}:texto='Portal_'+texto
    tipo='Diagnostico' if ext.startswith('diagnostico-') else 'DIVs_Selecionadas' if escopo=='selecionadas' else 'Comparacao'
    try:data=datetime.strptime(run_id[:8],'%Y%m%d').date().isoformat()
    except ValueError:data=datetime.now().date().isoformat()
    sufixo=re.sub('[^a-f0-9]','',run_id[-6:]) or 'local'
    return f'{texto}_{tipo}_{data}_{sufixo}.{ext.split("-")[-1]}'


def gerar_pdf(html_path,pdf_path):
    # Processo separado também funciona quando o chamador já usa Playwright.
    root=Path(__file__).resolve().parents[1]
    try:
        result=subprocess.run([sys.executable,'-B','-m','ambidiff.pdfexport',str(html_path),str(pdf_path)],cwd=root,capture_output=True,text=True,timeout=60)
        if result.returncode:raise RuntimeError('Não foi possível gerar PDF local. Confira a instalação do Chromium/Playwright.')
    except subprocess.TimeoutExpired as exc:
        Path(pdf_path).unlink(missing_ok=True)
        raise RuntimeError('Conversão PDF excedeu 60 segundos; HTML e dados originais preservados.') from exc
