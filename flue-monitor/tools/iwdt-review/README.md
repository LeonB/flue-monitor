# IWDT/light-sleep-transitie: experimenteel review-artifact (v3)

**Status: experimenteel. Niet uitgerold, niet in de build, niets geflasht of op hardware getest.**
Alles hier is een hostmodel van ESP-IDF 6.0.3 (`int_wdt.c`, `eco3_livelock_workaround.c`,
`highint_hdl.S`) plus een voorstel. Het is bedoeld voor een externe review.

## Inhoud

| bestand | wat |
|---|---|
| `iwdt_dualcore_model.py` | Bouwt en draait het twee-core-model. Draait de echte C van vier varianten. |
| `proposal_iwdt_transition.c.inc` | Voorstel v3 (kandidaat-vervanging van `cmake/iwdt_transition.c.inc`). |
| `proposal_v2_settle.c.inc` | Voorstel v2 (settle-and-verify), alleen als vergelijking. |
| `model-results.json` | Ruwe uitkomsten, 494 scenario-groepen. |
| `model-run.log` | Log van de sweep. Let op: de tick-regels met transitie op CPU0 zijn verouderd, de JSON is bijgewerkt. |

Varianten in het model: `sdk` (origineel), `deployed` (huidige patch), `v2settle`, `proposal` (v3).

Draaien: `JOBS=8 python3 iwdt_dualcore_model.py` (ruim 15 minuten). Eén run traceren:
`model-build/proposal_0 core=0 dir=0 stall_pc=15 stall_len=500 trace_exp=-6865`.
Parameters staan in de docstring van het script.

## Wat het model dekt (nieuw t.o.v. v2)

- Echte C per variant als coroutine op de gemodelleerde core, inclusief spinlock, `rsil 5` en kritieke niveaus.
- Beide handlerhelften op-voor-op uit de assembly, inclusief `sync/app/pro` en CPU1's interrupt-(un)map.
- `TIMG_WDTWPROTECT` als waarde (open zolang het de sleutel bevat), losse stage0/stage1/feed-writes, INT_RAW, timerverloop elke cycle, ook tijdens retries.
- FreeRTOS-tick op CPU0 op elke offset, uitgesteld achter lock en kritiek niveau.
- Beide richtingen: slaap in (`dir=0`) en wakker (`dir=1`).
- Stall van CPU1 na elke handlerstap (pc 2, 3, 5, 8, 15 t/m 20) met lengtes 40 t/m 20000 cycles. Pc 15 is direct na het lezen van `max`. De run loopt door tot ruim voorbij de post-check van CPU0.
- Een nooit-reagerende andere core.
- Invariant na elke cycle: I1 geen korte stage met `max=0`, I2 geen pending expiry met `counter>=max`, I3 stage1 altijd 3200. Daarnaast een eindtoestandscheck (stage0, `max`, stage1, INT_RAW, handler, WPROTECT, lock).

## Het voorstel v3

1. De transitie wacht onder `rsil 5` tot `INT_RAW==0` en de handlerstate `app==pro==sync[]==0`. `app` wordt in `highint_hdl.S` pas ná CPU1's stage0/stage1/feed gewist. Daarmee is "geen helft onderweg" een gelezen feit en geen tijdsaanname meer. De vaste settle-tijd van v2 vervalt.
2. Stage en feed worden geschreven met de WPROTECT-read-back (`flue_iwdt_write_stages`). De drie writes zijn bewezen geaccepteerd als WPROTECT nog onze sleutel bevat, en stage0 en stage1 worden daarna teruggelezen.
3. Commit: bij uitschakelen `max=0` terwijl stage0 al 1600 is; bij inschakelen eerst `max=39`, dan stage0=40.
4. `flue_iwdt_tick()` vervangt `flue_iwdt_update(false,true)` in de tick-hook.
5. Wachttijd begrensd in cycles (`1<<30`, langer dan stage0+stage1), geen pogingen. Daarna `abort()`.

Kost: het voorstel leest de handlerbookkeeping (`_lx_intr_livelock_sync/app/pro`). Die symbolen zijn lokaal in `highint_hdl.S` (`nm` op de uitgerolde ELF toont `d`, niet `D`). Ze liggen aaneengesloten na `max`. Er is dus een SHA-gepinde kopie van `highint_hdl.S` met drie `.global`-regels nodig, of een adres relatief aan `max` met een build-time `nm`-controle. Dat is nog niet gebouwd.

## Bewezen binnen het model

Dekking per variant: 1,9 tot 3,6 miljoen runs. Getallen zijn runs, geen kansen.

| eigenschap | sdk | deployed | v2 settle=0 | v3 |
|---|---|---|---|---|
| Sleep-ingang, expiry-sweep, S=0, beide cores | panic en stille fout | 14 stille fouten (`stage0=40, max=0`), alleen CPU0 | 53 zichtbare aborts | **0 fouten** |
| Wake-richting, expiry-sweep | alleen paniek vóór eerste feed | idem | idem | idem |
| Tick op elke offset, beide richtingen en cores | stille fout in 39939 runs (CPU1) | 0 | 0 | **0** |
| Tick x expiry, transitie op CPU1 | 259215 stille fouten | 0 | 0 | **0** |
| Invariant I1 (korte stage met `max=0`) | tot 20024 cycles | tot 20013 cycles | tot 118 cycles | **0 cycles** |
| I3 stage1 afwijkend | 0 | 0 | 0 | 0 |
| Nooit-reagerende andere core | n.v.t. | stage1-reset | stage1-reset | stage1-reset, nooit deadlock of eindeloos voeden |
| Eindeloos voeden / deadlock in model | 0 | 0 | 0 | 0 |

Toelichting:
- "Paniek vóór eerste feed" in de wake-richting: de plain-IWDT-expiry lag al vóór de transitie. Dat is een echte timeout, geen defect.
- Een stille eindtoestand (`BAD_FINAL`) komt bij v3 nergens voor. Elke fout van v3 is een zichtbare panic, reset of abort.
- Transitielengte v3: 261 tot 455 modelcycles. Max. tijd zonder voeding in een run: 46287 modelcycles, in de stall-scenario's.

## Bevindingen die het voorstel niet oplost of verslechtert

1. **Sync-miss in `highint_hdl.S` (alle varianten, ook SDK).** CPU1 mist `sync[0]` bij ≥36-40 extra stilstandcycles (APB=4) of ≥56-60 (APB=10) tussen `sync[1]=1` en zijn lezing. Het echte pad is 5-8 cycles. Resultaat: 265 van 319 runs eindigen in panic (sdk, deployed, v2) of stage1-reset (v3). Alleen op te lossen in de assembly.
2. **v3 voedt niet terwijl het wacht.** Bij een vastgelopen handlerronde loopt de oude 20 ms-stage door. Na 39 expiries (counter bereikt `max`) volgt een panic. De deployed patch en v2 voeden elke ronde met de 1600-stage en blijven daardoor langer in leven. Gemeten: stall van CPU1 in zijn delay-lus (pc 5, ook pc 8 en 15-17 bij 20000) van 8500-12000 cycles geeft 20 van 12742 runs panic bij v3 en 0 bij deployed. Stall van 20000 cycles vóór CPU1's feed (pc 18/19) geeft 10587 van 12742 panics bij v3. Let op de schaal: TICK is 500 modelcycles per watchdogtick, dus 20000 modelcycles staat gelijk aan één hele 20 ms-stage. Het zijn stalls van die orde in fysieke tijd, ver buiten wat de 7 instructies kunnen opleveren, maar het is wel een kwetsbaarheid die deployed niet heeft. De afweging is: v3 sluit het stille falen volledig, maar faalt eerder en zichtbaar bij een abnormaal trage handler.
3. **v2 (settle) kent abort-paden** bij stalls van 6000-12000 cycles (25-84 aborts). Dat is de reden dat v3 de settle-tijd heeft laten vallen.

## Hardware-timingaannames die overblijven (niet door het model te bewijzen)

H1. CPU1 blijft tussen `sync[1]=1` en zijn lezing van `sync[0]` korter dan ~36 cycles stilstaan (APB=4). Dit is een eigenschap van de SDK, geen aanname van v3.
H2. Een APB-write, gevolgd door `memw`, is voltooid voordat de latere `app`-write van dezelfde core in DRAM zichtbaar is voor de andere core. v3 leunt hierop: `app==0` moet betekenen dat stage0/stage1/feed zijn geland. Als een APB-write nog in een bridge hangt, is de redenering ongeldig. Dit is de belangrijkste nieuwe aanname.
H3. `TIMG_WDTWPROTECT_REG` geeft de geschreven sleutel terug bij lezen. De header zegt R/W (`timer_group_reg.h:349`). Niet gemeten. Als het register altijd de default teruggeeft, vervalt de read-back en blijft alleen de stage0/stage1-controle.
H4. De leesacties op INT_RAW, stage0 en stage1 (APB, vóór `memw`) tonen de huidige hardwaretoestand en niet een oudere.
H5. De commit (ongeveer 100 cycles) valt ruim binnen één watchdogperiode (800 ms voor de 1600-stage). Het model schaalt dit af (TICK=500); fysiek is de marge groter.
H6. De CPU1-stall van bevinding 2 komt niet voor. De lengte waarbij v3 faalt (8500+ modelcycles = ~8,5 ms bij TICK=500 geschaald naar de echte stage) is in de praktijk onbekend.
H7. De tweede core meldt zich binnen de wachttijd. Anders eindigt het in een zichtbare panic, reset of abort (model: nooit deadlock).

## Beperkingen van het model

- Kosten in cycles zijn parameters. De orde-eigenschappen (volgorde van writes, WPROTECT) hangen er niet van af. De drempels (sync-miss, stall) wel.
- APB-arbitrage tussen twee cores is een vaste kost. DRAM-zichtbaarheid tussen cores is onmiddellijk. Geen weak-ordering tussen APB en DRAM (zie H2).
- `abort()` is een modeluitkomst. Het gedrag van de panic-handler met vastgehouden sleep- en watchdoglocks is niet gemodelleerd.
- De run zonder expiry start met stage0=100000 en `max=0`. De invariant I1 meldt dan 96 cycles voor de eerste write. Dat is een artefact, geen defect.
- De IPC-stall van CPU1 na de transitie is niet gemodelleerd.
- Het bestaande `tools/test_iwdt_transition.py` heeft nog het oude atomaire handlermodel. Het ziet de WPROTECT-interleaving niet.

## Open vragen voor de reviewer

1. Is H2 houdbaar op een LX6 (volgorde van APB-write, `memw` en een daaropvolgende DRAM-write)? Dit is het enige punt waar v3 op leunt dat niet in het model zit.
2. Is het acceptabel dat v3 niet voedt tijdens het wachten (bevinding 2), of moet het tijdens het wachten alsnog de 1600-stage schrijven? Dat laatste heropent de WPROTECT-interleaving die in §Bewezen is gesloten.
3. Gebruiken we een SHA-gepinde kopie van `highint_hdl.S`, of liever relatieve adressering met `nm`-controle?
4. Moet de sync-miss (bevinding 1) bij Espressif gemeld worden? De sleep-ingang maakt hem fataal door `max=0`.
