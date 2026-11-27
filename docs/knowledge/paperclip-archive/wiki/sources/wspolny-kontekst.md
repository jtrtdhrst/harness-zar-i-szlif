---
title: WSPÓLNY KONTEKST — minimalny kanon wejściowy
type: source
tags: [kontekst, kontrakt, governance]
created: 2026-08-20
updated: 2026-10-04
---

# WSPÓLNY KONTEKST

Bootstrap only. Read when a task crosses domains or the issue/role pointers are insufficient; do not preload it on every heartbeat.

## Truth order
1. current explicit Board/user decision;
2. verified CURRENT from code/runtime/schema/tests;
3. [[wiki/projects/kompas-zbiorek/decisions]] and durable product knowledge;
4. [[wiki/sources/prd-kompas]] as TARGET;
5. domain Wiki;
6. issue history/raw as evidence only.

TARGET ≠ CURRENT. No current evidence = unconfirmed current state.

## Stable boundaries
- Publiczna nazwa produktu: **Żar i Szlif**; „Kompas Zbiórek” jest wyłącznie aliasem historycznym/technicznym, nie drugą aktywną marką. Nazwy repo, domen, API i slugów bez zmian automatycznych.
- Supabase/Postgres = application source of truth.
- Cloudflare Worker = API/integration/auth edge, not a second domain database.
- General scoped product implementation → Engineer.
- Architecture/root-cause/review → CTO.
- Execution-harness/runtime/environment defects → Harness/Environment.

CURRENT-sensitive endpoint/tool/model/deploy details must be verified only when relevant.

## Context rule
`issue/wake delta → role AGENTS → one domain source → targeted CURRENT verification`.
No whole-Wiki/full-PRD/broad-repo preload and no replay of continuation history already supplied by Paperclip.

Context/session policy: [[wiki/concepts/agent-context-budget]].
Further routing: [[wiki/index]].
