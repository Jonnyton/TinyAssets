# Test plan (shape preparation; no runtime implementation)

1. Reserved-block fixture: total100, used77, available19 =>81% uniformly, not77%;
   exact85 triggers, below85 does not; zero total/missing/non-finite fails closed;
   zero available with positive total is100%. Unknown store mapping refuses.
2. Keep every running/stopped-container image, current daemon, two newest older
   daemon images, all newer images, configured digest and receipt rollback.
3. Reject foreign repo, mutable/unmapped refs, extra foreign aliases, malformed
   timestamps, missing current container, unreadable/invalid config or receipt.
4. Exact index+child+config/layer validation supports containerd index IDs and
   classic config IDs; mismatches, wrong platform, oversize or missing blobs,
   token/network timeout cause no removal. Token never appears in output.
5. Either lock busy or any fence-state file -> zero removals; a concurrent deploy cannot pass the
   same mutation lock. Registry verification occurs outside locks; locked phase
   is at most60seconds. New stopped-container reference before delete protects it.
6. Removal argument vector is exactly non-force immutable allowed repo digest;
   tests forbid system/image/builder prune, journal vacuum, rm-volume/container.
7. Recheck pressure after each delete: stop at75, maximum4 or120sbudget. Docker
   failure stops pass; actual bytes measured, not reclaimed-byte estimates.
8. Dry-run cannot call deletion seam. Unit tests preserve disk-watch command
   order, migrate weekly entrypoint and assert complete checksummed installer
   closure includes every dependency plus CLI-help smoke checks.
9. Linux process test: real advisory flock contention with fake Docker/registry
   subprocesses, no Docker-host mutation; immutable host-install fixture runs
   both units' commands from installed runtime outside source checkout.
10. Lead-owned production acceptance (not authorized here): inspected dry-run,
    active+rollback preservation, data/container unchanged, public health green,
    subsequent healthy timer tick no further unnecessary removals.
