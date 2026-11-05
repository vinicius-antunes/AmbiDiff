# AmbiDiff Next

Projeto independente na raiz desta branch, que contém apenas o Next. Não
importar módulos do AmbiDiff legado em produção nem modificar seus arquivos.
Para benchmark comparativo, aceitar somente outra cópia local explicitamente
configurada por `AMBIDIFF_LEGACY_PATH`. A autorização desta tarefa permite
arquitetura própria, amostragem explícita e limite de capacidade configurável;
o teto fixo e a proibição de reescrita do legado não são contratos deste programa.
Segurança, bidirecionalidade, ÁUDIOS, evidências reais e preservação de parciais
continuam obrigatórios. Dados de execução ficam em data/ (ignorado pelo Git).

Com o venv ativo: `python -m pip install -r requirements-dev.txt`,
`python -m playwright install chromium`, `python -m pytest tests -q`,
`node --check ambidiff_next/static/app.js`, `python -m ambidiff_next`.
Somente fixtures locais em testes/benchmarks; INDEA e SEMA exigem autorização
futura. Ganho experimental alvo de 30–50% não é resultado comprovado e depende
preservar cobertura funcional, precisão e recall nas mesmas fixtures.
