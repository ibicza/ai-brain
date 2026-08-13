# ai-brain agent notes

## Project Navigation

Use the local `code-review-graph` index as the first navigation pass when exploring code structure, dependencies, callers, consumers, and likely blast radius.

Before a large task, or after a meaningful structural change, rebuild the graph from the repository root:

```powershell
.\scripts\update-code-graph.ps1
```

Prefer the graph for:

- finding target modules, classes, and functions;
- checking direct dependencies;
- finding callers and consumers;
- estimating blast radius before edits;
- orienting around runtime flows.

Use normal search tools such as `rg` to verify concrete details, inspect configuration, resolve ambiguous graph results, and confirm the final patch. Do not trust the graph blindly.

The generated `.code-review-graph/` directory is local cache and should not be committed. The `.code-review-graphignore` file is project configuration and may be committed.

After small local edits, a full graph rebuild is optional. Rebuild it when files are moved, public entry points change, module boundaries shift, or the graph appears stale.
