# ai-brain — Lifelong Cognitive System Roadmap

**Status:** North-star roadmap after M-30  
**Target repository path:** `docs/lifelong_cognitive_system_roadmap.md`  
**Scope:** architecture and research direction, not a fixed release schedule

---

## 1. North star

`ai-brain` is not intended to become a model that permanently stores all knowledge of the world in its weights.

The target is a lifelong-learning cognitive system that can:

1. receive new material and experience;
2. distinguish facts, rules, procedures, concepts, events, examples, constraints and interpretations;
3. preserve source provenance and uncertainty;
4. verify or contest extracted knowledge;
5. use external memory and exact capabilities to answer, reason and act;
6. restructure memory over time;
7. consolidate stable, general and frequently useful abstractions into adapters or weights;
8. remember long-lived personal and episodic experience without retaining every irrelevant detail;
9. generate its own questions and continue useful internal work between user requests;
10. later ground its existing concepts in continuous vision and audio streams.

The core principle is:

> The system does not need to know everything in its weights. It must know how to acquire, verify, organize, retrieve, apply, revise and eventually consolidate knowledge.

Weights are a fast learned cache of stable abstractions.  
External memory remains the editable, attributable and historically correct source of detailed knowledge.

---

## 2. Non-negotiable architectural principles

### 2.1 Knowledge is not one homogeneous object

The system must distinguish at least:

- facts and claims;
- rules and equations;
- procedures and algorithms;
- concepts and definitions;
- constraints and applicability conditions;
- causal claims;
- temporal and spatial relations;
- examples and counterexamples;
- interpretations and competing viewpoints;
- source evidence;
- episodic events;
- relationship-specific knowledge;
- learned skills;
- current working state.

### 2.2 New subjects must not require new core code

A new subject should normally be installed as a generated knowledge pack.

New core code is justified only when the material requires a genuinely new reusable capability, for example:

- symbolic algebra;
- theorem proving;
- spatial/GIS reasoning;
- code compilation;
- image understanding;
- audio understanding.

The governing question for every future implementation is:

> Is this a reusable capability, or are we hardcoding another subject?

### 2.3 Verified external knowledge overrides recalled weight knowledge

When the model's parametric memory conflicts with current verified external memory:

- the conflict is surfaced;
- verified current memory is used for trusted output;
- the mismatch becomes a consolidation/retraining candidate;
- the old weight association is not silently treated as authoritative.

### 2.4 No automatic promotion from observation to truth

Any source, web page, conversation, image, audio segment or model extraction initially creates a proposal.

Trusted memory requires the relevant combination of:

- source identity;
- provenance;
- verification;
- conflict handling;
- review or exact tests;
- applicability conditions.

### 2.5 No content-censorship roadmap

This roadmap does not introduce:

- moral filters;
- NSFW filters;
- political or ideological restrictions;
- generic refusal policies;
- topic bans;
- restrictions on internal reasoning.

Technical controls remain necessary:

- bounded resource use;
- authority separation;
- provenance;
- explicit confirmation for consequential actions;
- privacy and retention controls for personal and sensor data;
- rollback and regression checks for dynamic weights.

---

## 3. Target cognitive architecture

```text
Text / documents / web / code / conversation / video / audio / actions
                                |
                                v
                        Experience ingestion
                                |
                                v
                 Segmentation and type recognition
                                |
                                v
          Facts / rules / concepts / procedures / events / relations
                                |
                                v
              Verification, conflict detection and clarification
                                |
                                v
+-----------------------------------------------------------------------+
| Working Memory                                                        |
| Semantic / Fact Memory                                                |
| Rule and Procedure Memory                                             |
| Concept Graph                                                         |
| Skill and Capability Registry                                         |
| Episodic Memory                                                       |
| Relationship Memory                                                   |
| Source and Provenance Memory                                          |
| Goal / Agenda Memory                                                  |
+-----------------------------------------------------------------------+
                                |
                                v
                 Reasoning, retrieval, action and teaching
                                |
                                v
                  Usage, novelty and error observations
                                |
             +------------------+------------------+
             |                                     |
             v                                     v
     Continuous cognitive loop             Sleep / consolidation loop
             |                                     |
             +------------------+------------------+
                                |
                                v
             Stable adapter / weight consolidation candidates
```

---

## 4. Memory architecture

### 4.1 Working memory

Contains the active state required now:

- current conversation;
- active goal;
- current problem;
- retrieved facts and rules;
- intermediate calculations;
- active sensory objects;
- pending clarifications;
- current tool or skill state.

Working memory is small, fast and disposable. It is not long-term truth storage.

### 4.2 Semantic memory

Stores generalized knowledge:

- entities;
- definitions;
- factual claims;
- classifications;
- temporal facts;
- spatial facts;
- source versions;
- conflicts and supersession.

Existing `FactMemory` is the foundation.

### 4.3 Procedural memory

Stores how to perform actions:

- exact rules;
- algorithms;
- equations;
- procedures;
- API contracts;
- verified programs;
- executable skills.

Existing `RuleMemory`, exact interpreter, tools and `SkillRegistry` are the foundation.

### 4.4 Concept graph

Stores conceptual structure:

- prerequisites;
- is-a relations;
- part-whole relations;
- dependencies;
- equivalence and contrast;
- causal and temporal links;
- capability requirements.

The graph must be domain-independent.

### 4.5 Episodic memory

Stores events rather than timeless facts.

Each episode should bind:

- time interval;
- participants and objects;
- context;
- observations;
- actions;
- outcomes;
- emotional/goal significance when explicitly observable;
- source modality;
- confidence;
- links to related facts, concepts and people;
- salience;
- retention policy.

Examples:

- a conversation today;
- a debugging session yesterday;
- the first successful model experiment;
- a rare event from ten years ago;
- a recurring interaction pattern.

### 4.6 Relationship memory

Stores knowledge associated with a person, model, organization, device or other persistent entity.

It must distinguish:

- directly stated facts;
- direct observations;
- reports from third parties;
- system inferences;
- uncertain hypotheses;
- shared episodes;
- stable preferences;
- current relationship context.

A relationship summary is not a dump of all interactions.

### 4.7 Source memory

Stores:

- original snapshots;
- versions;
- derivations;
- evidence locations;
- trust and lineage metadata;
- retractions;
- conflicts;
- currentness.

### 4.8 Goal and agenda memory

Stores:

- current user goals;
- system maintenance goals;
- unresolved questions;
- contradictions;
- stale knowledge;
- missing capabilities;
- long-running research tasks;
- self-generated questions;
- scheduled consolidation work.

---

## 5. Dynamic episodic retention

The system should not remember every low-value event forever.

### 5.1 Retention hierarchy

```text
Seconds to minutes:
raw sensory ring buffers and fine-grained working events

Hours to days:
detailed episodes and current projects

Weeks to months:
compressed thematic episodes and recurring patterns

Years:
anchor memories, major changes, enduring relationships and rare events
```

### 5.2 Salience model

A retention score may combine:

- novelty;
- rarity;
- goal relevance;
- emotional significance when explicitly observed;
- relationship significance;
- future usefulness;
- repeated retrieval;
- causal importance;
- user instruction to remember;
- verification quality.

### 5.3 Memory restructuring

Over time, the system may:

- merge repetitive episodes;
- discard irrelevant detail;
- create summaries;
- preserve exceptional anchor memories;
- extract stable semantic facts;
- extract relationship patterns;
- retain links back to original episodes where needed.

Example:

```text
Raw episode:
"The user drank tea at 10:00."

Possible fate:
discarded as irrelevant.

Repeated meaningful pattern:
"The user often drinks tea during late-night project work."

Possible consolidation:
relationship preference/pattern with supporting episodes.
```

The system must support explicit user controls:

- remember this;
- do not store this;
- forget this;
- this was wrong;
- retain this only temporarily.

---

## 6. Wake, idle and sleep cycles

The long-term system should not exist only in the pattern:

```text
question -> reasoning -> action -> answer -> off
```

It should operate through three coordinated loops.

### 6.1 Wake loop

Triggered by user input, environment events or active goals.

```text
observe
-> update working memory
-> identify goals and uncertainties
-> retrieve relevant knowledge
-> reason
-> act or ask
-> verify outcome
-> store experience
-> update agenda
```

### 6.2 Idle cognitive loop

Runs when no urgent user task is active.

The purpose is not endless random token generation. It is bounded, agenda-driven cognition.

Possible activities:

- revisit unresolved contradictions;
- verify stale sources;
- test a recently learned rule;
- generate counterexamples;
- compare similar concepts;
- organize project plans;
- ask itself why a result failed;
- formulate questions for the user;
- prefetch likely needed knowledge;
- review recent mistakes;
- improve summaries;
- identify missing capabilities.

Each self-generated task must have:

- a reason;
- priority;
- budget;
- expected benefit;
- dependencies;
- termination condition;
- audit record.

### 6.3 Sleep / consolidation loop

A scheduled maintenance and learning cycle.

```text
1. Collect recent episodes, used facts, rules and errors.
2. Detect duplicates, contradictions and stale information.
3. Rebuild episodic summaries and relationship summaries.
4. Extract stable semantic and procedural candidates.
5. Recheck facts and rules against current sources.
6. Identify frequently used and expensive-to-retrieve knowledge.
7. Select candidates for adapter/weight consolidation.
8. Build replay and anti-forgetting datasets.
9. Train a candidate adapter.
10. Run regression, truth-consistency and capability tests.
11. Compare against external memory.
12. Promote or rollback.
13. Record consolidation provenance.
```

Sleep is not merely weight training. Most sleep cycles may only restructure external memory.

---

## 7. Self-generated questions and autonomous thought

The system should learn to ask useful questions without waiting for a user.

Question triggers include:

- conflicting verified claims;
- a rule with unknown applicability conditions;
- a prediction error;
- a missing prerequisite;
- a newly observed pattern;
- an incomplete relationship model;
- a stale source;
- a failed tool or skill;
- an unexplained anomaly;
- a gap between weights and external memory;
- a long-term goal without a next step.

Question classes:

- clarification for a person;
- source research question;
- internal consistency question;
- experiment proposal;
- missing capability request;
- memory-restructuring question;
- counterexample search;
- causal explanation request.

The cognitive loop should prefer useful questions over aimless monologue.

---

## 8. Dynamic weights and nightly consolidation

### 8.1 What belongs in weights

Good candidates:

- stable language patterns;
- reusable abstractions;
- common reasoning motifs;
- generalized procedures;
- frequently used concepts;
- robust interface habits;
- broadly useful compressed representations.

### 8.2 What should remain external

Prefer external memory for:

- precise dates;
- fast-changing facts;
- source provenance;
- personal episodes;
- relationship-specific facts;
- deletable information;
- legal or versioned documents;
- contested claims;
- detailed technical documentation.

### 8.3 Adapter-first strategy

Preferred hierarchy:

```text
Frozen base model
+ experimental short-term adapter
+ stable promoted adapter
+ domain/capability adapters
+ optional personal interaction adapter
```

Promotion requires:

- regression pass;
- no catastrophic forgetting;
- consistency with external memory;
- rollback support;
- provenance of the training set;
- no silent deletion of old knowledge;
- measurable benefit.

### 8.4 Weight-memory consistency checks

Periodically:

```text
answer from weights alone
-> extract claims/rules
-> compare with current external memory
-> classify:
   MATCH
   OUTDATED
   CONFLICT
   UNSUPPORTED
```

Disagreement becomes a consolidation or unlearning candidate.

---

## 9. Universal knowledge acquisition

The end state is:

```text
new sources
-> automatically detect knowledge types and required capabilities
-> construct a provisional knowledge pack
-> verify and clarify
-> install
-> solve held-out tasks using only the installed material
```

### 9.1 Universal Knowledge IR

The IR should represent:

- Claim;
- Definition;
- Concept;
- Entity;
- EntityType;
- Relation;
- TaxonomyEdge;
- PartWholeRelation;
- QuantityType;
- Unit;
- Equation;
- Constraint;
- Procedure;
- Algorithm;
- StateTransition;
- CausalRule;
- TemporalClaim;
- SpatialClaim;
- Exception;
- ApplicabilityCondition;
- Example;
- Counterexample;
- TestCase;
- ExerciseTemplate;
- Interpretation;
- SourceEvidence.

Knowledge character must be explicit:

- deterministic;
- empirical;
- approximate;
- heuristic;
- normative;
- interpretive;
- contested.

### 9.2 Capability registry

Reusable capabilities may include:

- factual retrieval;
- temporal reasoning;
- spatial reasoning;
- taxonomies;
- quantities and units;
- algebra;
- equation systems;
- constraints;
- causal graphs;
- procedures;
- code parsing;
- code compilation and testing;
- theorem proving;
- GIS;
- simulation;
- document parsing.

### 9.3 Domain packs

A generated pack should contain:

- `DomainManifest`;
- `ConceptGraph`;
- entity and relation schemas;
- facts;
- rules;
- constraints;
- procedures;
- examples and tests;
- exercise families;
- source snapshots;
- verification receipts;
- required capabilities.

A domain pack is content, not a new core module.

---

## 10. Web autonomy

### 10.1 Controlled-source phase

Start with bounded source families:

- official documentation;
- standards;
- primary scientific literature;
- university material;
- official repositories;
- selected reference works;
- Wikipedia as secondary orientation;
- Habr and similar engineering sources as practical secondary material.

Pipeline:

```text
fetch
-> immutable snapshot
-> provenance
-> extraction proposals
-> conflict detection
-> verification/review
-> memory
```

The web must never directly write trusted memory or weights.

### 10.2 Open-web phase

Later permit unrestricted discovery with:

- adversarial-source detection;
- source lineage;
- duplicate detection;
- reputation as metadata, not proof;
- conflict preservation;
- version tracking;
- monitoring and retraction handling;
- bounded autonomous research agendas.

---

## 11. Multimodal grounding

### 11.1 Paired learning

Later, teach vision and audio together with existing concepts.

Example:

```text
visual object
+ spoken/written label
+ sound
+ action context
+ existing concept graph
```

The system should be able to ask:

- Is this a cup or a glass?
- Is this sound produced by the object or the table?
- Is this the same object in the next frame?
- Why is this called a mug here?
- Which person is speaking?
- Does the current observation contradict the stored concept?

### 11.2 Vision memory

Represent:

- objects;
- tracks over time;
- scenes;
- spatial relations;
- actions;
- changes;
- uncertainty;
- visual evidence;
- links to entities and episodes.

### 11.3 Audio memory

Represent:

- speech segments;
- speaker identity hypotheses;
- non-speech sounds;
- temporal location;
- source direction when available;
- transcription;
- uncertainty;
- links to visual objects and episodes.

---

## 12. Continuous video and audio perception

The final sensor architecture should behave more like continuous perception than isolated file upload.

```text
camera stream + microphone stream
                |
                v
short raw ring buffers
                |
                v
streaming encoders and trackers
                |
                v
event segmentation
                |
                v
multimodal working memory
                |
                v
episodic memory and semantic updates
```

### 12.1 Retention layers

- raw video/audio: short-lived ring buffer by default;
- selected event clips: retained when salient or explicitly requested;
- structured observations: longer-lived;
- episode summaries: long-lived when important;
- semantic and relationship updates: retained with provenance.

### 12.2 Always-on does not mean store everything forever

Continuous perception should preserve continuity while still using:

- bounded raw buffers;
- event segmentation;
- salience;
- explicit retention;
- compression;
- deletion;
- privacy boundaries;
- per-person and per-location policies.

### 12.3 Cross-modal object continuity

The system should maintain persistent hypotheses:

```text
this face + this voice + this name + these prior episodes
-> possibly the same person
```

But identity links must remain probabilistic until verified.

---

## 13. Milestone roadmap after M-30

### M-31 — Universal Knowledge IR and Capability Registry

**Goal:** remove chemistry from the center of the architecture.

Deliver:

- universal IR;
- capability descriptors;
- generic pack manifest;
- chemistry represented as a pack;
- no chemistry-specific assumptions in the educational core.

Gate:

- chemistry still passes without relying on a chemistry-only core contract.

### M-32 — Source-to-Knowledge Compiler

**Goal:** turn heterogeneous material into provisional structured knowledge.

Inputs:

- PDF;
- HTML;
- Markdown;
- tables;
- code;
- API documentation.

Outputs:

- concepts;
- claims;
- rules;
- procedures;
- constraints;
- examples;
- tests;
- required capabilities;
- review questions.

Gate:

- extracted knowledge is attributable and testable;
- ambiguous items are not silently installed.

### M-33 — Cross-domain black-box proof

**Goal:** prove generality without core changes.

Target source sets:

1. school kinematics;
2. a biology chapter;
3. a historical topic with competing interpretations;
4. Java or library documentation.

Rule:

> No core-code changes between these material sets.

Allowed:

- generated packs;
- existing capability configuration;
- review artifacts.

Gate:

- held-out tasks solved using only installed material;
- unsupported operations return `NEEDS_NEW_CAPABILITY`.

### M-34 — Episodic and Relationship Memory

**Goal:** remember experience and people dynamically.

Deliver:

- event segmentation;
- salience;
- hierarchical compression;
- relationship summaries;
- direct observation vs report vs inference;
- forgetting and correction;
- long-lived anchor memories.

Gate:

- detailed recent memory;
- compressed old routine memory;
- preserved rare significant episodes;
- no cross-person contamination.

### M-35 — Sleep and External-Memory Consolidation

**Goal:** reorganize memory without weight changes.

Deliver:

- nightly agenda;
- duplicate merging;
- stale-source verification;
- episodic summarization;
- semantic extraction;
- relationship restructuring;
- unresolved-question generation.

Gate:

- improved retrieval and lower redundancy;
- no loss of anchor memories;
- full audit and rollback.

### M-36 — Dynamic Adapters and Weight Consolidation

**Goal:** move stable abstractions into learned parameters safely.

Deliver:

- candidate selection;
- adapter training;
- replay;
- anti-forgetting tests;
- memory-consistency tests;
- promotion and rollback;
- adapter provenance.

Gate:

- measurable speed/quality gain;
- no trusted factual regression;
- no catastrophic forgetting;
- external memory remains authoritative.

### M-37 — Persistent Cognitive Loop

**Goal:** maintain bounded self-directed cognition between requests.

Deliver:

- cognitive agenda;
- self-generated questions;
- idle tasks;
- resource scheduler;
- curiosity and anomaly triggers;
- termination policies;
- long-running project state;
- wake/idle/sleep coordination.

Gate:

- useful autonomous work;
- no runaway token loop;
- no duplicate agenda explosion;
- explicit reasons and budgets for every background task.

### M-38 — Controlled Web Autonomy

**Goal:** autonomous research within selected source families.

Deliver:

- source discovery;
- snapshotting;
- extraction proposals;
- update monitoring;
- contradiction handling;
- scheduled research tasks.

Gate:

- no direct trusted writes;
- provenance complete;
- retractions propagate;
- adversarial pages cannot become authority.

### M-39 — Open-Web Acquisition

**Goal:** broaden discovery to the open internet.

Deliver:

- adversarial-source defenses;
- source lineage;
- reputation metadata;
- duplicate farms detection;
- misinformation conflict retention;
- broad autonomous research.

### M-40 — Vision and Audio Grounding

**Goal:** connect existing concepts to images, speech and sound.

Deliver:

- paired multimodal teaching;
- object and speaker hypotheses;
- multimodal questions;
- grounded episodic events.

### M-41 — Continuous Sensor Streams

**Goal:** persistent video/audio perception.

Deliver:

- streaming encoders;
- ring buffers;
- object tracking;
- speaker tracking;
- event segmentation;
- cross-modal episodic memory;
- salience-based retention.

Gate:

- continuity across time;
- bounded storage;
- explicit privacy and retention controls;
- no unverified identity certainty.

### M-42 — Unified Lifelong Cognitive Agent

**Goal:** integrate acquisition, memory, cognition, sleep, dynamic weights, web and perception.

The system should:

- remain active across turns;
- manage long-running goals;
- learn new domains from sources;
- remember relationships and episodes;
- research independently;
- update itself through verified consolidation;
- perceive continuous multimodal streams;
- ask useful questions;
- preserve provenance and rollback.

---

## 14. Major proof points

### Proof point A — M-30

A complete trusted conversational tutor for the bounded chemistry domain.

### Proof point B — M-33

Four materially different domains installed without changing the core.

This is the first convincing proof of general learning from arbitrary materials.

### Proof point C — M-36

Stable knowledge and procedures safely consolidated into adapters while remaining consistent with external memory.

### Proof point D — M-37

The system performs useful self-directed cognition between user requests.

### Proof point E — M-41

The system maintains continuous grounded vision/audio experience and integrates it into episodic and semantic memory.

---

## 15. Definition of long-term success

The project reaches its intended goal when the system can:

1. receive unfamiliar material;
2. determine the knowledge types and required capabilities;
3. construct a provisional knowledge pack;
4. ask targeted clarification questions;
5. verify examples, rules and sources;
6. install the pack without core changes;
7. solve held-out tasks from the installed material;
8. revise or invalidate knowledge when sources change;
9. remember experiences and relationships at appropriate detail;
10. maintain an autonomous but bounded cognitive agenda;
11. restructure memory during sleep;
12. safely consolidate stable abstractions into adapters or weights;
13. research the web with provenance;
14. connect concepts to continuous vision and audio;
15. retain the ability to explain where knowledge came from and why an action was taken.

---

## 16. Immediate continuation rule

After M-30 is complete:

1. freeze the trusted conversational tutor interfaces;
2. do not begin another chemistry-specific expansion;
3. start M-31 with the Universal Knowledge IR and Capability Registry;
4. migrate chemistry into the generic pack format;
5. treat every new implementation decision as either:
   - generic knowledge representation;
   - reusable capability;
   - generated domain content;
   - or unjustified domain hardcoding.

This roadmap is the architectural north star for all milestones after M-30.
