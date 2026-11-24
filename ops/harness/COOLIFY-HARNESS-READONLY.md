# Harness Engineer — ograniczony dostęp Coolify MCP (ZARI-113 / ZARI-262)

## Zakres i architektura

Produkcyjna konfiguracja agenta **Harness Engineer** w workspace **Żar i Szlif** ma własny, agent-level MCP o nazwie `coolify-harness-readonly`. Stary workspace MCP `coolify` (token o szerokich uprawnieniach) pozostaje **disabled**. Połączenie nie nadaje uprawnień do wydań i nie znosi `HOLD`.

Protokół:

```
Hermes sandbox (Harness Engineer)
  -> /usr/bin/socat - UNIX-CONNECT:<role-profile>/coolify-mcp-readonly.sock
  -> systemd coolify-harness-readonly-mcp.service (User=multica-zar)
  -> per-connection @masonator/coolify-mcp@3.9.0, stdio
  -> root-owned systemd LoadCredential of Coolify token (abilities: ["read"])
  -> Coolify REST API http://127.0.0.1:8001
```

Socket jest uniksowy, nie nasłuchuje na TCP ani publicznym URL; należy do roli Harness, mode `0600`. Token jest pobierany jako **systemd credential**, nie jako wartość w argv, Multica MCP JSON, logach ani na dysku sandboxu. Wrapper odmawia działania bez `CREDENTIALS_DIRECTORY` i wymaganego użytkownika.

Natywne ustawienie agenta zapisane w Multica to:

```json
{"mcpServers":{"coolify-harness-readonly":{
  "command":"/usr/bin/socat",
  "args":["-","UNIX-CONNECT:/srv/multica-zar/.hermes/profiles/harness-engineer/coolify-mcp-readonly.sock"]
}}}
```

Nie dodawaj tokenu do powyższej konfiguracji. Nie włączaj dawnego workspace `coolify`.

## Instalacja operatora (nie wykonywać z niezatwierdzonego PR)

- Zainstaluj i zweryfikuj przypięte `@masonator/coolify-mcp@3.9.0` pod `/opt/multica-tools/coolify-harness-ro`. Nie używaj `latest`.
- Potwierdź, że `/root/coolify-secrets/coolify_api_token_readonly` jest root-only 0600 i że jego uprawnienia Coolify to dokładnie `["read"]`. Żaden token `root`, `write` ani `deploy` nie powinien być przekazywany do tej integracji.
- Zainstaluj z niezależnie zatwierdzonego SHA `scripts/coolify-harness-readonly-mcp.sh` do `/usr/local/libexec/coolify-harness-readonly-mcp.sh` (root:root 0755), a `ops/systemd/coolify-harness-readonly-mcp.service` do `/etc/systemd/system/` (root:root 0644).
- Wykonaj `systemctl daemon-reload`, `systemctl enable --now coolify-harness-readonly-mcp.service`. Zapisz SHA zainstalowanych plików i sprawdź `systemctl is-active`.
- Ustaw agent-level `mcp_config` w Multica (bez sekretów), po czym uruchom nową sesję agenta Hermes — sesje już otwarte nie odświeżają automatycznie katalogu MCP.
- Testuj `initialize`, `tools/list`, `tools/call` (`get_version`, `list_services`). Weryfikacja E2E musi zawierać **natywne** `issue.run-messages` z rzeczywistym `tool_use` i `tool_result` oraz niezależny odczyt.

## Dowody produkcyjne, 2026-11-19

Hostowa kontrola po aktualizacji systemd `LoadCredential`: serwer działa, gniazdo `0600`, `initialize` PASS, `tools/list` 46 narzędzi, `get_version` zwraca `4.4.6`. Użytkownik i właściciel socketu: `multica-zar`. Dodatkowy token w katalogu profilu agenta został usunięty.

Rzeczywisty run Harness Engineer `01a1f500-8168-740d-96e9-30a6e2629172` (ZARI-262): na serwerze Multica `issue.run-messages` seq 14–17 i 26–27 zawierają `tool_use/tool_result` dla `get_version`, `list_services`, `get_mcp_version`. Lista 25 usług zawiera Plasmic i Plasmic MCP. W tym runie nie było żadnego wdrożenia, zmiany ani restartu w Coolify.

Testy statyczne: `python3 -m unittest discover -s scripts -p 'test_coolify_harness_readonly_mcp.py' -v` — 6/6 PASS.

## Krytyczna granica produkcyjna

Nawet jeśli `tools/list` ujawnia nazwy `deploy` i `control`, token ma **tylko** `read`: Coolify blokuje wykonanie operacji zapisujących. `COOLIFY_MCP_REQUIRE_HUMAN=on` jest dodatkowym zabezpieczeniem, nie substytutem ograniczenia tokenu. Wydania muszą używać niezależnego, root-controlled mechanizmu atestacji/HOLD w ZARI-240 i wyraźnego uprawnienia do konkretnego UUID usługi. Stan ZARI-261 nie zmienia się od samego dodania MCP.

## Rollback

Wyłącz agent-level `coolify-harness-readonly` przez przywrócenie poprzedniego (pustego) `mcp_config`, uruchom nową sesję, następnie `systemctl disable --now coolify-harness-readonly-mcp.service`. Nie usuwaj ani nie unieważniaj współdzielonych tokenów i nie zmieniaj obrazów Coolify w ramach rollbacku tej integracji. Token wydany dla tego ograniczonego MCP można rotować osobno natywną funkcją Coolify, bez zmiany agent-level JSON.
