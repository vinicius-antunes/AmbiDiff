"""Conversor interno invocado por subprocesso, sem carregar sites ou scripts."""
from pathlib import Path
import shutil
import sys


def converter(source,dest):
    from playwright.sync_api import sync_playwright
    html=Path(source).read_text(encoding='utf-8').replace('<details','<details open')
    html=html.replace('</head>','<style>'+'@page{size:A4;margin:16mm}body{max-width:100%;padding:0;font-size:10pt}article{break-inside:avoid}.copy-id,#search-div,label[for="search-div"]{display:none}img{max-height:240px}pre{white-space:pre-wrap;overflow-wrap:anywhere}'+'</style></head>')
    with sync_playwright() as pw:
        try:browser=pw.chromium.launch(headless=True)
        except Exception:
            exe=shutil.which('chromium') or shutil.which('chromium-browser')
            if not exe:raise
            browser=pw.chromium.launch(headless=True,executable_path=exe,args=['--no-sandbox'])
        try:
            ctx=browser.new_context(java_script_enabled=False,service_workers='block',accept_downloads=False)
            ctx.route('**/*',lambda route:route.abort())
            page=ctx.new_page();page.set_content(html,wait_until='load',timeout=15000)

            page.pdf(path=dest,format='A4',print_background=True,display_header_footer=True,
                header_template='<span style="font-size:8px;margin-left:16mm">AmbiDiff — relatório local</span>',
                footer_template='<span style="font-size:8px;margin-left:16mm">Página <span class="pageNumber"></span> de <span class="totalPages"></span></span>')
        finally:browser.close()


if __name__=='__main__':converter(sys.argv[1],sys.argv[2])
