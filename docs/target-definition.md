<!--
Authority: canonical long-term target and convergence contract.
This document is not a claim about current implementation.
Current product claims must remain bounded by reproducible evidence.
-->

007 FRAMEWORK — MASTER PROMPT CANÔNICO

Evidence-First · Continuous Online Learning · Certified Runtime · Durable Code

Você está trabalhando no 007 Framework.

Este documento é simultaneamente:

1. definição-alvo do produto;
2. conjunto de invariantes arquiteturais;
3. contrato de validação;
4. regra de priorização;
5. plano de convergência do código atual.

Não trate cada seção como requisito para implementar imediatamente.

Essa distinção é fundamental.

O 007 tem uma visão arquitetural de longo prazo, mas sua implementação deve ser evidence-gated:

nenhum subsistema novo deve ser construído antes de existir evidência de que ele resolve um problema necessário para provar ou melhorar a tese central do framework.

O próprio 007 deve obedecer:

Use the minimum intelligence necessary. Prove the result.

E também:

Use the minimum framework complexity necessary. Prove that additional complexity buys something.

⸻

1. Objetivo fundamental

007 is an evidence-driven, headless control plane for agentic software engineering that sits above user-selected coding harnesses and continuously learns which certified execution strategy delivers the minimum sufficient intelligence for a task and codebase, subject to hard correctness and durability constraints.

O framework deve ser:

* model-agnostic;
* provider-agnostic;
* harness/agent-agnostic;
* UI-agnostic;
* language-agnostic na arquitetura;
* architecture-agnostic;
* local-first;
* auditable;
* reproducible;
* economical;
* incremental.

O objetivo é minimizar:

expected cost per accepted durable task
expected latency per accepted durable task
unnecessary complexity

sujeito a:

correctness
regression safety
required security
required performance
architecture invariants
durability constraints

⸻

2. O 007 não é um coding harness

Esta boundary é explícita.

O 007 pode executar e governar um CLI/harness externo como subprocesso:

Claude Code
Codex
Cline
Goose
OpenHands
future coding agent

Mas não deve alegar automaticamente que controla o interior desse harness.

O 007 normalmente governa:

task
route/policy eligibility
agent invocation
requested model/provider/effort
budgets
authority
runtime health
fallback
acceptance commands
evidence
cost
latency
post-execution gates
learning

O harness pode continuar controlando internamente:

context management
compaction
tool loop
subagents
internal retries
internal planning
prompt construction
memory

salvo quando um adapter específico expõe essas capacidades de maneira verificável.

Portanto:

007 governs the execution boundary, not necessarily the internal reasoning loop of the harness.

Nunca faça claim maior que isso.

⸻

3. A tese precisa ser provada antes da governança completa

A hipótese central do produto é:

para classes reais de tarefas de software, uma política que emprega apenas a inteligência necessária pode reduzir custo e/ou latência por task aceita sem produzir correctness ou durability materialmente inferiores às obtidas com uma política mais cara.

Essa hipótese ainda não deve ser considerada provada apenas porque o controller, selector ou dashboard funcionam.

Um selector sobre receipts sintéticos não prova a tese.

Um controller que bloqueia ações corretamente não prova a tese.

Um ROI agregado sem fontes reproduzíveis não prova a tese.

Logo, a primeira prioridade é um experimento real mínimo.

⸻

4. Phase Zero — Thesis Test

Antes de construir subsistemas amplos de governance, execute um experimento causal pequeno e reproduzível.

Comece com:

1 real repository
1 task class
2 execution policies
multiple real tasks
multiple independent executions
real model calls
real deterministic acceptance
verified served model

Não use uma única task repetida 30 vezes como única evidência de uma classe.

Isso mede variance daquela task, não generalização da policy.

Preferência inicial:

8–12 tasks reais suficientemente comparáveis
×
~3 independent runs per policy/task

produzindo aproximadamente:

24–36 executions per arm

Ajuste apenas se custo justificar.

Não ancore no número se a análise estatística mostrar outra necessidade.

⸻

5. O experimento inicial deve responder somente

Does the cheaper/faster policy produce
non-inferior accepted-task outcomes
for this task class,
on this repository,
under these acceptance criteria?

Métricas mínimas:

first-pass acceptance
final acceptance
escapes
retries
model cost
wall-clock latency
diff size
dependency delta
deterministically measurable D0

e pelo menos um proxy estrutural de durabilidade que seja realmente mensurável.

Defina antes:

hypothesis
control
treatment
acceptance commands
non-inferiority margin
kill criterion
required provenance

Se a hipótese falhar:

não construa mais governance para protegê-la.

Investigue a causa ou altere a tese.

⸻

6. Evidence before architecture

A regra geral é:

hypothesis
→ minimal measurement
→ evidence
→ architectural necessity
→ implementation

e não:

canonical architecture
→ dozens of subsystems
→ someday measure whether they matter

Toda proposta de novo componente deve responder:

1. qual failure mode real resolve?
2. temos evidência desse failure mode?
3. é necessário para o próximo experimento?
4. existe solução menor?
5. já existe ferramenta externa madura que podemos reutilizar?
6. o componente reduz ou aumenta a superfície de prova?

Se não houver resposta convincente:

DO NOT BUILD.

⸻

7. Execution Policy e Selection Policy são entidades distintas

Não reduzir o sistema a:

task → model

Nem a:

task → route

Execution Policy

Representa uma estratégia certificável de execução.

Uma policy pode incluir:

policy_id
eligible task classes
eligible impact profiles
agent/harness
agent version
model
provider
reasoning effort
invocation contract
required acceptance commands
budgets
fallbacks
recovery
required evidence

Não exija imediatamente um workflow DSL genérico.

Uma policy inicial simples pode ser:

inspect
→ invoke one coding harness
→ deterministic gates

Se nenhuma evidência exigir DAGs, stages arbitrários ou orchestration graphs:

DO NOT BUILD THEM.

⸻

8. Selection Policy

Selection Policy define como escolher entre Execution Policies certificadas.

Ela pode usar:

current task facts
repository facts
impact profile
current provider availability
current provider health
current pricing
repository-local learned state
global prior where allowed
user constraints

O algoritmo de seleção precisa ser:

versioned
auditable
reproducible
bounded by the release

⸻

9. Certified Policy Envelope

Toda release define explicitamente um envelope permitido.

Exemplo conceitual:

007 release R
selector = S
approved execution policies:
P1
P2
P3
approved fallback graph:
P1 → P2
P2 → P3
hard gates:
G1
G2
G3
learning algorithm:
L
health/circuit-breaker rules:
H

Runtime só pode operar dentro desse envelope.

Runtime pode decidir:

P1 today
P2 tomorrow

Runtime não pode inventar:

P99

ou executar modelo/harness não certificado simplesmente porque parece promissor.

⸻

10. Continuous Online Learning é parte do objetivo

Não implemente um sistema totalmente estático se os dados justificarem adaptação.

O 007 deve poder aprender continuamente:

execution
→ validated evidence
→ learned-state update
→ better future selection

A adaptação online é permitida entre policies previamente certificadas.

Regra:

Runtime may learn which certified strategy works better in the observed context. Runtime may not invent a new strategy.

Ou:

Learn online. Innovate offline.

⸻

11. Dois loops de evolução

Existem dois loops distintos.

FAST LOOP — Runtime calibration

task
→ approved policy
→ execution
→ gates
→ evidence
→ deterministic learned-state update
→ future selection changes

Não exige release.

Pode alterar:

estimated success probability
estimated escape probability
cost distribution
latency distribution
repo-local calibration
confidence
preferred certified policy

SLOW LOOP — Structural innovation

observational evidence
→ hypothesis
→ candidate model/policy/selector
→ causal experiment
→ promotion
→ release

Exige validação e versionamento.

Pode alterar:

approved policy envelope
new models
new harnesses
selector algorithm
learning algorithm
gate semantics
fallback structure
task taxonomy semantics

⸻

12. Runtime resilience é diferente de learned optimization

O runtime precisa responder a degradação operacional.

LLM APIs podem apresentar:

latency spikes
timeouts
availability failures
rate limits
provider degradation
unexpected served-model mismatch

Por isso, o Certified Policy Envelope pode definir um Circuit Breaker de Runtime.

Exemplo:

primary = P1
fallback = P2
if:
  provider unavailable
  OR
  timeout rate > threshold
  OR
  recent latency > certified threshold
then:
  temporarily mark P1 unhealthy
  use P2

Isso não é criação de policy.

É execução de uma regra de resiliência previamente certificada.

⸻

13. Circuit breaker precisa ser bounded

Os seguintes elementos são definidos pela release:

health signals
window size
threshold
fallback candidates
cooldown
hysteresis
recovery rule

Runtime pode atualizar:

current health state

Não pode mudar:

threshold semantics
fallback graph
window algorithm

silenciosamente.

Evite route flapping.

Use:

hysteresis
cooldown
minimum sample requirements

quando necessários.

⸻

14. Health state não é durability learning

Mantenha conceitos separados.

provider A is currently slow

é current health.

P1 historically produces durable code on Repo X

é learned evidence.

Não misture os dois numa única métrica obscura.

O decision record deve permitir distinguir:

selection due to learned quality

de:

fallback due to current runtime health

⸻

15. Quality before economics

Nunca faça:

70% reliable
5% escape
→ cheapest
→ winner

apenas porque passou thresholds frouxos.

A policy deve primeiro ser considerada quality-qualified para o contexto.

Só depois:

minimize expected cost
then latency

Não use weighted score simples para compensar qualidade com preço.

⸻

16. Confidence-aware selection

Evidence escassa não equivale a reliability comprovada.

5 successes / 5

não significa:

100% reliable

Use método simples, determinístico e documentado.

Exemplos:

Wilson interval
Beta-Binomial

Não implemente ML sofisticado sem evidence de necessidade.

Uma policy pode ser QUALITY_QUALIFIED somente quando os confidence bounds satisfizerem os requisitos certificados.

⸻

17. Estados mínimos de eligibility

Distinguir:

QUALIFIED
INSUFFICIENT_EVIDENCE
DISQUALIFIED
INCOMPATIBLE
UNAVAILABLE
UNHEALTHY

Não confundir pouca evidência com failure.

Não confundir provider outage com baixa qualidade.

⸻

18. Online learning não pode expandir o envelope

Mesmo se receipts observacionais indicarem:

P99
1000/1000 successes
$0 cost

se P99 não está no certified envelope:

P99 CANNOT SERVE.

Observational evidence pode gerar:

candidate proposal

não:

automatic certification

⸻

19. Natural evidence primeiro

Não introduza exploration randômica por default.

Prefira aprender através de:

normal serving
natural retries
fallbacks
recovery
longitudinal outcomes

Se duas policies certificadas forem executadas naturalmente em contextos comparáveis, isso gera evidência útil.

⸻

20. Shadow execution é opcional, não core requirement inicial

Quando existir vantagem comprovável e budget explícito:

serving = P1
shadow = P2

Shadow deve rodar isolado e nunca modificar o working tree real.

Mas:

NO SHADOW INFRASTRUCTURE

até existir evidence de que a falta de counterfactual data está impedindo aprendizagem relevante.

⸻

21. Task taxonomy deve ser evidence-driven

Não implemente uma lista extensa de task classes apenas porque parece semanticamente completa.

Comece com as classes atuais ou uma decomposição mínima melhor.

Só separe uma classe quando houver evidência de que:

the winning policy differs materially inside the class

Por exemplo, se implement contém dois grupos:

A → Pcheap dominates
B → Pstrong required

há evidência para split.

Sem isso:

KEEP IT SIMPLE.

⸻

22. Não usar AST impact como única task taxonomy

Categorias como:

READ_ONLY
SOURCE_MUTATING
DEPENDENCY_ALTERING

são úteis.

Mas representam impact profile, não necessariamente task semantics.

Um bugfix e um architectural refactor podem ambos ser SOURCE_MUTATING e ainda exigir policies radicalmente diferentes.

Portanto separar:

task_class

de:

impact_profile

Exemplo:

task_class = implement
impact = SOURCE_MUTATING

ou:

task_class = deep
impact = SOURCE_MUTATING + CROSS_CUTTING

Só adicione dimensões adicionais quando evidence justificar.

⸻

23. D0 determinístico é necessário para claims fortes

Uma policy não pode ser promovida com claim:

durability non-inferior

se não existe qualquer medida determinística relevante de D0.

Entretanto:

não torne um analisador AST universal obrigatório apenas para poder preencher um campo.

Isso criaria complexidade antes de provar valor.

⸻

24. Estratégia de medição D0 em camadas

Preferência:

Layer 1 — Existing deterministic repo-native evidence

tests
compiler
type checker
lint
static analysis
security checks
benchmarks
dependency checks

Layer 2 — Cheap language-independent deltas

files changed
LOC delta
dependency manifest delta
test delta
file creation/deletion
diff size

Layer 3 — Optional language-aware analyzers

Quando necessário e economicamente justificado:

AST complexity
duplication
abstraction delta
structural metrics

Podem usar adapters/tooling externo apropriado.

Tree-sitter é uma possibilidade, não um requisito arquitetural.

⸻

25. Regra para N/D

N/D continua válido como declaração de honestidade.

Mas há diferença entre:

execution may proceed

e:

strong durability claim may be made

Uma task pode executar com determinada métrica em N/D.

Porém:

uma policy não pode ser promovida com uma claim cuja variável essencial ficou N/D.

Exemplo:

D0 complexity = N/D

pode permitir executar.

Mas se o experimento pretende provar:

structural complexity non-inferior

a célula não possui evidence suficiente para essa conclusão.

⸻

26. Não transformar complexity em pseudo-durability

Cyclomatic complexity sozinha não prova durability.

AST abstraction count sozinha não prova overengineering.

LOC sozinha não prova qualidade.

Use várias evidências ortogonais quando possível.

A claim deve ser proporcional às métricas realmente observadas.

⸻

27. Dt continua essencial

Immediate D0 não substitui durability longitudinal.

Observe quando disponível:

reverts
corrective commits
follow-up defects
hotfixes
incidents
corrective churn
time to first repair
future-agent rework

Distinguir:

EVOLUTION
CORRECTIVE
UNKNOWN

Nunca classifique qualquer modificação futura como defeito da implementação anterior.

⸻

28. Dt não deve bloquear todo release

Não espere 30 dias para corrigir qualquer bug no framework.

Separar:

release correctness claim

de:

longitudinal durability maturity

Uma versão pode ser tecnicamente stable no contrato de runtime e carregar:

longitudinal_evidence_maturity = D0 / D7 / D30

Claims longitudinais maiores exigem maturidade correspondente.

⸻

29. Deterministic enforcement

A diferença entre testemunho e evidência precisa ser eliminada.

Um receipt contendo:

checks = ["tests passed"]

porque o adapter declarou isso não é prova.

O controller deve executar ou verificar os acceptance commands e registrar:

command
working directory
exit code
duration
stdout/stderr digest where appropriate

Se um hard gate obrigatório falhar:

accepted = false

independentemente do que o agent declarar.

⸻

30. Served identity é um hard experimental gate

Para qualquer causal experiment envolvendo:

model
provider
effort
harness

a identidade realmente servida precisa ser verificável.

Se:

requested_model = X
served_model = unmeasured

então uma conclusão causal sobre X não é válida.

Resultado:

EXPERIMENT CELL INVALID

ou:

CLAIM MUST BE DOWNGRADED

dependendo da hipótese.

Nunca fingir que requested = served.

⸻

31. Requested vs served deve permanecer separado no runtime

Continue registrando:

requested
served

independentemente.

Se um provider não permitir comprovar served identity:

served = N/D

Isso pode ser aceitável para uso normal dependendo da policy.

Mas limita claims experimentais.

⸻

32. Evidence Bundle mínimo

Não implemente imediatamente um schema gigantesco.

Para a próxima versão, o bundle precisa conter apenas o que é necessário para:

reproduce decision
verify execution
verify gates
measure economics
update learned state
run next experiment

Mínimo sugerido:

framework/release identity
task identity
task class
impact profile if known
repository identity/fingerprint
policy identity
selector identity
learned-state revision
requested route
served route
attempts
acceptance commands + exit codes
cost + provenance
latency
basic D0
outcome

Adicione campos somente quando uma hipótese real precisar deles.

⸻

33. Raw Evidence e Learned State são diferentes

Evidence é imutável.

Learned state é derivado.

raw receipts
+ matured outcomes
+ learning algorithm version
→ learned state

Deve ser possível reconstruir learned state a partir das fontes autoritativas.

Não deixe um arquivo mutável virar verdade irrecuperável.

⸻

34. Repository-local learning

Não concatene receipts de todos os projetos e assuma transferibilidade.

Aprenda primeiro localmente:

repository
× task class
× policy

Cross-project evidence deve começar como:

prior

não como fato local.

Somente use global evidence quando a Selection Policy definir explicitamente como transferi-la.

⸻

35. Cold start

Sem local history:

certified baseline / prior

deve permitir execução segura.

O framework não pode precisar de 50 receipts para funcionar.

Com evidence crescente:

global prior
→ local calibration

⸻

36. Circuit breaker não deve contaminar learning sem provenance

Se P1 falhou porque:

provider timeout

isso não prova:

P1 produces bad code.

Failure cause precisa ser classificada ao menos em categorias mínimas:

EXECUTION_QUALITY
PROVIDER_AVAILABILITY
PROVIDER_LATENCY
TOOL_FAILURE
GATE_FAILURE
UNKNOWN

Online learning de quality não pode contar indiscriminadamente falhas operacionais como falhas intelectuais.

⸻

37. SSoT de versão

Eliminar version drift.

Criar um único release manifest autoritativo.

README, SKILL, CLI, dashboard e evidence devem derivar sua versão dele ou ser validados contra ele.

Não manter múltiplas strings autoritativas independentes.

⸻

38. Release manifest mínimo

Não transforme release manifest em um registry corporativo gigante.

Comece com:

framework version
selector version/hash
policy registry version/hash
learning algorithm version/hash
receipt schema version/hash
approved policies
hard gates
fallback/circuit-breaker rules

E os hashes necessários.

Expanda somente quando necessário.

⸻

39. Provenance

Antes de construir ledger proprietário, considere compatibilidade com padrões existentes de attestation/provenance.

Não adicione uma grande dependência apenas por isso.

Mas evite inventar uma cadeia conceitualmente incompatível com formatos de supply-chain attestation existentes.

Princípio:

reuse semantics before reinventing mechanisms

⸻

40. Dashboard é observer

Dashboard:

reads
projects
explains

Não é:

controller
selector authority
promotion authority
causal engine

Não priorize features de dashboard enquanto a tese central e o E2E não estiverem provados.

⸻

41. Vendor parsers são adapters

Codex/Claude/Gemini/Kimi-specific parsing não deve definir o core.

Quando possível:

core contract
↓
optional adapter

Não reescreva parsers existentes apenas para pureza arquitetural se eles não estiverem bloqueando o experimento atual.

⸻

42. Runtime E2E alvo

O control plane mínimo precisa eventualmente executar:

task
 ↓
classify enough to select
 ↓
capture current repo facts
 ↓
load certified envelope
 ↓
load learned state
 ↓
apply runtime health
 ↓
resolve eligible policies
 ↓
select
 ↓
execute harness
 ↓
verify served identity where available
 ↓
execute deterministic gates
 ↓
record immutable evidence
 ↓
update learned state

Mas não implemente todas essas caixas antecipadamente.

Implemente apenas o caminho mínimo necessário para o próximo experiment.

⸻

43. A arquitetura é target, não checklist de release

Nunca use:

30 canonical clauses

como justificativa para implementar 30 componentes.

Cada componente deve nascer porque uma evidence gap bloqueia:

correct execution
credible measurement
online learning
causal inference
runtime resilience

Se o sistema continuar correto sem ele:

DEFER.

⸻

44. Current beta claim

Enquanto o E2E completo e a tese econômica não estiverem demonstrados, a descrição pública deve ser honesta.

Algo equivalente a:

007 is a local agentic coding lifecycle, controller, evidence observer and experimental evaluation toolkit evolving toward an evidence-driven coding control plane.

Não publique claims de:

optimal routing
durability superiority
causal ROI
best model selection
universal interoperability

sem evidence reproduzível.

⸻

45. Target definition pode viver separadamente

Mantenha:

docs/target-definition.md

ou equivalente.

Isso documenta ambição.

Não confundir:

TARGET

com:

CURRENT PRODUCT CLAIM

⸻

46. Tagline também é uma claim

Não use publicamente:

Use the minimum intelligence necessary. Prove the result.

como descrição de comportamento comprovado até que exista pelo menos um causal experiment real sustentando a tese central.

Pode existir internamente como design principle.

⸻

47. Ordem corrigida de implementação

Phase 0 — Reverify

Não confie cegamente na auditoria fornecida.

Reverifique:

HEAD
branches
worktrees
version strings
tests
current candidate diff
current receipt behavior
selector behavior
evidence artifacts

Não modifique nada antes de saber o estado atual.

⸻

Phase 1 — Fix evidence truthfulness

Prioridade máxima.

Controller deve executar acceptance commands reais.

Registrar:

command
exit code
result

Bloquear accepted em hard-gate failure.

Preservar requested/served.

Fazer served identity verificável onde o adapter permitir.

Isso transforma receipt de testemunho em evidence.

⸻

Phase 2 — Define one minimal certified experiment

Selecionar:

one repository
one task class
two routes/policies
multiple real tasks
replicates

Criar manifest experimental mínimo.

Não construir taxonomy completa.

Não construir policy engine genérica.

⸻

Phase 3 — Run thesis experiment

Medir:

accepted-task quality
cost
latency
escapes
D0

Executar de forma reproduzível.

Se served identity não puder ser comprovada e isso for variável causal:

invalidate cell.

⸻

Phase 4 — Kill/continue decision

Se cheaper/minimum-intelligence strategy NÃO mostrar evidence útil:

STOP governance expansion.

Investigue tese.

Se mostrar:

CONTINUE.

Documente exatamente qual claim foi suportada.

⸻

Phase 5 — Freeze certified envelope

Somente agora transformar as strategies validadas em policies certificadas.

Runtime não pode executar policy fora do envelope.

⸻

Phase 6 — Minimal online learned state

Implementar apenas estatísticas necessárias para escolha entre as policies certificadas.

Comece simples.

Exemplo:

counts
success
failure
cost
latency
confidence bounds

Não introduza ML.

⸻

Phase 7 — Circuit breaker

Adicionar somente sinais operacionais necessários:

availability
timeouts
latency degradation

Fallbacks precisam já pertencer ao envelope.

⸻

Phase 8 — Repository-local calibration

Impedir contamination cross-project.

Global evidence somente como prior explícito.

⸻

Phase 9 — Version SSoT

Manifest único.

Eliminar drift de README/SKILL/dashboard.

⸻

Phase 10 — E2E integration

Eliminar glue manual:

task
→ select
→ execute
→ gate
→ receipt
→ learn

⸻

Phase 11 — Slow Evolution loop

Só então formalizar:

hypothesis
candidate
experiment
promotion decision
release

com a complexidade mínima.

⸻

Phase 12 — Expand only from evidence

Adicionar:

new task classes
new policies
AST analyzers
shadow mode
richer provenance
more durability metrics

somente quando uma evidence gap concreta justificar.

⸻

48. Constitutional tests

Os seguintes testes são especialmente valiosos.

Evidence is real

Adapter dizer:

tests passed

não basta.

O controller executa o command e observa exit 0.

⸻

Failed gate cannot be overridden economically

cheaper route
+ failed hard gate
→ rejected

sempre.

⸻

Online learning changes certified selection

Com duas policies certificadas:

initial evidence → P2
later valid evidence → P1

é permitido sem version bump.

⸻

Online learning cannot create behavior

P99 outside envelope

nunca é selecionada.

⸻

Circuit breaker works

Se P1 violar health threshold:

P1 temporarily unhealthy
→ approved fallback P2

⸻

Circuit breaker cannot invent fallback

Se P3 não está autorizado:

never select P3.

⸻

Operational failure does not poison quality estimate

Timeout não deve necessariamente contar como bad-code outcome.

⸻

Learned state is reproducible

same authoritative evidence
+ same learning algorithm
→ same learned-state hash

⸻

Invalid evidence cannot update learning

Malformed/untrusted receipt:

reject
state unchanged

⸻

Repository isolation

Evidence de Repo A não muda diretamente decisão de Repo B salvo regra global explicitamente certificada.

⸻

Experiment identity

Quando hipótese depende do modelo:

served model unknown
→ experiment cell invalid

⸻

Version SSoT

Todos os surfaces reportam a versão derivada do mesmo manifest.

⸻

49. Overengineering kill criteria

Pare uma implementação se ela começar a exigir, sem evidence:

database
daemon
scheduler
event bus
distributed coordination
generic DAG engine
new model gateway
new frontend
universal AST framework
complex plugin system
custom provenance ledger
ML-based classifier
bandit infrastructure

Antes de adicionar qualquer um:

prove que o problema atual não pode ser resolvido corretamente com a arquitetura simples existente.

⸻

50. Standards over invention

Quando um problema já possui padrão maduro:

provenance
attestation
policy evaluation
experiment recording

investigue reutilização conceitual ou interoperabilidade antes de inventar formato incompatível.

Mas:

do not add dependencies merely because a standard exists.

Use somente se reduzir complexidade total.

⸻

51. Do not optimize for architecture purity

O objetivo é:

credible durable outcomes

não:

perfect abstraction diagram

Uma solução local feia mas simples e bem testada pode ser melhor que um subsystem genérico elegante e desnecessário.

⸻

52. Do not preserve wrong behavior because it exists

O inverso também vale.

Se o código atual permite:

unbounded live receipts
→ immediate cross-project route mutation

e isso não está dentro de um certified learning contract:

corrija.

Preserve primitives saudáveis, não erros históricos.

⸻

53. Preserve known-good primitives

Preserve salvo evidence em contrário:

atomic/no-replace writes
begin/run/record lifecycle
authority blocking before subprocess
requested vs served distinction
honest N/D/unmeasured
cost provenance
temporary isolated replay
seed/order capture
stop on invalid experiment cell
similarity only as diagnostic
standard-library-first core
SHA-256 manifests
tag-conditioned CI
claim boundaries

⸻

54. Definition of Done — next meaningful milestone

Não use a definição canônica completa como DoD.

O próximo milestone só precisa provar:

A. Real evidence

controller executes gates
receipt records truth

B. Real causal experiment

real repo
real tasks
real models
verified binding
real cost
real latency
real D0

C. Useful thesis result

Alguma evidence reproduzível de que uma lower-intelligence policy:

reduces cost and/or latency
without violating predefined quality constraints

ou uma conclusão honesta de que isso não ocorreu.

D. Claim discipline

Nenhuma claim além do que o experimento realmente prova.

⸻

55. Definition of Done — first actual 007 beta

Depois que a tese sobreviver:

task
→ eligible certified policies
→ online learned-state-aware selection
→ runtime health/circuit breaker
→ execution
→ deterministic gates
→ immutable evidence
→ learned-state update

com:

runtime can adapt inside certified envelope
AND
runtime cannot expand the envelope

⸻

56. Definition of Done — stable

Stable só deve significar que:

runtime contract is coherent
tests are green
release bytes are exact
manifest matches
policy envelope is provenance-bound
learning updates are reproducible
circuit breaker is bounded
hard gates are enforced
supported claims have reproducible evidence

Não use stable como sinônimo de:

all imaginable features implemented.

⸻

57. Required response before implementation

Antes de alterar código, produza um diagnóstico curto contendo:

current verified state
current thesis evidence
minimum experiment we can run
which existing primitives can be reused
which existing behaviors are unsafe or false
smallest sequence of patches
explicit non-goals
kill criteria

Não gere um roadmap de dezenas de componentes.

⸻

58. Required behavior during implementation

Para cada patch:

1. declare qual hipótese/failure ele resolve;
2. escreva ou identifique o teste que demonstra o problema;
3. faça a menor mudança;
4. execute testes;
5. capture evidence;
6. confirme que nenhuma claim maior foi criada;
7. confirme que não introduziu nova dependency ou abstraction sem necessidade;
8. preserve clean rollback.

⸻

59. Final decision rule

Sempre escolha entre duas implementações usando esta ordem:

1. Which one is demonstrably correct?
2. Which one produces stronger evidence?
3. Which one introduces less regression risk?
4. Which one preserves durability better?
5. Which one is simpler?
6. Only then: which one is cheaper/faster to run?

Para seleção de uma já-certified execution policy, após hard quality qualification:

1. quality/confidence constraints
2. current health eligibility
3. expected cost
4. expected latency
5. complexity/operational burden

Não misture essas duas decisões.

⸻

60. North-star metric

A direção econômica do 007 pode ser expressa conceitualmente como:

             successful durable outcomes
------------------------------------------------
expected cost × latency × unnecessary complexity

Não use essa expressão como weighted runtime score.

É uma north-star para comparar sistemas.

Hard quality constraints continuam lexicograficamente superiores.

⸻

61. North-star philosophy

O 007 deve buscar:

the minimum sufficient intelligence, not the maximum available intelligence.

Mas precisa aplicar a mesma disciplina a si próprio:

the minimum sufficient framework, not the maximum imaginable architecture.

⸻

62. Canonical principles

Preserve estas frases como princípios do projeto:

Use the minimum intelligence necessary. Prove the result.

Learn online. Innovate offline.

Adapt inside the certified envelope. Change the envelope only through evidence.

Reasoning may be probabilistic. Enforcement must be deterministic wherever deterministically verifiable.

Observational evidence creates learning and hypotheses. It does not manufacture causal proof.

Requested is not served.

N/D is better than invented certainty.

The smallest correct change is preferred over the most impressive change.

The framework itself must earn every layer of complexity it adds.

⸻

63. Ultimate product definition

The long-term target remains:

007 is an evidence-driven, headless control plane for agentic software engineering. It sits above user-selected coding harnesses, continuously learns from real execution, adapts its choice among causally certified execution policies, responds deterministically to runtime degradation through certified fallbacks, and uses hard verification gates to seek the lowest-cost and lowest-latency strategy that produces correct, non-regressive and durable software. New strategies enter the certified envelope only after reproducible causal validation.

This is the target.

Do not claim the current repository already satisfies it.

Build toward it only as fast as evidence justifies.

⸻

64. Immediate mission

Given the current repository:

Do not attempt to implement this entire document.

Your immediate mission is:

1. Reverify current state.
2. Make evidence trustworthy by executing real gates.
3. Define the smallest reproducible causal experiment.
4. Verify requested versus served identity.
5. Run the experiment on real code/tasks.
6. Decide whether the core 007 thesis survives.
7. Only then implement the minimum certified-policy + online-learning machinery justified by the result.

If the thesis fails:

REPORT IT.
DO NOT HIDE IT WITH MORE FRAMEWORK.

If it succeeds:

USE THE EVIDENCE TO DECIDE WHAT TO BUILD NEXT.

The success metric is not how much of this specification gets implemented.

The success metric is:

how much credible evidence the smallest implementation can produce that 007 delivers more durable accepted software per unit of intelligence, money, time and complexity.
