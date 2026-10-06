# Cognitive Virtual Memory — CVM v0.1 (original spec)

*This is the spec the implementation was built from, lightly reformatted.
Implementation notes appear in italics where the code differs or adds something.*

**Status:** experimental architecture.

**Goal:** test whether an LLM can behave as a processor operating inside a
persistent, externally managed cognitive address space, rather than receiving
its world serialized into every prompt.

## 1. Thesis

Conventional LLM systems approximately implement:

    Output = Model(Instruction + WorldState)

CVM instead attempts:

    Output = Model_ContextID(Instruction)

`ContextID` selects a persistent execution environment that contains:

- identity
- object namespace
- permissions
- working memory
- evidence
- external resources

The model does not receive the entire environment. It receives a resident
working set and may explicitly dereference non-resident state.

```
                     Cognitive Process
                            │ instruction/task
                            ▼
                    ┌──────────────┐
                    │ LLM processor│
                    └──────┬───────┘
          READ / TRAVERSE / SEARCH / FAULT / EVIDENCE / WRITE
                           ▼
                  ┌─────────────────┐
                  │   CVM Runtime   │  Context Manager, Resolver, Working Set,
                  │                 │  Capabilities, Provenance
                  └────────┬────────┘
          Graph · Git · Logs · Databases · Files · APIs   (physical world)
```

Architectural principle: **context belongs to the substrate, not the instruction stream.**

## 2. Research question

Can an LLM solve tasks over a world containing N objects while its resident
context remains approximately bounded?

    |WorkingSet| ≪ |World|,   ideally |WorkingSet| ≈ O(task complexity), not O(world size)

The primary experiment is not "does CVM improve RAG?" It is: **can cognitive
working-set size become independent of world size?**

## 3. Core abstractions

Six first-class objects: **Context, Object, Reference, WorkingSet, Capability, Evidence.**

Six initial operations: **READ, TRAVERSE, SEARCH, FAULT, EVIDENCE, WRITE.** V0
can omit WRITE for most experiments.

*Implementation: WRITE is implemented, but only for the context's own
`scratch://` notes. That turned out to be essential (see RESULTS_V0, notes
ablation).*

## 4. Context

A Context is analogous to a process or address space.

```ts
interface CognitiveContext {
  id: ContextID; principal: Principal; task: TaskRef;
  namespaces: NamespaceMount[]; capabilities: Capability[];
  workingSet: WorkingSet; evidencePolicy: EvidencePolicy; parentContext?: ContextID;
}
```

Example: `ctx://8472`, principal `agent://incident-debugger`, task
`task://payment-outage-184`, namespaces `service:// host:// config:// change:// incident://`.

The model never decides its own ContextID. The runtime establishes it.

## 5. Cognitive addresses

Every externally addressable object gets a stable URI of the form
`<namespace>://<stable-id>`. Examples:

- `service://payments`
- `host://prod-17`
- `repo://backend`
- `commit://a8f92d`
- `symbol://backend/PaymentProcessor`
- `incident://184`
- `change://9182`
- `person://alice`
- `claim://redis-capacity-caused-184`
- `memory://deployment-pattern-27`

These are references, not serialized objects. `service://redis-prod` might
represent gigabytes of associated state; the model initially sees only the
handle.

## 6. Object model

```ts
interface CVMObject { ref; type; label?; attributes: Record<string, unknown>;
                      relations: Relation[]; provenance: ProvenanceRef[]; version; }
interface Relation { predicate: RelationType; target: ObjectRef; }
```

Example: `service://payments` has these relations:

- `DEPENDS_ON → service://redis-prod`
- `DEPENDS_ON → service://stripe`
- `OWNED_BY → team://payments`
- `HAS_INCIDENT → incident://184`

## 7. Graph semantics

The graph is the logical address space. It does not have to contain the
physical data. For example:

- `service://redis-prod` has `HAS_CONFIG → config://redis-prod`,
  `HAS_LOGS → logs://redis-prod` and `HAS_METRICS → metrics://redis-prod`.
- `logs://redis-prod` might resolve into Loki.
- `metrics://redis-prod` might resolve into Prometheus.
- `repo://backend` might resolve into Git.

**Graph ≠ Storage. Graph = Address Space.**

## 8. Namespace mounts

The runtime keeps something like a virtual filesystem mount table:
`interface NamespaceMount { prefix: string; resolver: ResolverID; }`.

| Namespace | Resolver |
|---|---|
| `service://`, `host://` | InfrastructureGraphResolver |
| `repo://`, `commit://` | GitResolver |
| `symbol://` | ASTResolver |
| `logs://` | LogResolver |
| `metrics://` | MetricsResolver |
| `incident://` | IncidentResolver |
| `claim://` | EvidenceGraphResolver |
| `memory://` | AgentMemoryResolver |

This lets the cognitive address space span heterogeneous systems.

## 9. Resolver

The resolver is the closest thing in V0 to the MMU.

```ts
interface Resolver { resolve(context: ContextID, reference: ObjectRef, operation: Operation): Promise<MaterializedObject>; }
```

Resolution must always consider **context + reference + operation**, not
merely the reference, because different contexts may have different views of
the same object: `MaterializedState = Resolve(C, Address, Operation)`.

## 10. Cognitive instruction set

Keep V0 extremely small.

- **READ** reads a known property:
  `READ(object=service://redis-prod, field=configuration)` returns
  `VALUE {ref: config://redis-prod/918, value: {...}, provenance: [...]}`.
- **TRAVERSE** follows graph relations:
  `TRAVERSE(object=service://payments, relation=DEPENDS_ON)` returns
  `[service://redis-prod, service://stripe]`. It returns references, not
  necessarily full objects.
- **SEARCH** is discovery when an address isn't known:
  `SEARCH(namespace=change://, query="Redis configuration changes before incident 184")`.
  SEARCH is expensive and imprecise; once an object is discovered, later
  operations should use its stable reference. The path is: semantic discovery
  → stable identity → deterministic dereference.

## 11. FAULT

This is the central experimental primitive.

```ts
interface CognitiveFault { type: "FAULT"; requirement: string; object?: ObjectRef; field?: string; reason: string; }
```

Example: `FAULT {object: config://redis-prod, field: state_at_incident_start,
reason: "Required to determine whether the connection limit preceded the
payment failures."}`.

Runtime behavior: the LLM attempts reasoning and issues a FAULT. The runtime
then:

1. suspends generation;
2. resolves the requirement;
3. materializes the object;
4. inserts it into the working set;
5. resumes.

This is our software approximation of a page fault.

## 12. FAULT versus SEARCH

These must stay distinct.

- **SEARCH** means "I need to discover an object."
- **FAULT** means "I know what state I require, but it isn't currently resident."

For example, `SEARCH(change://, "redis changes")` might discover
`change://9182`. Later, `FAULT(change://9182.details)` makes its details
resident.

## 13. EVIDENCE

Models must distinguish knowing that an object exists from having evidence for
a claim. `EVIDENCE(claim://redis-capacity-caused-incident184)` might return:

- `deploy://771`
- `metric://redis-connections`
- `logs://payment-timeouts`
- `config://redis/9182`

Claims are themselves graph objects, for example `claim://552` with:

- `SUPPORTED_BY → metric://781`
- `SUPPORTED_BY → logs://991`
- `CONTRADICTED_BY → metric://883`

## 14. Working set

Each context keeps a bounded resident working set:
`interface WorkingSet { objects: ResidentObject[]; maxObjects; maxTokens; evictionPolicy; }`.

An initial constraint is `maxObjects = 32` and `maxTokens = 16,000`. The whole
synthetic world might hold 1,000,000 objects; the model sees at most about 32
materialized objects.

## 15. Residency

Object states: `NON_RESIDENT` → (FAULT / READ) → `RESOLVING` → `RESIDENT` →
(pressure) → `EVICTED`. A possible extension is HOT / WARM / COLD /
NON_RESIDENT; V0 doesn't need it.

## 16. Eviction

Start with boring algorithms; LRU is enough. Later, investigate semantic
eviction:

    EvictionScore(o) = f(recency, task relevance, dependency, evidence importance, retrieval cost)

The model should not control eviction at first; that is a runtime
responsibility. This preserves the analogy: applications don't manually manage
physical RAM pages.

## 17. Model-visible context

The actual prompt should be intentionally sparse:

```
CONTEXT ctx://8472
TASK  Determine the most likely cause of incident://184.
RESIDENT OBJECTS
  incident://184  started_at: 14:32  affected: service://payments
  service://payments  status: degraded  DEPENDS_ON: service://redis-prod, service://stripe
AVAILABLE OPERATIONS  READ TRAVERSE SEARCH FAULT EVIDENCE
RULE  Do not assert external state that is not resident. If required state is unavailable, issue FAULT.
```

No 100k-token world dump.

## 18. Epistemic invariant

The model may reason freely over resident information. But:

    ExternalFact ∉ WorkingSet ⇒ CannotAssert(ExternalFact)
    Need(ExternalFact) ⇒ FAULT

For example, "Redis probably had max_connections=500" is invalid.
`FAULT(service://redis-prod.configuration, "Need connection limits to test
capacity hypothesis.")` is valid.

## 19. Provenance verifier

Don't trust the model to obey this voluntarily. Every materialized fact gets a
support identifier:

- `[fact:921] max_connections = 500`
- `[fact:922] changed_at = 14:20`
- `[fact:923] incident_started = 14:32`

Final assertions reference their support:

    CLAIM: Connection exhaustion is the likely cause.
    SUPPORT: fact:921 fact:922 fact:923

The runtime rejects unsupported external claims. This gives a primitive
approximation of memory safety for cognition.

## 20. Capability system

A context receives capabilities when it is created:
`interface Capability { namespace; operations: ("READ"|"SEARCH"|"TRAVERSE"|"WRITE")[]; scope?; }`.

Example `ctx://incident-agent`:

- `READ service://*`
- `READ logs://payments/*`
- `READ metrics://*`
- `SEARCH change://*`
- `TRAVERSE infrastructure://*`
- `DENY WRITE *`

The LLM cannot override these. An unauthorized operation produces
`CAPABILITY_FAULT`, not "Please don't do that."

## 21. Context switching

Contexts are persistent. Each one holds its task, working set, references,
evidence, capabilities and execution state. The scheduler can
`SUSPEND(ctx://A)`, `RESUME(ctx://B)` and later `RESUME(ctx://A)`, without
reconstructing A's entire world from conversation history.

## 22. Context inheritance

This is useful later for agents that spawn agents: a parent context spawns
children such as security-investigator, code-investigator and
metrics-investigator. Children inherit selected mounts and capabilities, not
necessarily memory:
`spawnContext({parent, capabilities: subset(parent.capabilities), task})`.
This gives delegation an OS-like containment model.

## 23. V0 synthetic world

Do not begin with GitHub, Slack or Kubernetes. Build a deterministic synthetic
environment, generated in this order:

1. organizations
2. services
3. dependencies
4. hosts
5. configurations
6. deployments
7. metrics
8. incidents

Aim for e.g. 100,000 objects and 500,000 relations, with known causal chains
injected: `change://72 → config://redis → connection_limit ↓ →
service://redis → latency ↑ → service://payments → incident://184`. Ground
truth is therefore known.

## 24. Task generation

Automatically produce questions such as "What caused incident 184?", where
answering requires 3–10 dereferences. Other task types:

- Which change caused X?
- Which service owns dependency Y?
- Which deployment introduced regression Z?
- Is hypothesis H supported?
- What changed between healthy state A and unhealthy state B?

Difficulty is controlled by graph distance (difficulty ≈ required traversal
depth).

## 25. Experimental conditions

Run identical tasks under four architectures:

- **A, full context:** serialize everything potentially relevant into the
  prompt. This becomes impossible as the world grows.
- **B, RAG:** retrieve the top-k chunks before inference.
- **C, agent/tool calling:** conventional search and query tools.
- **D, CVM:** persistent address space, stable references, bounded residency,
  explicit faults.

## 26. Scale experiment

World sizes 10², 10³, 10⁴, 10⁵ and 10⁶, with task complexity held roughly
constant. Measure whether CVM keeps the working set about constant as world
size grows. That is the headline experiment.

## 27. Metrics

Primary metrics:

- TaskAccuracy
- ResidentTokens
- ObjectsMaterialized
- FaultCount
- SearchCount
- UnsupportedClaimRate
- TotalInferenceTokens
- ExternalIO
- Latency

CVM-specific metrics:

- **Cognitive locality** `CL = UsefulResidentObjects / TotalMaterializedObjects`
- **Virtualization ratio** `VR = |AddressSpace| / |PeakWorkingSet|` (e.g.
  1,000,000 / 30 ≈ 33,333 at high accuracy)

## 28. Fault quality

`FaultPrecision = Faults contributing to solution / TotalFaults`. A bad model
might thrash (FAULT A, B, C, D, E...), the analogue of pathological memory
access. **Cognitive thrashing:**
`ThrashRate = RepeatedMaterializations / TotalMaterializations`.

## 29. Prefetching

Once V0 works, the runtime can predict likely future dereferences. A request
for `service://redis-prod` suggests `config://`, `metrics://` and
`change://recent/` for it, and the runtime can prefetch them. Prefetching is
an optimization, not the abstraction.

## 30. Caching

Resolvers cache materializations keyed by `ObjectRef + Version + Context
visibility`. That eventually gives a hierarchy:

- **L1:** active model context
- **L2:** runtime object cache
- **L3:** graph/index
- **L4:** original source
- **L5:** remote or expensive source

## 31. Suggested implementation

The suggested stack is TypeScript or Python with:

- Postgres for objects, relations, facts and provenance;
- in-memory storage or Redis for contexts, working sets and the
  materialization cache;
- an LLM API with structured outputs;
- a runtime holding the resolver registry, capability enforcement, the
  working-set manager and the experiment harness.

No vector database is required. SEARCH can be deterministic, which is
preferable so retrieval quality doesn't contaminate the first experiment.

*Implementation: Python standard library only; SQLite + FTS5 instead of Postgres.*

## 32. Runtime loop

```
while not context.finished:
    prompt = build_resident_view(context)
    action = model.step(prompt)
    match action:
        Read(ref, field)        -> working_set.materialize(resolver.read(context, ref, field))
        Traverse(ref, relation) -> working_set.add_refs(graph.traverse(ref, relation))
        Search(namespace, query)-> working_set.add_refs(search(namespace, query))
        Fault(requirement)      -> working_set.materialize(resolve_fault(context, requirement))
        Evidence(claim)         -> ...
```

## 33. What NOT to build (initially)

- autonomous multi-agent orchestration
- embeddings everywhere
- sophisticated memory summarization
- long-term human memory
- an MCP integration zoo
- a fancy UI
- RL
- a custom model or inference server
- GPU memory management
- semantic caching
- production connectors

The first question is narrower: can explicit dereferencing plus bounded
residency outperform context serialization as the external world becomes large?

## 34. Success criteria

V0 is successful if, at 10⁶ external objects:

- Accuracy_CVM ≈ Accuracy_FullContext at small scale;
- PeakResidentObjects < 50;
- task token consumption is mainly a function of task complexity rather than
  world size;
- unsupported external claims are near zero.

The killer graph: context consumed vs. world size. Full context rises
steeply, RAG plateaus, CVM stays flat, and accuracy stays roughly horizontal.

*Implementation: met with the reference processor at all sizes. With
DeepSeek-V4.1-Flash, residency and token criteria were met and no unsupported
claim was accepted, but accuracy was 0.70 at 10⁶ (see RESULTS_V0).*

## 35. V1: train for faults

Do this only after V0 validates the architecture. Construct trajectories:

1. task
2. reason
3. missing external state
4. FAULT
5. materialization
6. reason
7. TRAVERSE
8. FAULT
9. materialization
10. ANSWER + EVIDENCE

Fine-tune a small model on thousands to millions of these trajectories. The
learned invariant becomes **uncertainty about the world → dereference**,
rather than **uncertainty about the world → prediction**. That would be the
first genuinely interesting model-level result. *See [PLAN_V1.md](../PLAN_V1.md).*

## 36. Longer-term architecture

```
COGNITIVE PROCESS → Neural Processor → (references / faults / writes) → Cognitive MMU
  [identity · capabilities · provenance] → Context Manager → Working-set cache → Object resolver
  → Graph · Code · Records · Logs · APIs · World
```

The model is no longer responsible for carrying its universe around. It
computes inside a universe maintained by the substrate. That is the
architectural claim CVM v0.1 should attempt to falsify. Keep the first
repository aggressively small: `context`, `object`, `resolver`, `working_set`,
`runtime`, `synthetic_world`, `experiments`.
