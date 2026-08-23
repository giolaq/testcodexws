# Compatibility and updates

Release: `workshop-v1.1.0`

The factory preserves remote Issues, Projects, pull requests, claims, reviews,
and run summaries across local upgrades. It does not reinterpret old local
state as current evidence when required governance or causal proof is missing.

## Supported upgrade boundary

`workshop-v1.1.0` is the first release with a managed-file install manifest.
Create a fresh checkout when moving from an earlier release. Do not copy the old
`.factory` directory: it contains machine-local prompts, logs, worktrees, and
credentials context rather than portable shared state.

New checkouts record `.factory/workshop-install.json` during
`factory/new_workshop.sh` or the first `setup_demo.sh` run. The ignored manifest
contains only the installed version, managed relative paths, hashes, and modes.
It contains no file contents or credentials.

## Update a managed checkout

Clone the desired tagged release beside the attendee repository:

```sh
git clone --branch workshop-v1.1.0 \
  https://github.com/giolaq/software-refactory-workshop.git \
  ../software-refactory-release
```

From the attendee repository, preview the change:

```sh
./factory/update_workshop.sh --source ../software-refactory-release
```

The preview prints `ADD`, `UPDATE`, and `REMOVE` for workshop-owned files. It
does not change the checkout. After reviewing the list:

```sh
./factory/update_workshop.sh \
  --source ../software-refactory-release \
  --apply
```

The updater manages `factory/`, `workshop-guide/`, `setup_demo.sh`, the bundled
PRD, and hosting configuration. It never manages the attendee's product source.
If a managed file differs from its installed hash, the update reports `DRIFT`
and changes nothing. Preserve or reconcile that customization manually, then
record a deliberate baseline or use a fresh checkout.

## Local-state behavior

| Existing artifact | Behavior in this release | Recovery |
| --- | --- | --- |
| Planning Run without approved Charter governance | Fails closed; it cannot publish or export current evidence | Keep the old plan as evidence and run Product Review again under the approved Charter |
| Execution state without profile, Charter hash, or merge authority | Fails closed before dispatch or merge | Reset only local execution, then republish and rerun governed Tickets |
| Ticket without causal RED/GREEN evidence | Cannot satisfy Standard or Assured completion | Re-run QA and implementation for that Ticket |
| Changed PRD, Project Contract, or Charter after planning | Old approvals become stale | Use **Restart planning safely**; do not blind-retry the expert |
| Existing remote claim | Remains authoritative after reset or fresh checkout | Resume the owning run or explicitly release the confirmed abandoned claim |
| Existing GitHub Issue, Project item, PR, review, or run summary | Preserved | Reconcile it through Live status or Monitor; never delete it through local reset |

Reset scopes are explicit. **Reset current run** clears local ticket execution
and factory-owned worktrees while keeping the approved plan. **Start workshop
over** also clears local planning artifacts and approvals. Neither action
releases remote claims or deletes GitHub evidence.

## Removed compatibility surface

The unsupported static `factory/dashboard.html` view was removed in
`workshop-v1.1.0`. The Control Center is the single operator dashboard and the
CLI remains its execution layer. This avoids two lifecycle vocabularies and two
partially overlapping state views.

## Merge behavior change

Lean, Standard, and Assured now stop at a human exact-revision merge decision.
The Supervisor recommends an approved head but cannot merge it. The optional
Autonomous Demo retains delegated merge execution only after a fresh explicit
opt-in; it is not the normal production path.
