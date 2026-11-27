# Autodeploy MCP — kontrakt wykonawczy i produkcyjne E2E

Stan na 20.11.2026. Jedyna natywna ścieżka wdrażania obrazów Harness: istniejący **`harness-image-delivery.timer` → `harness-image-delivery.service` → `scripts/harness_native_delivery.py`**. Nie uruchamiać drugiego kontrolera ani timera.

## Przepływ bez ręcznego uruchamiania buildu

1. PR przechodzi niezależny review dla dokładnego HEAD; zatwierdzony merge trafia na Harness `main`.
2. Operatorowy synchronizator aktualizuje dokładny checkout `/var/lib/harness-image-delivery/checkout` oraz `source-range.env`. Kontroler sprawdza, że `origin/main == HEAD == HARNESS_SOURCE_SHA`.
3. Dla usług z `promotion_state: auto_main` i `auto_deploy_expected: true` (sześć MCP: emailens, mantic, plasmic, playwright, supabase, ubuntu) autoryzacją wydania jest merge do trusted `main`. Kontroler sam pobiera exact main, buduje obraz lokalnie z tego SHA i promuje po weryfikacji digestu, health i źródłowego SHA. Nie ma per-merge request/grant. Usługi `hold` nadal wymagają root-owned request/grant i niezależnego review.
4. Workflow `.github/workflows/mcp-images-ghcr.yml` (PR #186) buduje sześć źródłowych obrazów MCP na zaufanym `main`, publikuje `ghcr.io/miloszspyrka-code/harness-<service>:sha-<FULL_SHA>` i zapisuje niezmienny digest. Niczego nie wdraża do Coolify.
5. Po niezależnej autoryzacji wydania `--mode deploy --auto` sprawdza request, grant i wszystkie bramki polityki. Istniejąca podpisana atestacja CI jest weryfikowana i używana. **Jeśli jej nie ma**, kontroler:
   - pobiera **wyłącznie** obraz `ghcr.io/miloszspyrka-code/harness-<service>@sha256:<APPROVED_DIGEST>` (bez drugiego buildu na VPS),
   - porównuje `RepoDigests` i etykietę źródłowego SHA z autoryzowanym `request.image_digest`,
   - uruchamia `harness_local_ci_attest.py` według root-owned allowlisty bez uprawnień roota,
   - weryfikuje podpis HMAC i ponawia dopuszczenie do promocji,
   - uruchamia istniejący transport Coolify, kontrolę SHA/digest/health oraz rollback w razie awarii.
6. Dopiero pełne **produkcyjne MCP E2E** (`initialize`, `tools/list`, rzeczywista akcja oraz odmowa bez autoryzacji) potwierdza sukces zadania. Odczyt konfiguracji, `running:healthy`, PR i test jednostkowy nie są wystarczające.

**Fail closed przed jakimkolwiek buildem:** brak request/grantu, niezatwierdzony SHA, inny UUID, brak root-owned polityki CI dla usługi, inny repo/key, zmiana źródła, brak zatwierdzonego digestu GHCR. **Fail closed przed deployem:** digest niezgodny, brak testów, błędny podpis, zły SHA lub nieudany smoke. Stan produkcji pozostaje bez zmian; nie nadpisywać danych ani nie odblokowywać HOLD przez zgadywanie.

## Ważny stan realny

- Auto-main buduje lokalnie z exact `main`, bo GitHub App nie ma `packages:read` i nie może pobrać prywatnego obrazu z GHCR. Workflow GHCR pozostaje niezależną walidacją/buildem, nie ścieżką wdrożenia.

- Mapa aktywnych usług Compose/Git znajduje się na PR #182 w `ops/mcp-autodeploy/routes.json`. To tylko mapa; nie jest triggerem deploymentu. Przestarzały `zar-i-szlif-mcp-host` nie powinien być aktywnym celem.
- Na VPS root-owned `/etc/paperclip-gitops/harness-ci-policy.json` zawiera aktualnie **tylko `ubuntu-mcp`**; testy innych usług trzeba niezależnie zdefiniować i sprawdzić przed aktywowaniem autoprepare.
- Historyczny grant dla `ubuntu-mcp` jest wygasły. Zmiana kodu nie tworzy nowej zgody i nie usuwa obowiązku niezależnego przeglądu.
- Część Compose (np. `cloudflared-mcp` i zewnętrzny `repowise-mcp-runtime`) korzysta z upstream obrazów, a nie z repozytoryjnego Dockerfile. Te obrazy wymagają osobnego zatwierdzonego, niezmiennego digestu.
- Testy kodu nowej ścieżki to **80/80 PASS**, pełne regresje **288 PASS (2 skipy środowiskowe)** w izolowanym środowisku Ubuntu; nie zastępuje to testu następnego automatycznego wdrożenia na produkcji.
- Ta poprawka wymaga niezależnego exact-head review, zielonego CI po merge, instalacji sprawdzonych bajtów przez operatora i nowej zmiany źródłowej z pełnym produkcyjnym E2E. Do tej chwili nie oznaczać Compose autodeploy jako DONE.

## Kontrola operatora

```bash
systemctl show harness-image-delivery.timer -p ActiveState -p UnitFileState
git -C /var/lib/harness-image-delivery/checkout rev-parse HEAD
git -C /var/lib/harness-image-delivery/checkout ls-remote origin refs/heads/main
journalctl -u harness-image-delivery.service -n 45 --no-pager
python3 /usr/local/libexec/harness_native_delivery.py \
  --mode plan --auto-main \
  --repo /var/lib/harness-image-delivery/checkout \
  --attestation-key /etc/paperclip-gitops/harness-attestation.key \
  --state-dir /var/lib/harness-image-delivery/delivery
```

Wydanie zaliczone E2E dopiero po zebraniu: `approved_PR_head`, `source_main_SHA`, `trusted_CI`, `auto_timer_run`, `image_manifest_digest`, `Coolify_UUID`, `live_container_image_ID`, `live_revision_SHA`, `MCP_functional_E2E`, `rollback_verified`. Jeśli którykolwiek etap nie ma dowodu, status BLOCKED, nie SUCCESS.

## Testy i cofnięcie

Testy jednostkowe z repo:

```bash
python3 -m unittest discover -s scripts -p 'test_harness_native_delivery.py' -v
python3 scripts/check-release-lanes.py --self-test
```

Niezależny reviewer sprawdza dokładny blob skryptu i negatywne przypadki przed instalacją w `/usr/local/libexec/`. Przed zmianą zapisać root-private kopię i SHA256, a po instalacji sprawdzić identyczny SHA256 i wykonać pełny test następnego automatycznego wydania. W razie regresji odtworzyć poprzedni skrypt, nie odtwarzać usuniętego legacy timera panelu ani nie uruchamiać równoległego deployera.

## Jedna ścieżka budowania obrazu

Nie uruchamiać dwóch builderów. PR #186 odpowiada za GitHub-hosted source-build i publikację do GHCR; istniejący root-owned Harness controller zużywa **pinned digest** z GHCR i prowadzi wyłącznie autoryzowaną promocję. Stary lokalny `--mode prepare` pozostaje jako jawna ścieżka serwisowa, nie jest odpalany przez `--mode deploy --auto`. Zgodność tagu `sha-<SHA>` ani samej etykiety revision nie wystarcza: podmieniony tag nie może zmienić żądanego manifest digest. Repozytorium musi udowodnić trusted-main run dla danego obrazu; bez tego E2E i provenance pozostają NIEPOTWIERDZONE.

Nie zmieniać tego runbooka w deklarację wykonania 13 deploymentów bez prawdziwych wdrożeń, autoryzacji oraz testów funkcjonalnych.
