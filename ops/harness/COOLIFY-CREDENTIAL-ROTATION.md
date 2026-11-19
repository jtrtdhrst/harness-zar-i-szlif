# ZARI-240 / ZARI-261 — systemowa rotacja Coolify API tokens

Status: **bezpieczna procedura i read-only gate; brak autoryzacji do rotacji i brak zdjęcia HOLD**.

## Potwierdzona przyczyna źródłowa (19 listopada 2026)

Trzy niezależne działające kontrolery czytają ten sam root-only sekret z:
  /root/coolify-secrets/coolify_api_token

Dotyczy: harness_native_delivery.py, product-image-delivery.py i product_mcp_host_delivery.py. Wyłączenie starego harness_image_delivery.py (exit 78) nie unieważniło jego tokenu. Autoryzowany odczyt GET /api/v1/services/a6ci2beifbinzckfnneiqnjd starym tokenem zwraca 200, bez tokenu 401. Natychmiastowe unieważnienie sekretu bez migracji 3 konsumentów przerwałoby ich działanie.

Oficjalna dokumentacja: https://coolify.io/docs/core/security/credentials/api-tokens i https://coolify.io/docs/api/permissions

## Docelowy mechanizm

Administrator odpowiedniego teamu Coolify tworzy w panelu Keys & Tokens → API Tokens trzy osobne tokeny z wąskimi zakresami zasobów, kontrolowanym terminem ważności i najniższymi potrzebnymi uprawnieniami. Nie używaj root ani All Resources jako obejścia błędów 403. Opcje wymagają weryfikacji rzeczywistych endpointów kontrolera: read (GET), write (PATCH compose) i deploy (POST deploy).

Nowe root-only ścieżki (0600, atomowy zapis przez zatwierdzone zarządzanie sekretami):
- Harness: /root/coolify-secrets/harness_delivery_api_token
- Product image: /root/coolify-secrets/product_image_delivery_api_token
- Product MCP host: /root/coolify-secrets/product_mcp_host_delivery_api_token

Nie kopiuj starego sekretu do nowych plików. Nie umieszczaj tokenów w argv, URL, logach, repo, issue ani plikach env dostępnym dla innych użytkowników.

## Etapy — niezależna kontrola przed każdą mutacją

1. Utrwal przed zmianą: root-owned kontrolery, trzy główne UUID, stan działającego obrazu Docker oraz podpisane zgody (nie wystawiaj ich sam). Uruchom read-only gate w trybie inspect. Ten tryb powinien zgłosić BLOCKED, dopóki 3 kontrolery współdzielą token.
2. Uprawniony administrator Coolify tworzy oddzielne tokeny natywną funkcją platformy. Root operator bezpiecznie zapisuje każdy w odpowiednim dedykowanym pliku, upewnia się, że własność to root, mode=0600, bez symlinków i bez odzyskiwania starego tokenu.
3. Uruchom tryb staged z trzema argumentami --target NAZWA=UUID. Nowe tokeny muszą być różne od starego i od siebie, a każdy wskazany GET musi zwrócić 200. Staged PASS to **tylko odczyt**, nie dowód możliwości PATCH/POST i nie jest zgodą na release. Potwierdź write/deploy z oficjalnych uprawnień tokenu i pozytywnej kontroli właściciela.
4. W osobnych, zatwierdzonych PR zmień trzy kontrolery tak, by każdy wskazywał dedykowany plik. Istniejący PR #159 modyfikuje harness_native_delivery.py — nie uruchamiaj równoległego writera tego samego pliku. Przed instalacją wymagane niezależne review dokładnego SHA, backup, test odmowy bez tokenu, rollback i odczyt installed SHA. Nie zmieniaj obecnej polityki HOLD.
5. Dopiero po bezpiecznym przełączeniu wszystkich trzech administrator odwołuje stary token w Coolify. Uruchom gate w trybie revoked: wymaga starego GET=401, nowych 3x GET=200, trzech ścieżek wskazujących dedykowane tokeny, braku powtórnego użycia sekretu i braku zmiany działającego imageId.
6. Zapisz wynik i podpisane/zweryfikowane metadane bez sekretów w ledgerze wydania. Niezależny CHO/COO może dopiero wtedy ponownie oceniać osobny per-UUID HOLD, attestację, immutable digest, plan rollback i produkcyjne E2E. Rotacja tokenu sama nigdy nie znosi HOLD.

## Read-only gate

Plik: scripts/harness_coolify_credential_gate.py

Przykład baseline (nie wykonuje zmian):

python3 scripts/harness_coolify_credential_gate.py --phase inspect --legacy-service-uuid a6ci2beifbinzckfnneiqnjd --expected-image-id sha256:bd1b33731dfe3342166359e5df46d459eb2dde68b73525a28ada63f6c19d291b

Staged i revoked wymagają każdej pary --target controller=serviceUUID dla harness, product_image i product_mcp_host. UUID muszą pochodzić z aktualnej autorytatywnej konfiguracji platformy, nie z wymyślonego placeholdera. Endpoint GET testuje tylko odczyt i dostęp do wskazanego zasobu. Gate nie zapisuje sekretów, nie zmienia tokenów, nie wykonuje wdrożeń; wychodzi z kodem 1, jeśli warunki nie są spełnione.

## Zweryfikowany E2E WAB — niezależny od release

Komentarze Plasmic MCP mają potwierdzony prawdziwy round trip w projekcie testowym mcp-e2e-test2. W jednorazowym izolowanym kontenerze z obrazu z merge a14e811bf6174d8053988fd3a6be9915c23799e2 wykonano na TEST projekcie: odmowę błędnego anchor UUID, create, duplicate idempotency, reply, edit-own, readback, resolve+history, final readback (8/8 PASS). Wątek testowy został pozostawiony zamknięty. To NIE jest deployment serwisu MCP z Coolify: aktywna produkcja wciąż wskazywała starszy image sha256:bd1b33731dfe3342166359e5df46d459eb2dde68b73525a28ada63f6c19d291b. Nie obchodź release HOLD.

## Harness Engineer read-only Coolify MCP socket-broker integrity gate (2026-11-19)

Before an operator changes the MCP wrapper/package or declares agent-level access ready, run:

```bash
python3 scripts/harness_coolify_readonly_mcp_layout.py
python3 -m unittest scripts/test_harness_coolify_readonly_mcp_layout.py
```

The preflight enforces the pinned `@masonator/coolify-mcp` module entry SHA256, root-owned package and wrapper, systemd `LoadCredential` (never inline token), `NoNewPrivileges`, `ProtectSystem`, dedicated 0600 Unix socket, and the `COOLIFY_MCP_REQUIRE_HUMAN=on` guard. It fails closed on drift without reading token values or modifying provider resources. The approved transport is the root-owned systemd/socat broker; the Hermes task accesses the agent-scoped Unix socket, **not** the package under `/opt` directly (its task sandbox denies that path).

Live proof on Ubuntu (2026-11-19): read-only preflight `PASS`, `get_version` Coolify 4.4.6, `list_services` 25 services, and native Multica ZARI-262 tool calls independently reviewed before that issue was closed. This is a read-only MCP admission result only; it does not clear the broader release HOLD, authorize a Coolify deploy, or replace immutable image provenance and authenticated production E2E. Do not create another release controller or recurring job for this preflight.
