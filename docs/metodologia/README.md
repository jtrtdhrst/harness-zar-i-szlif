# Metodologia — notatki robocze

> **Status:** szkic roboczy · **Cel:** wspólnie wypracować metodologię, a nie z góry narzucać gotowe reguły.
>
> Ta strona jest miejscem na surowe pomysły, obserwacje, przykłady, decyzje i ich ewolucję. Treść w sekcji „Notatnik” nie stanowi zatwierdzonej polityki ani instrukcji dla agentów.

## Notatnik

<!-- Tutaj dopisujemy pomysły chronologicznie. Nie trzeba ich od razu porządkować. -->

### 2026-11-21 — początek

- **Myśl / pytanie:** 
- **Przykład z praktyki:** 
- **Co chcę osiągnąć:** 

## Tezy do sprawdzenia

| ID | Teza | Jak ją zweryfikować? | Status |
| --- | --- | --- | --- |
| T-001 | *(do uzupełnienia)* | *(do uzupełnienia)* | szkic |

**Statusy:** szkic → testowana → potwierdzona / odrzucona.

## Zasady metodologii

Tutaj przenosimy jedynie tezy świadomie zaakceptowane jako zasady.

| ID | Zasada | Dlaczego? | Przykład zastosowania |
| --- | --- | --- | --- |
| — | *(do uzupełnienia)* | — | — |

## Proces w praktyce

1. **Sygnał / problem:** co uruchamia działanie?
2. **Diagnoza:** jakie fakty trzeba potwierdzić?
3. **Decyzja:** według jakich kryteriów wybieramy rozwiązanie?
4. **Wykonanie:** kto lub co wykonuje działanie?
5. **Weryfikacja:** jaki mierzalny wynik świadczy o sukcesie?
6. **Wnioski:** co zachować, poprawić lub odrzucić?

Ten schemat jest tylko szablonem do dalszej pracy, nie ustaloną metodologią.

## Cykl produkcyjny — docelowy standard (2026-11-21)

**Cel:** doprowadzić zmianę do faktycznie działającej produkcji, a nie do samego zadania, PR, zielonego CI albo zdrowego kontenera. To kontrakt docelowy; opis nie potwierdza, że wszystkie usługi mają już automatyczne wdrożenia.

```text
Jeden task → CHO (priorytet, zakres i właściciel)
→ Harness Engineer (jedna implementacja, jeden branch/PR na task)
→ CTO (niezależny przegląd dokładnego SHA)
→ merge do właściwego main + zaufane CI
→ obraz OCI z niezmiennym digestem / dopuszczony artefakt
→ COO + kontrola release (konkretny zasób UUID, grant, HOLD, rollback)
→ wdrożenie przez istniejący kontroler / Coolify
→ odczyt faktycznego SHA + digestu uruchomionego kontenera
→ Production QA: dodatnie i ujemne uwierzytelnione E2E
→ DONE wyłącznie przy pełnych dowodach; w przeciwnym razie STOP / rollback.
```

**Bramki obowiązujące na każdej zmianie:**

1. **Identyfikacja:** jedno natywne zadanie Multica; CHO wskazuje repo, usługę, zależności, kryterium akceptacji i istniejący branch/PR. Zero duplikatów.
2. **Implementacja:** Harness Engineer rzeczywiście uruchamia narzędzia, testy i CI. Dla danego taska jedna aktywna gałąź/PR; naprawa błędów na tym samym PR, a nie nowym wątku.
3. **Niezależny review:** CTO ocenia konkretny commit (SHA), testy, zmianę uprawnień, sekrety i ryzyko. Sam merge, komentarz agenta albo zielony mock nie stanowią zatwierdzenia.
4. **Budowanie:** merge do właściwego `main` uruchamia zaufane CI; obraz jest identyfikowany przez `sha256` digest, a source SHA i build attestation muszą odpowiadać dokładnie kandydatowi. Dla produktu osobna istniejąca ścieżka `main → validate-product → ci-approved → Coolify`; nie wolno zastępować jej przypadkową gałęzią.
5. **Autoryzacja release:** COO / autoryzowany operator dopuszcza konkretny Coolify UUID, zgodny ze spisem usług i polityką. Status `HOLD`, nieaktualny checkout, niezgodny source-range, brak per-UUID grant albo podpisanej atestacji blokują wdrożenie; żadnego zbiorowego usuwania blokad.
6. **Wdrożenie:** wyłącznie jeden istniejący kontroler transportu danej usługi. Coolify musi uruchomić zatwierdzony artefakt, nie niezweryfikowany `latest`. Zapisać deployment ID, czas, source SHA, OCI digest i poprzedni działający digest.
7. **Produkcyjne QA:** odczyt rzeczywistego obrazu/kontenera i rewizji z produkcji, health oraz prawdziwe dodatnie i ujemne E2E (w tym MCP/browser, odpowiedzi bez uprawnień, izolacja agentów). Sprawdzić możliwość odtworzenia poprzedniej wersji.
8. **Wynik:** `PRODUCTION_VERIFIED` / `done` dopiero po zgodności source SHA, digestu, Coolify i E2E. Niepowodzenie → zatrzymanie promocji, rollback do potwierdzonego artefaktu i ponowny readback; `BLOCKED` z jednym konkretnym błędem i dowodem. Nie przesuwać baseline tylko z powodu merge lub zdrowego kontenera.

**Osobne ścieżki:** Harness (wiele niezależnych MCP/Compose, każdy własny UUID i HOLD) oraz Product (własne `ci-approved` i testy panelu). `main` jest gałęzią integracji, nie uniwersalnym wskaźnikiem tego, co uruchomiono na produkcji. Dokumentacja bez zmian runtime może dostać akceptację `SOURCE_ONLY`, ale nie status produkcyjnego wdrożenia.

**Zapis dowodów:** w istniejącym issue Multica: task, PR, reviewed SHA, wynik CI, digest, grant/autoryzacja, Coolify UUID i deployment, rzeczywisty runtime SHA/digest, dodatnie/ujemne E2E, rollback oraz końcowy status. **RepoWise = fakty z aktualnego kodu i decyzje** (wymagane indeksowane SHA równe bieżącemu GitHub main). **Hindsight = zweryfikowane doświadczenie wykonawcze**, nie substytut kodu ani dowodów produkcyjnych.

**Źródła normatywne do weryfikacji:** `docs/architecture/HARNESS-DELIVERY-CONTRACT.md`, `docs/RELEASE-POLICY.md`, `ops/release-lanes.json`, `scripts/harness_native_delivery.py`, `scripts/harness_release_admission.py` oraz aktualne konfiguracje GitHub CI i Coolify. Zawsze sprawdzić na bieżąco — ta notatka nie nadaje uprawnień do deploymentu.

## Przykłady i kontrprzykłady

| Sytuacja | Działanie | Wynik / dowód | Lekcja |
| --- | --- | --- | --- |
| *(do uzupełnienia)* | — | — | — |

## Decyzje i historia zmian

| Data | Decyzja | Uzasadnienie | Zmienione sekcje |
| --- | --- | --- | --- |
| 2026-11-21 | Dopisano docelowy cykl produkcyjny i mierzalny warunek DONE | Kontrakt source → CI → immutable digest → Coolify → E2E albo rollback, bez deklarowania gotowego autodeploy | Cykl produkcyjny |
| 2026-11-21 | Utworzono miejsce do budowania metodologii | Oddzielenie surowych notatek od zatwierdzonych reguł | Wszystkie |

---

**Zasada redakcyjna:** zachowujemy pierwotne notatki, a tezy, które przeszły weryfikację, przenosimy do „Zasad metodologii”. Każda istotna zmiana pozostaje w historii Git.
