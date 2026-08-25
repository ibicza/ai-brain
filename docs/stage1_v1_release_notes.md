# Stage-1 v1 Release Notes

## v1.0.1

Stage-1 v1.0.1 hardens the frozen v1.0.0 architecture with bounded state, execution, and trace policies; strict ProgramSpecification and workflow artifact schemas; explicit verified-bundle review; approval binding to the review hash; proposal-to-rule installation receipts; complete audit evidence and failure events; audit reconstruction; mandatory RuleMemory checksums and explicit legacy migration; durable validated writes and explicit backup recovery; full RU/EN synonym contradiction coverage; and a standalone UTF-8 no-torch production CLI.

Release evidence uses two commits: the annotated `stage1-v1.0.1` tag targets the exact locally and remotely tested code commit H, while logs and generated evidence live in later evidence-only commit E. No self-referential commit SHA is embedded in H.

The six families, four registers, three primitives, controlled language, compiler, CEGIS budget, and verifier semantics are unchanged.
