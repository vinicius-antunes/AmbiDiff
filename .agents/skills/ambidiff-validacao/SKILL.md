---
name: ambidiff-validacao
description: Planejar e executar testes locais e revisão de alterações do AmbiDiff, selecionando regressões pertinentes e distinguindo simulações, verificações não executadas e validação real autorizada.
---

# Validação e prevenção de regressões

Use ao validar uma correção, preparar uma entrega ou revisar riscos de regressão.
Siga o `AGENTS.md` para comandos, segurança e contratos; não copie a suíte nem
crie testes que apenas reproduzam a implementação.

1. Examine o diff e identifique os contratos afetados e os testes existentes.
2. Rode primeiro o arquivo/caso direcionado com `unittest`. Adicione ou ajuste
   regressões pequenas para comportamentos importantes, preservando asserções
   válidas. Não remova testes para obter aprovação.
3. Execute a suíte completa quando o alcance justificar e nas entregas que a
   exigirem. Em mudanças documentais, prefira estrutura, metadados e diff, salvo
   exigência explícita de suíte completa. Não rode benchmarks irrelevantes.
4. Priorize conforme o risco: ÁUDIOS; editorial versus estrutural; teto HTML e
   drenagem; Chromium oculto/recuperação/isolamento; interrupção/checkpoint;
   progresso/falhas da automação; JSON/CSV/HTML/PDF e evidências; HOMOL em B e
   relatórios legados. Localize os casos em `tests/`, especialmente `test_update19`,
   `test_update18`, `test_update12`, `test_smart`, `test_progress` e `test_perf`.
5. Para JavaScript, use também `node --check web/static/app.js`. Revise escopo e
   arquivos sensíveis com Git; valide configurações novas com ferramentas disponíveis.
6. Em falha, conserve a saída, diagnostique e corrija apenas no escopo autorizado.
   Se depender de mudança funcional não autorizada, pare essa expansão e informe
   o impedimento. Não transforme skip ou recurso indisponível em aprovação.

Entrega: comandos, quantidades/resultados, falhas corrigidas, verificações não
executadas, limites de ambiente e revisão do diff. Simulação, Chromium loopback,
Windows e portal institucional são evidências distintas; nunca declare uma pelas
outras. Consulte `docs/manutencao-ia.md` para CI e manutenção das instruções.
