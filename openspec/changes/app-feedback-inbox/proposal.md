# App feedback inbox

Build authenticated app feedback submission and ticket tracking, with a reviewer inbox and an agent-readable path. Reports are private platform-held support records shared only with their submitter and the explicitly configured support reviewer. No submission grants execution authority or invokes a model. No new MCP handle.

Acceptance: durable ticket receipt; retry deduplication; own-ticket isolation; reviewer-only status transitions with revision checks; bounded requests and rate limits; safe text rendering; export and deletion; tests for concurrency and authority.
