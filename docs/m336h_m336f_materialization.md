# M-33.6h M336F materialization

`materialize_m336f_selected_source_snapshot` verifies the selector receipt, selected manifest, closure manifest, feasibility proof, source-entry bindings, exact selected and witness sets, identities, raw and canonical hashes, roles, paths, and destination containment before writing any Java source.

It rejects links, traversal, absolute selected paths, duplicates, missing witnesses, extras, unbound support files, hash or canonicalization drift, and destinations inside Git or public staging. Its public receipt contains only hashes, counts, roles, and status; selected paths and host paths stay private.
