# Reflection

- **What surprised me:** Any process-local “private” registry remained forgeable by code in the same Python process. The trustworthy boundary required signed evidence verified from process-trusted public configuration, plus durable one-use admission in the database.
- **Pattern worth keeping:** Exact-head adversarial review should reproduce forged-but-self-consistent evidence, migration corruption, replay, and cross-process races rather than only inspect intended call paths.
- **What I would do differently:** Start with the signed, durable authority model and POSIX fork/corrupt-migration probes in the first design round instead of discovering those trust gaps during review.
