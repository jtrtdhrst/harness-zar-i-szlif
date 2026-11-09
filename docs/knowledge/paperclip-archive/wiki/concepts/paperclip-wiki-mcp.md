---
title: Paperclip MCP Wiki — read/write contract
type: concept
tags: [paperclip, mcp, wiki, concurrency, optimistic-locking]
sources: [raw/WSPOLNY_KONTEKST.md, raw/documentation.md]
created: 2026-08-26
updated: 2026-09-07
---

# Paperclip MCP Wiki

## Aktualny zakres

Dostępne operacje Wiki:

- `paperclipWikiList` — lista stron do routingu;
- `paperclipWikiSearch` — search po path/title;
- `paperclipWikiGetPage` — pełny Markdown + aktualny hash;
- `paperclipWikiProposeChange` — dry-run zapisu;
- `paperclipWikiApplyChange` — zapis istniejącej strony z optimistic locking;
- `paperclipWikiCreatePage` — utworzenie nowej strony;
- `paperclipWikiMovePage` — rename/move;
- `paperclipWikiDeletePage` — usunięcie strony z aktualnym hashem.

Nie utrzymuj w tej stronie listy narzędzi, których aktualny Paperclip runtime nie wystawia.

## Read-before-write

Przed modyfikacją lub usunięciem pobierz stronę przez `paperclipWikiGetPage` i użyj zwróconego **aktualnego hash**. Przy konflikcie pobierz stronę ponownie i przebuduj zmianę; nie obchodź optimistic locking.

`paperclipWikiList` służy do routingu. Hash do write/delete bierz z bezpośredniego `GetPage` wykonanego przed operacją.

## Granice

Wiki przechowuje durable knowledge i kanoniczne kontrakty agentów pod `wiki/agents/*/AGENTS.md`. `raw/`, runtime configuration, sekrety, `.git/` i inne wewnętrzne pliki nie są bieżącym kanonem do edycji przez publiczny Wiki path.

`index.md`, `log.md` oraz pliki chronione przez runtime mogą mieć ograniczenia Delete; aktualne ograniczenia sprawdzaj przez bieżący tool/runtime, nie przez historyczną listę.

## Weryfikacja

Read oraz operacje create/read/move/update/delete z ochroną hash były używane i zweryfikowane w bieżącym Wiki workflow. Szczegóły historycznych testów należą do `wiki/log.md`, nie do tego trwałego kontraktu.