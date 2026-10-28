---
name: ambidiff-otimizacao
description: Analisar gargalos e propostas de desempenho do AmbiDiff com métricas por fase e comparação controlada de cobertura, sem ocultar verificações, falhas ou trabalho pendente.
---

# Desempenho com cobertura auditável

Use para investigar lentidão, requisições redundantes, cache, descoberta ou fila.
Siga os contratos e limites comuns do `AGENTS.md`; não use esta Skill em tarefas
meramente documentais nem rode benchmarks automaticamente por sua disponibilidade.

1. Defina o cenário e um baseline reproduzível. Consulte métricas já existentes
   antes de instrumentar: navegação, preparação/espera, extração, comparação,
   evidências, recuperação e checkpoints. Não some fases aninhadas.
2. Examine só os gargalos demonstrados: requisições/visitas duplicadas, descoberta,
   filas, releituras e gravação. Avalie cache/reaproveitamento somente com evidência
   suficiente de equivalência, isolamento e validade do estado; título ou aparência
   semelhante não comprovam equivalência de página.
3. Proponha uma alteração pequena com hipótese mensurável, regressões necessárias,
   riscos de cobertura e critérios para mantê-la ou descartá-la. Implemente apenas
   dentro do escopo autorizado.
4. Compare antes/depois nas mesmas condições, com repetições quando úteis e sem
   concorrência de outras cargas de teste que distorçam os tempos. Use fixtures e
   scripts pertinentes de `scripts/`; portais reais exigem autorização específica.
5. Compare também admitidos, efetivamente comparados, inconclusivos, falhos,
   pendentes, evidências e verificações realizadas. Uma versão que encerra mais
   cedo com trabalho perdido não demonstrou ganho de desempenho.
6. Confirme as regressões de qualidade relacionadas, incluindo ÁUDIOS e separação
   editorial/estrutural quando afetadas; reaproveite a Skill de validação se útil.

Entrega: gargalo medido, proposta/alteração, condições, tempos e cobertura de
ambas as versões, ganho/perda observado e limitações. Não estime ganhos sem
medição nem prometa mil pares em 1h30: é objetivo, não garantia ou prazo global.
