# Żar i Szlif — Wiki Index (historycznie: Kompas Zbiórek)

This is a router, not a preload list. Start from the narrowest source needed for the current issue.

## Start
1. current issue / wake delta;
2. role `wiki/agents/<role>/AGENTS.md`;
3. [[wiki/concepts/agent-context-budget]] for prompt/session hygiene when context grows;
4. one domain page only if needed.

Do not read the whole Wiki or full PRD by default.

## Core context
- [[wiki/concepts/language-and-content-policy]] — mandatory English operational output; preserve Polish brand, product copy, UI, stories and marketing emails.
- [[wiki/concepts/context-first-execution]] — startup order and resume/delta semantics.
- [[wiki/sources/wspolny-kontekst]] — cross-domain bootstrap only.
- [[wiki/concepts/definition-of-done]] — delivery/review/docs closeout.
- [[wiki/entities/repo-map]] — product-repo routing when repository location is relevant.

## Product / requirements
- [[wiki/concepts/zar-i-szlif-swiat-i-gamifikacja]] — kierunek świata i gamifikacji Żar i Szlif (TARGET).
- [[wiki/concepts/onboarding]] — kanoniczny onboarding TARGET 2026-10-18: CTA, zwierzak, prywatne pytania o staż, drużyna i zaproszenia.
- [[wiki/concepts/arc-01-nasz-pierwszy-namiot]] — roboczy Arc 1 po onboardingu: Namiot Zastępu, prywatne pytania i dziennik aktywności; **WORKING DRAFT**, nie implementacja.
- [[wiki/concepts/arc-02-wyznaczamy-kierunek]] — Arc 2: obowiązkowy temat roczny, jeden cel z DoD na bieżące 3 miesiące, aktywności miesięczne i Dziennik Aktywności; zasady uzgodnione, scenki robocze.
- [[wiki/concepts/arc-03-przygotujmy-zbiorke]] — Arc 3: trzy zadania w jednej karcie, **tylko Planowanie**, bez eksperymentu na pierwszej zbiórce (working draft).
- [[wiki/concepts/arc-04-co-zabieramy-dalej]] — Arc 4: **Podsumowanie** po realizacji i opcjonalne **Problemy** oraz eksperyment na przyszłość (working draft).
- [[wiki/concepts/karta-zbiorki]] — mapa pól i trzech zakładek karty: co planujemy, co zapisujemy po zbiórce, jak przechodzi eksperyment.
- [[wiki/projects/kompas-zbiorek/index]] — durable product knowledge.
- [[wiki/projects/kompas-zbiorek/decisions]] — current/superseded decisions.
- [[wiki/sources/prd-kompas]] — TARGET requirements; load requirement-specific sections only.

## Architecture / integrations
- [[wiki/concepts/product-mcp-crud-and-chatgpt-client-eligibility-20261107]] — authoritative boundary: MCP CRUD vs ChatGPT plan/plugin eligibility vs free in-app user access; historical read-only Worker is not a protocol restriction.
- [[wiki/sources/integracje-mcp]]
- [[wiki/concepts/product-mcp-cloudflare-worker]] — current dedicated product MCP Worker, Cloudflare config, security and self-repair runbook (on demand).
- [[wiki/entities/integracje-api]]
- [[wiki/entities/mcp-qdrant-hybrid]]
- [[wiki/concepts/plugin-boundaries]]
- [[wiki/concepts/paperclip-wiki-mcp]]

## UI / design / QA
- [[wiki/concepts/brand-dna]]
- [[wiki/concepts/ui-delivery-ownership]]
- [[wiki/concepts/bramka-jakosci-ui]]
- [[wiki/concepts/mascot-style-2-pipeline]] — canonical mascot pipeline: contracts, V3/V4 history, quality gates, native DAG and owners.
- [[wiki/concepts/mascot-rework-ui-qa-rubric]] — UI QA acceptance rubric for the post-rejection mascot rework: app-anchored surface contrast, path-level failure classes, crop acceptance test, per-size proof expectations, verified browser-verification environment notes.

## Agent contracts
Role pages contain only always-loaded ownership/boundaries and pointers to lazy skills:
- `wiki/agents/ceo/AGENTS.md`
- `wiki/agents/coo/AGENTS.md`
- `wiki/agents/cto/AGENTS.md`
- `wiki/agents/engineer/AGENTS.md`
- `wiki/agents/mcp-engineer/AGENTS.md`
- `wiki/agents/designer/AGENTS.md`
- `wiki/agents/ui-qa/AGENTS.md`
- `wiki/agents/cmo/AGENTS.md`
- `wiki/agents/email-creative/AGENTS.md`
- `wiki/agents/lifecycle-ops/AGENTS.md`

Do not create parallel copies of role contracts. Detailed procedures belong in canonical skills/on-demand pages.

## CURRENT
Verify CURRENT-sensitive paths, endpoints, tools, models, deploy recipes and schemas only when relevant. `raw/` and `wiki/log.md` are evidence/history and never override a newer decision or verified runtime state.