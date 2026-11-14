# IWDT/light-sleep-transitie op ESP32 ECO3 — voorstel v2, met twee-core-modelresultaten

Versie 2, na de tegenreview. Alles hieronder komt uit broncode (ESP-IDF 6.0.3),
de exacte uitgerolde ELF en een nieuw cycle-gestept twee-core-hostmodel.
Niets is op silicium gereproduceerd. Kosten in cycles zijn **parameters**, geen
metingen. Het model is geen Xtensa-emulator.

Wat v2 anders doet dan v1: de handler-aanname "stage0 vóór pending" is
vervangen door de echte volgorde uit `highint_hdl.S`; het model heeft beide
handlerhelften, de volledige `sync/app/pro`-synchronisatie, het (un)mappen van
CPU1's interrupt, losse registerwrites, de gedeelde WPROTECT en timerverloop;
het voorstel is aangepast op twee punten die het model blootlegde (§5).

---

## 1. Drie dingen die uit elkaar gehouden moeten worden

1. **De oorspronkelijke SDK-race** (incident 2026-11-01 15:56 UTC): in
   `esp_int_wdt_livelock_workaround(false)` wordt `max=0` gezet terwijl de
   hardware nog stage0=40 ticks heeft; één expiry in dat venster → panic. De
   dump plaatst de PC precies daar. Sterke aanwijzing, geen bewijs (geen
   timerregisters in de dump). **Het model reproduceert deze klasse**: de
   originele SDK-code panict in alle 32 parameter-combinaties
   (`stage0=40 max=0 counter=0` bij de eerste expiry).
2. **Een tekortkoming in onze reparatie** (de uitgerolde patch): de
   verificatie `pending==0 && stage0==1600` kijkt naar de verkeerde kant van
   het rendezvous (§3). Het model laat de stille verkeerde eindtoestand zien.
3. **Een SDK-eigen marge in het rendezvous** die geen van de C-varianten
   raakt, maar die door de slaapmodus `max=0` (upstream én wij) van
   zelfherstellend in fataal verandert (§4). Dit is het punt dat de
   tegenreviewer aandroeg; het model bevestigt het.

## 2. Wat de handler werkelijk doet (`highint_hdl.S`, 6.0.3)

| stap | core | wat | regel |
|---|---|---|---|
| a | CPU1, 1e entry | `app++`, `sync[1]=1`, wacht `sync[0]&&sync[1]` | 389-406 |
| b | beide | delay 480–2160 cycles (afhankelijk van flash/PSRAM-mode) | 435-452 |
| c | CPU1 | `app!=2` → unmap eigen TG1-interrupt, exit (`sync[1]=0`) | 462-466, 509-527 |
| d | CPU0 | `pro++` per rondje; zolang beide sync gezet: opnieuw delay; daarna bij `pro>=2` → remap CPU1's interrupt, **wacht tot CPU1 opnieuw binnen is** | 467-500 |
| e | CPU1, 2e entry | `app++` (=2), `sync[1]=1`, wacht `sync[0]&&sync[1]` | 389-406 |
| f | CPU0 | ziet `sync[1]` → **`wdt_clr_intr_status`: WPROTECT open, INT_CLR, WPROTECT dicht**, exit (`pro=0`, **`sync[0]=0`**) | 505, 509-527 |
| g | CPU1 | `counter++`, delay, **`wdt_feed`: WPROTECT open, leest `max` live, stage0=`1600/(max+1)`, stage1, FEED, WPROTECT dicht**, exit | 410-416, 509, 92-117 |

Twee gevolgen:

- INT_RAW wordt gewist in (f), vóór CPU1's registerwrites in (g). Een C-check
  "pending==0" bewijst dus niets over (g).
- (e)→(f): CPU1 moet `sync[0]` lezen vóórdat CPU0 het in (f) wist. CPU0's pad
  tussen "ziet sync[1]" en "`sync[0]=0`" is vier APB-toegangen plus ~15
  instructies; CPU1's pad tussen "`sync[1]=1`" en "leest sync[0]" is 5–8
  instructies. Dat is de marge uit §4.

## 3. De uitgerolde patch in het model

Trace (transitie op CPU0; APB=4, delay=2160, efuse=60; modelcycles):

```
   1    stage0 expiry; CPU1 en CPU0 betreden handler
2201    CPU1 1e entry klaar: unmap, exit
4371    CPU0 pro=2 → remap CPU1; 4383 CPU1 2e entry
4427    CPU0: INT_CLR ; 4441 CPU0 exit (sync[0]=0)      ← CPU1 zit nu in delay (g)
6489    C: WPROTECT open ; stage0=1600 ; stage1 ; FEED ; close
6547    C: rsil 5 ; INT_RAW=0 ; stage0=1600  → "schoon", commit
6597    CPU1 (g): stage0=40 (las max=39)
6617    CPU1: FEED
6623    C: WPROTECT open  (commit: max=0 is al geschreven)
6624    CPU1: WPROTECT dicht                               ← gedeelde register
6637    C: stage0=1600  BLOCKED
6655    C: stage1       BLOCKED
6667    C: FEED         BLOCKED
        eind: stage0=40, max=0  → volgende expiry (20 ms) = panic-route
```

Sweep (expiry-offset −(3·delay+4000) … transitielengte+2000, stap 1 cycle;
16 combinaties APB∈{4,10} × delay∈{480,2160} × efuse∈{60,400} × core∈{0,1},
zonder extra CPU1-stall): **7/16 runs met 116 offsets in totaal eindigen stil
in `stage0=40, max=0`; allemaal met de transitie op CPU0.** Geen panic binnen
het modelvenster (de 20 ms-expiry valt erbuiten), geen deadlock. Op CPU1 geen
fouten: daar zijn wij de core die in (g) voedt, en `rsil 5` houdt die helft
buiten onze commit.

Hoe smal het venster fysiek is, hangt af van cycle-tellingen die het model
niet kent. Het bestaan ervan volgt uit de registerdeling, niet uit de timing.

## 4. De SDK-marge in het rendezvous (bevinding van de tegenreviewer, bevestigd)

Model: extra stall `S` voor CPU1 tussen `sync[1]=1` en zijn lezing van
`sync[0]` (stap e). Transitie op CPU0, uitgerolde patch, delay=2160:

| APB-kost | S waarbij CPU1 `sync[0]` mist |
|---|---|
| 4 | ≥ 36–40 cycles |
| 10 | ≥ 56–60 cycles |

CPU1's werkelijke instructiereeks daar is 5–8 cycles, op level 5, IRAM, DRAM,
niet onderbreekbaar. Er is dus ~30–50 cycles **onverklaarde** stilstand nodig.
Of de hardware die ooit levert (DRAM-arbitrage, iets anders) weet het model niet.

Gevolgen als het gebeurt:
- CPU1 spint op level 5 op `sync[0]`. In normale modus (`max=39`) betreedt
  CPU0 bij de volgende expiry de handler, zet `sync[0]=1` en CPU1 herstelt.
  Zelfherstel na ≤ 20 ms.
- Na een commit `max=0` (upstream-origineel, uitgerolde patch én voorstel)
  komt er nooit meer een handler: CPU1 blijft bevroren. CPU0 loopt vervolgens
  vast in `esp_ipc_isr_stall_other_cpu()` → IWDT op CPU0 → panic. In het model:
  `bad_final` met `cpu1{lvl5, in_handler, pc3}` in **alle** varianten bij
  S=40/APB=4.
- Onze pre-commit `reconfigure_ticks(1600)` (patch én voorstel) rekt het
  zelfherstel op van 20 ms naar 800 ms als de miss vóór de commit valt:
  CPU1 800 ms bevroren, daarna herstel, geen panic. Upstream-origineel heeft
  in dat geval geen herstel (schrijft 1600 pas samen met `max=0`).

Dit is niet door C-code op te lossen zonder `highint_hdl.S` aan te raken.
Een .S-fix zou zijn: CPU0 wacht in (f) op een bevestiging van CPU1 ("ik heb
`sync[0]` gelezen", bv. `app==2 && counter` opgehoogd) vóór `sync[0]=0`; of
CPU1 herleest met een time-out. Dat valt buiten dit voorstel; het hoort bij
Espressif. Het incident van 15:56 past hier **niet** op: CPU1 stond in de
idle-WFI, niet op level 5 in de handler.

## 5. Voorstel (v2)

### 5.1 Principe: settle-and-verify vóór de commit

1. Oude modus, lange stage, verse feed (`reconfigure_ticks(1600, 3200)`).
2. Eerste blik onder `rsil 5`: INT_RAW==0 en stage0==1600. PS herstellen.
3. **Settle**: spin ≥ `T_settle` CPU-cycles met hoge IRQs aan. Een CPU1-helft
   die al voorbij (f) was, rondt (g) af en schrijft daarbij stage0=40 (`max`
   is nog 39) — dus zichtbaar.
4. Tweede blik onder `rsil 5`: INT_RAW==0 en stage0==1600. Anders → retry.
   Slaagt dit, dan is geen handlerhelft meer onderweg en kan er geen nieuwe
   starten: de laatste stage0=1600-schrijf was de onze, met feed, hooguit
   `T_settle+ε` geleden; en CPU1 kan zonder onze deelname aan het rendezvous
   geen WDT-register schrijven (stap e wacht op `sync[0]`).
5. Commit (`max`, dan stage0/stage1/feed) onder hetzelfde masker.
6. Post-commit-controle onder masker (zie 5.3).

Er is geen moment waarop stage0=40 en `max=0` tegelijk gelden, ook niet
transiënt.

### 5.2 Modelresultaten voor het voorstel

Zelfde sweep als §3. Zonder extra stall (S=0):

| settle (cycles) | runs met fout / 16 | wat er misgaat |
|---|---|---|
| 0 | 7 (106 offsets) | uitgestelde CPU1-feed bereikt de commit → **post-check → `abort()`**, nooit stil |
| 3000 | 0 | — |
| 5000 | 0 | — |
| 8000 | 0 | — |
| 20000 | 0 | — |

De drempel ligt dus tussen 0 en 3000 bij delay=2160 (de feed landt ≤ ~2500
cycles na INT_CLR in dit model). 8000 is ~3× die waarde; 20000 verandert
niets meer. **Welke garantie hangt aan de grens:** alleen stap 4's
"geen handlerhelft meer onderweg". Valt de grens te kort, dan vangt stap 6
het op met een zichtbare `abort()`, niet met een stille verkeerde toestand.
De grens is dus een aanname over *beschikbaarheid*, niet over *veiligheid*.

Met S=40 (sync-miss, §4): 8/16 runs fout in alle settle-waarden — identiek aan
de uitgerolde patch en aan het SDK-origineel. Zie §4; niet door dit voorstel
te verhelpen.

Andere core echt vastgelopen (neemt nooit interrupts): uitgerolde patch en
voorstel eindigen beide in `STAGE1_RESET` zodra er een expiry in het venster
valt, nooit in eindeloos voeden of deadlock. De retry-lus onderdrukt de
watchdog dus niet in dit scenario.

### 5.3 Twee wijzigingen t.o.v. v1, beide door het model afgedwongen

**(a) Retry-bound in tijd, niet in pogingen, en groter dan de hele
watchdogperiode.** v1 had 16 pogingen; het model liet zien dat een pending
INT_RAW legitiem ~2×delay (≈4300 cycles) blijft staan terwijl CPU0 wacht om
CPU1's interrupt te remappen (stap d) — 16 × ~80 cycles was te kort en gaf
3241 onterechte aborts op CPU1. Een bound van 1<<20 cycles bleek óók te kort:
bij een sync-miss vóór de commit herstelt het systeem zich na 800 ms (§4), en
die 800 ms vallen binnen onze lus. De bound moet daarom > stage0+stage1
(2,4 s) zijn: **1<<30 cycles** (~4,5 s @240 MHz). Hij bestaat alleen om
eindeloos voeden te stoppen in een toestand die deze code niet begrijpt.

**(b) Post-commit-controle moet alle drie writes dekken, niet alleen stage0.**
De tegenreviewer heeft gelijk dat stage0==doel niet bewijst dat stage1 en
FEED geaccepteerd zijn. `TIMG_WDTWPROTECT_REG` is R/W
(`soc/esp32/register/soc/timer_group_reg.h:349`). Voorstel: de commit niet
via `reconfigure_ticks()` maar expliciet:

```c
wdt_hal_write_protect_disable(&iwdt_context);
wdt_hal_config_stage(&iwdt_context, WDT_STAGE0, target, WDT_STAGE_ACTION_INT);
wdt_hal_config_stage(&iwdt_context, WDT_STAGE1, IWDT_STAGE1_TIMEOUT_US, WDT_STAGE_ACTION_RESET_SYSTEM);
wdt_hal_feed(&iwdt_context);
bool accepted = REG_READ(TIMG_WDTWPROTECT_REG(1)) == TIMG_WDT_WKEY_VALUE   /* nobody closed it meanwhile */
             && flue_iwdt_stage0_ticks() == target
             && REG_READ(TIMG_WDTCONFIG3_REG(1)) == IWDT_STAGE1_TIMEOUT_US;
wdt_hal_write_protect_enable(&iwdt_context);
```

Als WPROTECT nog open staat ná onze drie writes, heeft niemand het tussentijds
gesloten, en zijn alle drie geaccepteerd (openen door een ander blokkeert ons
niet). Nog te controleren: dat het register werkelijk de geschreven sleutel
teruggeeft (datasheet zegt R/W; niet gemeten). Dit staat **niet** in de
gemodelleerde versie (die gebruikt `reconfigure_ticks` + stage0-check); het
model zegt dat de commit na stap 4 onbetwist is, dus de controle is een
vangnet voor modelfouten, geen dragend onderdeel.

### 5.4 Code

`proposal_iwdt_transition.c.inc` (naast dit document) is wat het model draaide,
op (a) na: het model liep met 1<<20, het bestand heeft nu 1<<30. Het enige
verschil in uitkomst zit in de S=40/CPU1-gevallen uit §4 (abort → herstel na
800 ms). (b) is nog niet in het bestand verwerkt.

Tick-pad (in `tools/patch_iwdt_transition.py` wordt `flue_iwdt_update(false, true)`
vervangen door `flue_iwdt_tick()`):

```c
static void ESP_SYSTEM_IRAM_ATTR flue_iwdt_tick(void)
{
    portENTER_CRITICAL_SAFE(&s_iwdt_configure_lock);
    if (soc_has_cache_lock_bug() && s_flue_livelock_enabled) {
        esp_int_wdt_set_livelock_params(CONFIG_ESP_INT_WDT_TIMEOUT_MS);   /* counter reset: as original */
        reconfigure_ticks(esp_int_wdt_livelock_get_feed_stage0_ticks(), IWDT_STAGE1_TIMEOUT_US);
    } else {
        reconfigure_ticks(IWDT_STAGE0_TIMEOUT_US, IWDT_STAGE1_TIMEOUT_US);
    }
    portEXIT_CRITICAL_SAFE(&s_iwdt_configure_lock);
}
```

In normale modus is dit byte-voor-byte de originele SDK-tick; de vlag
voorkomt alleen dat een tick tijdens de slaapmodus `max=39`/stage0=40
terugschrijft (de echte SDK-race die de uitgerolde patch al dichtte). Het
tick-pad hoeft niet te maskeren: het wijzigt `max` niet, de lock ordent het
tegen een modewissel. Nog **niet** in het twee-core-model opgenomen.

### 5.5 Kosten

+`T_settle` per slaapingang en per ontwaken (33–100 µs bij 8000 cycles),
binnen de bestaande `s_config.lock`-sectie. Bij `enable==true` is de settle
strikt genomen overbodig (`max=0` → geen handler mogelijk) en kan worden
overgeslagen; niet gedaan om één pad te houden. Een tick-ISR op de andere
core die de lock wil, spint maximaal `T_settle` extra.

## 6. Het model (`iwdt_dualcore_model.py`)

- Draait de **echte C** van (a) SDK-origineel, (b) uitgerolde `.c.inc`,
  (c) voorstel; `reconfigure_ticks` en de ECO3-helpers zijn uit de echte
  (gegenereerde) bronnen geëxtraheerd.
- Beide handlerhelften als op-machines uit de assembly (§2), met
  `sync[2]/app/pro`, (un)map van CPU1's interrupt, elke registerwrite apart,
  WPROTECT als gedeeld last-writer-wins-register (writes op stage/feed
  worden geblokkeerd als het dicht is), INT_RAW edge-getriggerd op
  `cnt >= stage0`, stage1-reset op `cnt >= stage0+stage1`.
- Delivery: INT_RAW && gemapt && `PS.INTLEVEL<4`; `counter>=max` → PANIC
  (de `bltu a0,a5`-route). Een core in de handler zit op level 5.
- Parameters: APB-toegang, handler-delay, efuse-leeskosten in
  `soc_has_cache_lock_bug()`, extra CPU1-stall bij stap e, TICK (500
  modelcycles; fysiek 120000 @240 MHz — zie beperkingen), andere core vast.
- Per scenario: expiry-offset t.o.v. transitiestart, stap 1 cycle over
  −(3·delay+4000) … transitielengte+2000. Uitkomst: ok / PANIC /
  STAGE1_RESET / DEADLOCK (modeldeadline) / ABORT / BAD_FINAL
  (stage0≠1600 ∨ max≠0 ∨ INT_RAW ∨ core in handler ∨ WPROTECT open, na
  12000 cycles uitlopen).
- 7 varianten × 32 grid + stall-probe + hung-probe; ruwe resultaten in
  `model-results.json`, log in `model-run.log`, trace-modus per offset.

**Beperkingen (eerlijk):**
- Cycle-kosten zijn aannames. De *volgorde*-eigenschappen (§3, §4) hangen
  er niet van af; de *drempels* (settle ≥ ~2500, stall ≥ 36–60) wel.
- TICK=500 maakt een 20 ms-stage 20000 cycles i.p.v. 4,8 M. Daardoor is een
  expiry tijdens de transitie in het model veel waarschijnlijker dan fysiek,
  wat conservatief is voor het vinden van interleavings, maar de absolute
  aantallen ("116 offsets") zijn geen kansen.
- DRAM-zichtbaarheid tussen cores is onmiddellijk gemodelleerd; `memw` per
  core. APB-arbitrage tussen twee cores op TIMG1 is niet gemodelleerd
  behalve als vaste kosten.
- `abort()` is een modeluitkomst; het gedrag van de panic-handler met
  vastgehouden sleep-/watchdoglocks is niet gemodelleerd.
- Het tick-pad en de `enable==true`-richting zijn niet in dit model
  opgenomen (wel in de bestaande `tools/test_iwdt_transition.py`, die het
  oude atomaire handlermodel heeft en dus §3 niet ziet).
- De IPC-stall van CPU1 ná de transitie is niet gemodelleerd; het model stopt
  bij de terugkeer uit de transitie plus uitloop.

## 7. Open vragen voor de tweede reviewer

1. §4: is de 5–8-cycle-reeks van CPU1 tussen `s32i sync[1]` en `l32i sync[0]`
   op een LX6 onder enige omstandigheid 30–50 cycles te vertragen (DRAM-bank-
   conflict met CPU0, debug-module, iets anders)? Zo nee, is §4 theoretisch.
   Zo ja, dan is dit een upstream-melding waard, los van onze patch.
2. §5.1 stap 4: klopt de claim "CPU1 kan geen WDT-register schrijven zonder
   ons" ook voor CPU1's *eerste* entry (stap a–c)? Die schrijft alleen de
   interrupt-matrix (unmap), geen WDT-register — graag tegencontrole op
   regels 462-466.
3. §5.3(b): geeft `TIMG_WDTWPROTECT_REG` de geschreven sleutel terug, of
   altijd de default? Datasheet zegt R/W. Als dit niet klopt, vervalt de
   read-back en blijft alleen stage0/stage1-lezing over (FEED onverifieerbaar).
4. §5.3(a): is 1<<30 (4,5 s feeden in een onbegrepen toestand, daarna abort)
   verdedigbaar, of wil je hier liever terugvallen op "stop met voeden en laat
   stage1 resetten" (= gewoon `return` zonder commit)?
5. De 800 ms-bevriezing van CPU1 bij een sync-miss vóór de commit (§4, derde
   punt): acceptabel als zeldzaam herstelpad, of reden om vóór stap 1 eerst
   te wachten tot INT_RAW==0 *zonder* te herprogrammeren (zodat een miss nog
   op de 20 ms-stage herstelt)? Dat laatste verlengt de transitie met tot
   ~20 ms in het zeldzame geval en verandert niets in het normale pad.
6. Modelkritiek: welke aanname in §6 zou, als hij fout is, §3 of §5.2 omver
   halen? Mijn eigen kandidaat: als APB-writes van twee cores naar TIMG1
   niet in programmavolgorde per core aankomen, klopt de WPROTECT-redenering
   in §3 en §5.3(b) niet meer.

## 8. Referenties (lokaal)

- SDK: `~/Library/Caches/esphome/idf/frameworks/6.0.3/components/esp_system/{int_wdt.c, port/soc/esp32/eco3_livelock_workaround.c, port/soc/esp32/highint_hdl.S}`; SHA-256-pins in `flue-monitor/tools/patch_iwdt_transition.py`.
- Uitgerolde patch: `flue-monitor/cmake/iwdt_transition.{cmake,c.inc}`, `flue-monitor/tools/{patch,test}_iwdt_transition.py`; kandidaat + ELF + disassembly: `flue-monitor/.cache/watchdog-diagnostics/693379f6eea4ccc7/`.
- Incident: `flue-monitor/.cache/watchdog-captures/incident-20261101T1556Z/`.
- Dit document, `proposal_iwdt_transition.c.inc`, `iwdt_dualcore_model.py`, `model-results.json`, `model-run.log`, `model-build/` (gegenereerde C per variant, binaries met trace-modus): allemaal in dezelfde map als dit bestand.
