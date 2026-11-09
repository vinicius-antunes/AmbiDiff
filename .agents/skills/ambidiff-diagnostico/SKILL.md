---
name: ambidiff-diagnostico
description: Investigar erros, interrupções, resultados inconclusivos e regressões do AmbiDiff, comparando comportamento esperado, evidências e versões antes de propor uma correção mínima.
---

# Diagnóstico de erros e regressões

Use quando o pedido for investigar, por exemplo: “por que a varredura parou?”,
“o que mudou no último commit?”, “analise Target closed” ou “investigue os
inconclusivos da POLITEC”. Siga as regras comuns do `AGENTS.md` da raiz.

1. Descreva o comportamento relatado, o esperado e a versão efetivamente usada.
2. Examine somente logs, JSONs, checkpoints e capturas disponibilizados localmente
   e necessários ao caso. Informe evidências ausentes; não exija outra varredura
   longa para iniciar uma reprodução pequena.
3. Localize o fluxo responsável. Para navegação/recursos, comece por `browser.py`,
   `navigation.py` e `paired.py`; para progresso/recuperação, `execution.py`,
   `checkpoints.py`, `diagnostics.py` e `web/server.py`, todos nos diretórios atuais.
   Leia testes relacionados antes de expandir a investigação.
4. Se houver suspeita de regressão, compare os commits relevantes com o HEAD atual.
   Diferencie alteração responsável comprovada de mera coincidência temporal.
5. Reproduza com fixture local e falha controlada quando possível. Separe problema
   de acesso/site, dados editoriais e automação; registre impacto, evidência,
   hipótese, confiança e o que falta para confirmar a causa.
6. Proponha a menor correção e o teste que a comprovaria. Se o pedido for somente
   diagnóstico, apresente o resultado e solicite autorização antes de implementar;
   se a correção já estiver autorizada, siga esse escopo sem reconfirmar.
7. Preserve arquivos originais e resultados parciais; analise cópias/projeções.

Entrega curta: sintomas, causas confirmadas, hipóteses, reprodução/testes,
correção recomendada e limites. Não atribua causas comprovadas a INTERMAT ou
POLITEC sem evidência do caso. Esta Skill não inicia acessos aos portais.
