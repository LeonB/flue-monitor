# flue-monitor (plain ESP-IDF, not ESPHome/Arduino)

## 2026-11-16 persistent remembered dashboard sessions

Owner approved bounded persistent sessions instead of JWT: remembered sessions
survive OTA/reboot with fixed90day expiry, max8slots. Runtime+NVS store SHA256
hashes, never raw cookies; sessions_v1 snapshot360B (plus NVS overhead), bound
to the password credential hash. Credential replacement invalidates an old
snapshot even across power loss without a second NVS transaction. Logout,
rotation or eviction of a remembered slot must persist successfully before
reporting success; failure rolls runtime state back. Normal requests never
refresh cookies or write NVS. Volatile sessions still end at reboot. Monotonic
LRU use resets on reboot (restored slots initially tie); current-boot use picks
least recently used. Expired slots reused. Valid UTC required for remembered
session checks/new remembered login; boot awaits existing SNTP (same2026 floor
as tunnel TLS), and unsynced checks do not destroy stored sessions. No stack,
watchdog, display, settings or graph format changes. Login help now90days.

Host ASan/UBSan tests cover real SHA256/PBKDF2, eight durable slots plus eviction,
reboot/expiry/clock sync, durable logout, remembered-to-volatile rotation,
password binding, malformed snapshots, open/set/commit failures, hash failure,
and100requests without writes/cookie renewal. Actual HTTP2 adapter/auth passed
both gzip variants; login/OTA PSRAM failure tests cover clock503 and storage500.
Login-page, asset versions, BoschUI and settings-sync tests passed. IDF6.0.3
build1518912B,17088B OTA free; SHA256
5ccf698431f3d85c4d684a830667bffb3dc9adbca2dbbc36ad8724a4eb987022.
Frozen artifacts/source/config/logs .cache/persistent-auth/5ccf698431f3d85c/.
First OTA backup .cache/ota-history/20261115T232130419001Z/ verified360samples/
15events. Chrome checked Remember me and logged in on new firmware. Second OTA
.cache/ota-history/20261115T232321802911Z/ also verified360samples/15events.
After that reboot, Chrome reload opened the live dashboard without any login
or password entry: remembered session survival verified on hardware. New live
thermocouple reading85C confirmed requests worked after reboot, not just cached
HTML. Other browsers must opt into Keep me signed in once on this version.
Owner requested committing this change; nothing pushed. No USB or watchdog restart.

## 2026-11-16 burn-session lighting and cooling threshold

Owner approved sustained-rise starts and 30min below a configurable end threshold
without renewed sustained warming. burnHistoryRange now uses independent end60C,
validated finite/nonnegative and below the cold-zone start limit. Starts also on
>=2C/min across>=2 consecutive intervals spanning>=4min; gaps>8min reset the rise
candidate. Uses temperature differences rather than one regression rate value.
Glowing/coaling observations remain manual; no colour/LED/sensor changes.
Dashboard Tuning has Burn sessions / Session ends below. Field is monitor-only,
no display acknowledgement. settings_t append4B (4496B), NVSsettings_v4 migrates
v3 and existing v2/v1 layouts while retaining old keys for rollback. Older API
clients omit the new field without resetting it.

Owner supplied read-only Sheet1FBclI7nmsVf1YWoD5LyQ6gISbO4SOWURTZWdCJyEavY;
authenticated browser CSV export3036rows through16Nov00:05local. Source unchanged.
Replay:15Nov12:21 old range09:21..now, new12:00..now;16Nov00:05 old22:31..now,
new16:26..now (pre-start padding included). This supports earlier lighting and
merging warm refills; not ground-truth classification of every session. One
stored rate121C/min motivates rejecting isolated rate values. Actual15Novlighting
temperatures embedded as a small regression fixture, not the whole private Sheet.
Host graph, settings-sync, ASan/UBSan settings migration/REST, asset versions and
history snapshot tests pass. Firmware IDF6.0.3 build1517872B,18128B OTA free;
SHA256f467d5b7280d66b102132902456aabe73d4f4c3039ac4025a216cbbad7457c93.
Frozen artifacts .cache/burn-sessions/f467d5b7280d66b1/. OTA succeeded with backup/readback
.cache/ota-history/20261115T230843716554Z/:360samples/15events preserved.
Production Chrome verified Session ends below60C, existing cold125/hot200,
Bosch21.6/9C, four tunnel connections and live graph15Nov21:21..16Nov00:10.
Important: Sheet logging is sparser than the four-minute device history. Device
history shows<60C from20:45 through21:36; thus this legitimately splits the evening
at21:36 (15min padding21:21), unlike replay of the sparser Sheet. Never claim Sheet
sampling is ground truth or that the live graph must match its16:26 replay.
Owner requested committing this change; nothing pushed. No watchdog monitoring restart or USB open.

## 2026-11-15 Bosch outdoor temperature DEPLOYED

Bosch outdoor_t1 is fetched read-only by the existing Bosch worker every900s,
independently of the room reading. Valid range-40..60C; cache expires after1800s.
Gateway switching/disconnect invalidates outdoor cache. API includes independent
outdoor availability/value/age/http status. Homescreen shows a sun/cloud SVG next
to the room reading; tooltip and screen-reader label retain Outdoor temperature.
Unavailable values show a dash. Existing periodic/event Sheets rows include
outdoor_temperature from cache (event snapshot at tap). Existing Code.gs dynamic
column behavior tested locally; no Apps Script deployment or live Sheet readback.

Eight relevant host programs passed: Bosch ASan/UBSan, Bosch header, Sheets memory,
Bosch UI, Sheets dynamic columns, asset versions, event log, burn graph. Icon-only
change additionally passed Bosch UI/asset versions and git diff --check.
IDF6.0.3 final image1516832B,19168B OTA free; SHA256
0ec3658b8ec689daabad631ff08f81014b5dd023b07bb8db88ec4cf44b466dfd.
Frozen artifacts/source/config/logs: .cache/bosch-outdoor/0ec3658b8ec689da/.
OTA succeeded to monitor192.168.1.137. Backup/independent restore verification
preserved360samples/14events: .cache/ota-history/20261115T225314260430Z/.
Chrome production login and visual verification confirmed room21.7C and outdoor8.0C
with the requested icon (no Outside text). No fake production event, display flash,
USB open or watchdog monitoring restart. Owner requested committing the outdoor feature; nothing pushed.

## 2026-11-15 grouped burn log and Coaling DEPLOYED

Owner approved the local design and explicitly requested implementation+OTA.
Dashboard Log a moment now separates Actions (five entries) and Fire status
(six entries) in the approved warm bottom-sheet layout. New status Coaling:
glowing embers, little flame. No extra statuses added. Presentation order and
short labels are UI-only: original API/Sheets slugs and labels retained.
Coaling appended to EVENTS as index10, preserving all original0..9 snapshot
IDs. Fire-status observations remain manual annotations, without changing
sensor classification, burn detection, settings, LED behaviour or stack sizes.
Icons use fixed local SVG paths (no HTML from API); tab arrow/Home/End handling,
initial focus, Escape close and opener-focus restore verified locally.

Node test_event_log.js covers exact stable taxonomy IDs,5/6 groups, old-device
capability filtering, canonical coaling POST, queue-full feedback, failure,
focus behaviour and unchanged readings/settings. ASan history snapshot test
now roundtrips coaling index10 in unchanged6296B format. Existing history-memory
fixture corrected to use the established native adapter shim (it predated9bed160).
Nine targeted test programs pass, including HTTP2/identity/gzip, asset versions,
UTC OTA backup, full history, graph follow and display settings acknowledgement.
Local Chrome actual implementation verified selecting Coaling/toast and keyboard
navigation, with synthetic data only. Local preview now ordinary mock_server
port8886 (session99010), replacing the temporary prototype server.

IDF6.0.3 build1515712B;20288B OTA free. Exact image SHA256
3759ff55ad2cf97bd5353e6f8db21529db7b6bd9cb4852debb032be3a3739d1c.
Frozen bin/ELF/map/actual sdkconfig/source/build+test logs:
.cache/burn-log/3759ff55ad2cf97b/. OTA to monitor192.168.1.137 succeeded;
Mac UTC backup and independent restore readback preserved360samples/14events:
.cache/ota-history/20261115T223547735173Z/. All redacted settings unchanged
apart from boot-randomized revision. Chrome owner-authorized login after OTA
works; production Actions5 and Fire status6 including Coaling confirmed.
No fake event logged on production. No display flash, USB open or watchdog
monitoring restart. Owner requested committing the change; nothing pushed.


## 2026-11-15 audit cleanup and retired tunnel removal DEPLOYED

Owner approved the audit's small simplifications and explicitly requested all
remaining PageKite code removed. Removed prototype scripts/C/README, runtime
settings fields, active documentation and test-domain references. Historical
entries below remain diagnostic history. Recorder event IDs9..11 retired without
renumbering later events (NVS_BEGIN stays12). Settings_t shrank5008->4492B.
New saves use settings_v3; v1/v2 imports skip the retired516-byte region and
preserve the original Cloudflare token/hostname/connections plus sensor/display/
Sheets settings. Older keys stay untouched for rollback; no settings save was
performed on hardware merely to force a new-format write. Migration and v3
save/reload/corrupt-length behaviour tested with fixed deployed offsets on host.

Fonts now use the same web_request/HTTP2 dispatcher and512B streaming as all
other assets. All five old font URLs retained; Figtree aliases share one handler.
The old fast-path's accepted uppercase V version query remains supported for
tunnel fonts. Duplicate font streaming/cache helper and its isolated test removed;
coverage moved to actual direct-bridge tests, including12 concurrent fonts.
Accept-Encoding parser now shared across LAN and tunnel. Diagnostic internal
asset-buffer switch also honoured by direct decoder (tested both configurations).
Only one CSS source remains, shared by device generation, preview and checks.
Login template moved from disabled C to web_ui/login.html. Generated login and
CSS bytes unchanged; dashboard JS changes remove localhost-only preview logic,
and dashboard HTML changes only its JS version reference. Mock-server status
configuration preserves previews. Explicit host/auth_crypto.inc and auth_peer.inc
fixtures replace parsing another test's source; legacy native fixture adapter
remains for existing tests, without a test-framework rewrite.

15 test programs passed, including ASan/UBSan direct/auth/migration tests, graph,
service worker, display acknowledgement, Bosch, asset bytes/versions/decoding,
HTTP/OTA/history and recorder tests. Actual ROM-compatible decoding reference
/tmp/flue-miniz-v114.c. Monitor build with IDF6.0.3 passed. Display build could
not run: activation refers to absent SDK5.5.5; only6.0.3 is installed. Shared
parser compiled/tested for strict monitor PSRAM and internal-only display mode;
no display hardware flash or unsupported SDK upgrade attempted.

Image1513888B,848B smaller than9bed160's deployed image; OTA free22112B.
SHA25663d971ec8fde0f99be86797ad916a930148bb5c39d5646d3abb5dd925a1412e7.
Frozen bin/ELF/map/actual sdkconfig/source/build+host logs:
.cache/cleanup/63d971ec8fde0f99/. OTA succeeded on monitor192.168.1.137;
UTC graph backup/independent restore readback preserved360samples/14events at
.cache/ota-history/20261115T215430469511Z/. All21 redacted settings fields
unchanged (boot-randomized revision excluded).64 public asset/security checks
passed;36requests at concurrency12 included fonts and icons, all200.
Chrome authenticated login, live sensor/room temperature/display Wi-Fi, drawn
graph, Bosch status and saved tuning confirmed; tunnel reports4/4 connections.
No settings changed in browser. Hardware results in frozen directory. No USB
opened, watchdog monitoring not restarted. Owner requested committing this
cleanup; nothing pushed.


## 2026-11-15 direct HTTP/2 assets and API DEPLOYED

Owner requested remaining assets and dashboard API directly over HTTP/2. Added
web_request adapter shared by real native HTTPD requests and direct tunnel jobs.
No synthetic httpd_req_t objects and no loopback proxy sockets for application
routes. Both transports dispatch existing app/auth handlers on the HTTP task;
only tunnel task touches CFT streams. Immutable assets reference flash; JSON
ownership and bounded request storage stay in PSRAM. Internal 8-byte atomic
control per job avoids ESP32 external-RAM S32C1I limitations. Maximum16 pending
jobs,10s receive/handoff timeout,512B streaming chunks. Active handoff polling5ms,
normal idle100ms preserved. Identity clients use PSRAM ROM tinfl dictionary.
LAN HTTP/1.1, display WS and local OTA remain supported. Host/HTTPS allowlist,
cookies, CSRF and settings redaction preserved. Removed obsolete proxy queue.

Host checks passed: dashboard auth, versioned assets, Bosch, Cloudflare settings,
HTTP PSRAM/OTA buffers, history snapshot, tunnel lifecycle/policy, compressed
assets, and actual direct bridge+adapter with actual auth under ASan/UBSan.
Direct tests include fragmented POST, cancellation/worker lifetime, all allocation
failure points, saturation/timeouts, identity multi-block decoding,512B writes,
header lifetime, real PBKDF2 cookies and CSRF. Decoder reference dependency:
/tmp/flue-miniz-v114.c (official miniz v114 single-file source).

Firmware1514736B,21264B free per OTA slot; SHA256
51b99163eef6bff3defa9dc86b436c100ac0db1385bd452c86f3965dda22d249.
Frozen bin/ELF/map/actual /tmp/flue-cloudflare.sdkconfig/source/build log:
.cache/direct-http2/51b99163eef6bff3/. OTA succeeded at192.168.1.137, no USB
opened. UTC backup+independent restore readback verified360samples/14events:
.cache/ota-history/20261115T212014414701Z/. Public hardware checks passed58
asset/security cases (LAN versus public decoded bytes, all14launch images,
icons/fonts/manifest in gzip and identity; protected APIs401; local-only404;
foreign Origin and remote setup403), plus36requests at concurrency12, all200.
Results hardware-public.json in frozen directory. Public login and auth-status
API work. Authenticated Chrome verification passed after owner-authorized login: live
reading, room temperature and Wi-Fi update; burn graph drawn with historical
events; settings and Bosch state load; Cloudflare reports4/4 connections.
Reload retains the authenticated session and live dashboard. No settings changed. Owner requested committing the change; nothing pushed.
Previous stable image .cache/graph-loading/98da9d2639d2bb25/ retained.


## 2026-11-15 graph loading animation DEPLOYED

Owner requested visible feedback while history loads. Graph card now reserves
its drawn height and displays the existing startup spinner plus Loading history
until fetch completion AND uPlot ready (first draw). chartReady component flag
set by ready hook; tooltip hidden until drawn. Empty/error states replace spinner,
and a first-load retry resets historyLoaded while existing graphs remain visible
on refresh. Existing reduced-motion rule applies; no new library or runtime task.

Chrome real dashboard with temporary7s history delay confirmed loading spinner
visually, successful graph reveal, and503 stopping spinner with existing retry
message. Local preview /tmp/flue-graph-loading-preview.py port8882, prefetch
suppressed only in preview; production prefetch retained. Node graph test checks
ready lifecycle and existing auto-follow; asset/hash/cache tests pass. Build
1511952B,24048B free; frozen source/ELF/map/bin/actual sdkconfig at
.cache/graph-loading/98da9d2639d2bb25/. OTA succeeded; UTC backup and independent restore readback verified at
.cache/ota-history/20261115T203646306966Z/. Not committed; preceding combined
graph fix is3f68a1c.


## 2026-11-15 recent-session cooling tail now follows current time

Owner clarified graph must reach current time even after the recent session has
ended. Prior16be2e3 fixed asynchronous uPlot manualRange freeze, but range policy
still capped completed sessions at end+15min. Changed burnHistoryRange max to now
for every recent session, retaining15min pre-start padding,30min cold-gap merging
and3h recency/fallback. No session threshold changes. Updated completed-session
expectations and added regression for ended/cooling session continuing to follow.
Graph tests and asset/hash/cache tests pass; firmware builds. Frozen image/source
and ELF/map/actual sdkconfig .cache/graph-cooling-follow/1c3b4f3b819b30f1/.
OTA accepted and Mac UTC backup/restore verified after restart; artifacts
.cache/ota-history/20261115T202920868843Z/. The graph now ends at current time.
Not committed. Owner was told previous repair missed this requested behavior.


## 2026-11-15 graph automatic-follow fix DEPLOYED

Owner reported graph not moving to latest active-session data. Root cause:
uPlot1.6.32 defers setScale hooks through queueMicrotask; resetRange cleared
manualRange before hook fired, which then incorrectly set manualRange=true.
Prior test mock invoked hooks synchronously, hiding the bug. Changed resetRange
to guarded plot.batch commit, so automatic hooks run under automaticRange flag;
user drag/wheel/touch retain manual range, reset resumes following.

Updated test_burn_graph.js uses deferred commit mock; failed before fix and
passed after. Chrome using actual bundled uPlot and controlled advancing clock:
old code fails live-follow and resume-after-reset, manual zoom passes; fixed
passes all three. Local fixture /tmp/flue-graph-browser-check.py port8879.
Asset-version/actual handler/cache and graph tests passed; firmware build passed.
Image1511776B,24224B free; frozen bin/ELF/map/sdkconfig/source/test and browser
results .cache/graph-follow/0386926e37403975/. OTA accepted, UTC backup and
restore verified .cache/ota-history/20261115T202350685038Z/ (360samples,13events).
Not committed/pushed. Prior PNG optimization was committed65c5138.

Live settings threshold125C; pre-OTA snapshot last56C (114s old). Latest burn
ended105minutes before snapshot according to current rules; it is recent but
NOT still active. Thus default graph should show completed-burn end+15min,
not necessarily present time. Told owner both this and the separate fixed bug.
No thresholds or session detection changed. Original direct HTTP2 remaining
assets/API work still pending.


## 2026-11-14 lossless PNG flash reduction DEPLOYED

Owner requested firmware storage reduction and authorized access; prior autonomous
flash/testing authorization persists. Measured baseline1522480B with13520B OTA
headroom. Added optional tools/optimize_png_assets.py maintenance tool (temporary
Pillow13.0.0/zopfli0.4.0 environment /tmp/flue-library-publish/test-env). Ordinary
build has no new dependency. Tested candidates with/without Zopfli, kept only
smaller gzip payloads, verified identical RGBA pixels, dimensions, color/density
metadata on ALL17PNGs. Original sources archived .cache/asset-optimization/.
No fonts, TLS, watchdog, runtime code or partitions changed. Plain stronger outer
gzip alone was only2031B across all web assets, so not added to build.

PNG gzip payloads shrink10826B. Actual image1511632B: saves10848B; free24368B.
SHA2567e2ac6dd9828eb9410ec4fb8bc17e4b43ce6e5ebc23fab6639783677bc50e7eb.
Exact bin/ELF/map/actual /tmp/flue-cloudflare.sdkconfig copied to
.cache/asset-optimization/deployment/7e2ac6dd9828eb94/; build.log/report in parent.
Compressed-asset, actual asset handler/version/cache and login HTML tests passed;
firmware build passed. UTC history work was committed earlier as cfa4e3e.
PNG source/tool/docs modifications NOT committed yet.

OTA through tools/ota_with_history.py succeeded. UTC pre-backup and independent
post-restore readback in .cache/ota-history/20261114T010304815668Z/ verified
43samples/4events preserved. All17PNGs served byte-exact through LAN identity AND
gzip (34requests); hardware-verification.json in frozen deployment directory.
Settings preserved and password configured; public /login HTTP200. No USB opened.
No blind USB opening: earlier power-on reset cause remains unknown. Original
remaining direct HTTP2 assets/API work is still pending, not accomplished here.

## 2026-11-14 baseline committed; UTC Mac backup implemented locally

User requested commit all changes, THEN start UTC timestamps. Baseline source,
tests and Cloudflare experiment committed as00213ec (author/committer LeonB,
not pushed). Excluded generated build-*, personal design-import/readings/resume/
DNS-import files and private secrets. Original778a071 was amended solely to fix
author/committer; use00213ec. UTC changes are subsequent, UNCOMMITTED.

Mac tools/ota_with_history.py now writes canonical history-before.json and
history-after.json: format flue-monitor-history, version1, captured_at Unix UTC
seconds; each sample/event has explicit timestamp. Backup records never change
during restoration. Relative6296B wire v2 remains firmware-compatible; at restore
UTC records convert to current ages using Mac time, no device NTP. Raw bin files
remain diagnostics. Script reads saved JSON back for actual restore. Explicit
schema/range/finite/order checks before update; event verification now preserves
multiplicity of genuine duplicate taps. No ESP32 source changes/flash for UTC.
Legacy prepare_restore(binary) helper retained for earlier local tools/backups.
README documents seconds precision and network/rounding uncertainty.

Local test_ota_history.py passed: HTTP backup/restart/import/readback with JSON,
delayed/repeated UTC conversion through1year, unchanged original timestamps,
invalid data, backwards Mac clock, uint32 age overflow, duplicate event counts,
USB identity/layout mocks. py_compile and git diff --check pass. Read-only real
UTC capture at .cache/ota-history/20261114T003104181060Z/ had only2samples/0events:
monitor had restarted again. Restored last verified full33point/3event snapshot
plus new live data through RAM import; verified35points/3events under
.cache/ota-history/20261114T003208192930Z/. JSON UTC backup saved there. WS then
uptime407s, reset_reason1(power-on), sensorOK,4CF connections, Sheets success1.
Cause of power-on reset not established; no evidence of watchdog. Do not claim
history persists arbitrary power loss: it remains RAM-only, Mac handles flash.
Original HTTP2 remaining assets/API task remains pending.

## 2026-11-14 recovery and OTA graph round-trip VERIFIED

USB recovery installed e23c1a602272047f. Subsequent owner-approved identical OTA
succeeded, proving the old checkpoint veto is removed. Final artifact directory
.cache/ota-history/20261114T001908248108Z/: raw-before.bin preserves the unmodified
46point/6event state; history-before.bin uses original31points/3events plus newer
post-USB measurements. OTA response accepted, RAM empty after reboot, one import,
independent readback verified33points/3events (backup32points/3events). No graph
NVS persistence. All original31points retained; shifted duplicates gone.
LAN settings match before-settings.json excluding randomized revision; auth
still configured. Curl public root returns normal303 /login. urllib follow gave
403 so do not conflate that client-specific result with tunnel outage.
USB .cache/ota-history/20261114T001040041035Z/usb.log includes MAC, partitions,
both app hashes. Settings/bootloader/partition table/otadata were preserved.
Earlier sections saying waiting for monitor USB or recovery not installed are
superseded. Original HTTP2 remaining assets/API task still pending. User asked
about absolute timestamps for backup, no new wire-format change authorized yet.

## 2026-11-14 USB recovery completed; OTA/read-back check in progress

Owner connected monitor USB /dev/cu.usbserial-5C671828951. Verified PICO-V3-02
rev3.1 MAC8c:94:df:0b:be:fc and existing partition table. Both application slots
written and hash-verified, NVS/bootloader/table/otadata unchanged. Installed
recovery SHA e23c1a602272047fffabd3b8be3c4c1c22e0982f6e05cb384d457885cf7b87b1.
USB log and first backup/restore verification in .cache/ota-history/
20261114T001040041035Z/. Device reachable again, v2 maintenance export working.

Pre-USB backup .cache/ota-history/20261114T000907983706Z/history-before.bin has
31samples/3events. Plug-in had already rebooted OLD firmware; its later backup
has14samples/3events shifted +10s from legacy NVS restore. Importing both yielded
46samples/6events, so do NOT call that final clean restoration. All raw snapshots
retained. Owner explicitly approved one same-image OTA and clean restoration:
use original31samples/3events plus only post-USB new measurements/events. Script
/tmp/flue-clean-history-ota.py; hardware execution in progress. First attempt was
auto-review rejected, NO mutation; user then answered prma to specific approval.
Do not conflate this with a new implementation or claim final success before
verified.json. User asks about absolute time: answered UTC per backup record is
clearer, monotonic time can remain internally; no new format change yet.

## 2026-11-14 ACTIVE: Mac-owned backup/flash/restore (not installed)

This section supersedes the compact-NVS recovery plan below. Owner clarified:
fetch graph data before flash, save on Mac, flash, then restore. Local firmware
now has RAM-only history_snapshot.h v2 export/import (6296 bytes). Mac stamps
capture time and supplies elapsed seconds; ESP32 NTP is not involved. All graph
NVS checkpoint/restore code and the pre-OTA checkpoint veto were removed. Boot
migration erases ONLY the obsolete graph_history namespace; settings/auth remain.

Root ota_flash.sh delegates monitor updates to tools/ota_with_history.py. It
backs up before reset/upload, freezes the image, performs one OTA upload or a
MAC/layout-checked USB app-only write, restores and independently reads back.
Backups remain in .cache/ota-history. USB writes both existing application slots,
leaving otadata, NVS, partition table and bootloader intact. Never use the connected
flue-display port; actual monitor connection is still awaited. Expected monitor
MAC 8c:94:df:0b:be:fc. Current installed image is still 8e56e74ab280a693 and its
OTA gate still fails; no further OTA attempt until USB repair.

Local test_history_snapshot.py and test_http_psram_buffers.py passed again;
test_ota_history.py passed its local HTTP backup/reboot/restore/readback and USB
identity/layout/address mocks. Firmware build passed (history-mac-backup-build.log).
These are local results, not a successful hardware recovery. Original remaining
HTTP2 assets/API work is still pending. Earlier checkpoint deployment details
below are historical and must not be treated as the current design.



## 2026-11-14 ACTIVE recovery update (not installed yet)

Owner approved ONE diagnostic repeat OTA after the automatic approval rejection.
It ran at23:35:42UTC: HTTP500 exact body History checkpoint failed; update not
activated. Current image remains8e56e74ab280a693. GET maintenance export succeeds,
so failure is in the NVS write path, but the firmware does NOT report the exact
ESP error code; NVS capacity/fragmentation remains suspected, not proven.
Acknowledge this was our implementation flaw: optional graph persistence was
made a prerequisite for firmware updates, blocking remote repair. User asked
what the problem is; explained plainly that one USB recovery is now needed.

USB inventory: ONLY /dev/cu.usbserial-21130 (CH340 VID1a86/PID7523). Owner explicitly
identified it as flue-display, NOT the flue-monitor. DO NOT OPEN/RESET/FLASH it.
Async question pending: can owner connect flue-monitor itself via USB, or later?
Do not perform further OTA attempts on the current image: they will hit the same
veto. Wait for actual monitor connection before USB; verify MAC8c:94:df:0b:be:fc
before writing. Only application slots, NO NVS/partition/bootloader erase/change.
Current selected slot unknown; can write same recovery app to BOTH known slots
0x20000 and0x1a0000 so otadata remains intact. Read/verify partition table if needed.
Use esptool only after owner confirms monitor connected. Preserve settings and
external graph snapshot. Scope original HTTP2 remaining assets/API still pending.

Local recovery changes prepared: NVS keyv2 packs max360samples+64events into3944B
(one NVS page incl index/chunk overhead), instead of always6296B. Header is same
24B; each sample age4, whole-degree temp+zone2, exact float rate4; events age4/id1.
External maintenance wire format remains6296B v1. Read legacyv1 for migration;
erase oldv1 only AFTER compactv2 write+commit succeeds. No periodic flash writes.
Optional OTA checkpoint errors now log the SDK error and ALLOW firmware repair.
Never claim this version is installed until USB recovery happens.

Added tools/ota_with_history.py: shared root ota_flash.sh delegates to it for the
monitor only. It saves authenticated external binary backup under .cache/ota-history
before upload; one upload, no automatic retry; after restart, compares history,
restores backup if needed and verifies by read-back. --without-history is explicit
legacy/recovery override. Avoid exception strings with secret URLs; HTTPError
status/body recorded without credentials. New test_ota_history.py uses real local
mock HTTP server and passes backup/restore/readback, failure logging/no retry.
Default timestamp matching currently2s; a long-running device clock correction
shifted observed epochs by4s between snapshots, so /tmp roundtrip comparison
failed despite allpoints still present. This is NOT data loss. Do not silently
claim exact epoch equality; account for clock correction when verifying.

Latest external full snapshot25samples saved from current maintenance GET at
23:47:22UTC to .cache/cloudflare-integration/history-preservation/before-usb-full.bin.
Earlier /tmp/flue-checkpoint-roundtrip.py compares to bootstrap with2s tolerance;
it now writes current-read.bin BEFORE comparing, so capture survives comparison
failure. If current-read.bin is newer, copy that; never label stale failed compare
output as fresh. Refresh via safe GET before physical reset when possible.

Recovery build passed before the final erase-error logging tweak, size1523504B
(0x173f30),12496B headroom. Rebuild after latest tweak before freezing artifacts.
Host test_history_checkpoint.py updated for compact max3944B round-trip, exact
float rates, v1migration, epochs, fresh merges and write failure. Actual OTA
handler tests updated: optional checkpoint failure permits repair; auth/limits/free
remain covered. Run these and relevant asset/auth tests. Original compiler flags
retained (all ineffective optimization trials were removed). Variable font is
already in installed8e56 image and visual/native byte checks passed.

## 2026-11-14 ACTIVE: history preservation installed; repeat OTA rejected

Owner explicitly authorized autonomous flash/test/rollout for HTTP2 optimization.
Original outstanding task: direct-dispatch remaining Cloudflare assets/API (only
fonts implemented so far). Before that refactor, owner requested preserving graph
history across reflashes; this is the current priority and NOT yet fully verified.
Do not claim complete. No HTTP2 transport-abstraction code has been changed yet.

Current installed firmware SHA256
8e56e74ab280a69373dc3d2f9b53192a732d67bcc1941bed6068b5850fa40db2,
1522944bytes,13056bytes free. First OTA at2026-11-13 22:57:30UTC succeeded.
Exact ELF/bin/map/sdkconfig/receipt/settings/telemetry and bootstrap under
.cache/cloudflare-integration/deployment/history-checkpoint-8e56e74ab280a693/.
Owner logged in; read /api/history via native Chrome and saved latest12samples/
3events to .cache/cloudflare-integration/history-preservation/
before-first-install-latest.json and bootstrap.bin. Bootstrap timestamp from host
receipt has estimated15s uncertainty. POST maintenance import succeeded and GET
verified all12old samples/3events plus a fresh point; original epoch positions
match within2s of the bootstrap metadata. After further sampling14points intact.
Sensor, Sheets, settings/auth and4CF connections passed postcheck. Browser login
page renders new variable font correctly. No credentials retrieved from browser.

New code: main/history_checkpoint.h versioned6296B binary (little endian,
header <qIIII: saved_at,version,count,event_count,reserved;360x<IffI samples;
64x<II events; eventoffset5784). Ages stored; uint32 wraparound rebases pre-boot
samples correctly. sensors_merge_history merges fresh points under sensor mutex.
rest_api checkpoint/import/export/event merge execute on HTTP task. Automatic
restore is lazy at history fetch/event or checkpoint/export; waits for valid time.
NVS namespace graph_history,keyv1 stores full6296B CRC-protected NVS blob.
main registers optional shared OTA hooks. Authenticated GET/POST /ota/history
use same OTA secret as /ota and remain excluded from tunnel policy. POST is binary
size6296, cap32768; GET provides binary snapshot without NVS write. Prepare hook
runs after image validation BEFORE esp_ota_set_boot_partition; a hook failure
returns500 and leaves current boot partition selected. No periodic/power-failure
checkpoint, nor protection against erase_flash. Normal local/OTA stack unchanged.

Second identical OTA at23:00:06UTC returned HTTPError; original deployment
script discarded status/body, so exact error UNKNOWN. Do not assert NVS capacity
as proven. Read-only export after failure confirms history intact, no reset.
Record in sibling ...history-checkpoint-8e56e74ab280a693-second-ota/ota.json.
Likely checkpoint/NVS issue (24KB NVS, full6296B copies), but needs error body.
The deployment logger now records HTTPError status/body. Read SDK confirms
nvs_commit is currently effectively no-op; blob updates write before commit.
Do not extrapolate mocked commit-failure atomicity to actual NVS.

Attempt to perform ONE diagnostic identical OTA was twice rejected by automatic
approval review. Rejection says a current user instruction forbids activating a
new image before backup fix, but that wording came from my commentary precaution,
not the user's explicit instructions. Still DO NOT bypass rejection. A concise
async approval question is PENDING: one controlled attempt may restart only if
checkpoint succeeds; options yes diagnostic attempt/no read-only. Wait for owner
answer before any further OTA attempts. User was informed of automatic rejection.
Can continue local/read-only work. /tmp/flue-checkpoint-second-deploy.py is the
rejected diagnostic script; /tmp/flue-checkpoint-roundtrip.py reads/compares
snapshots using OTA secret without printing it. Mode bootstrap imports; other
modes only GET. Failed-OTA snapshot has been/should be renamed
'after-rejected-ota.bin', not presented as a successful second reboot. Verify
files before using. /tmp/flue-checkpoint-artifact-path points to first artifact.

To fit without partition changes, replaced three Figtree2.002 static instances
(total34396B) with official Figtree2.002 variable (20184B), same222codepoints,
wght300..900, no topology changes; outlines/metrics differ only <=1/1000em due
static rounding. New figtree-variable.woff2 + OFL-Figtree.txt; original files
archived under history-preservation/original-fonts/. HTML/login have one variable
face400..700 and only2font preloads. Legacy400/600/700routes remain aliases;
generator aliases share file/hash and new canonical URL. Canonical direct tunnel
font route allowed; mock server updated. Original compiler/link flags retained:
experimental app LTO and Oz attempts did not help and were REMOVED. Check main
CMake to avoid reintroducing ineffective trials. SDK/IRAM/watchdog unchanged.

Host tests pass: new test_history_checkpoint.py(actual merge/checkpoint code,
ASan/UBSan) covers epochs, reboot/fresh merge, bounded rings, invalid binary,
allocation/NVS failure, clock rollback, corrupt-blob repair. Extended actual OTA
handler test covers prepare failure veto, import/export auth/body limits/free.
Existing compression, auth, assets/version, CFfont/policy and burn-range tests
pass. FontTools installed in /tmp/flue-library-publish/test-env from public PyPI;
CSS source /tmp/flue-figtree-variable.css, font-source.json under history-preservation.
No further firmware changes or successful second OTA claim until resolved.

## 2026-11-13 direct HTTP2 fonts deployed and compared

Owner accepted reducing the loopback proxy overhead, then explicitly authorized
flashing/testing/rolling out autonomously for this optimization. First step only:
public fonts served directly by the tunnel; HTTP1/LAN/OTA and all protected assets,
authentication and APIs still use the existing server. No8KB HTTPD stack saving
claimed. main/cloudflare_font.h streams shared flash bytes in512B chunks, with
small strict-PSRAM response state, writable backpressure and close cleanup.
Canonical matching asset-version URLs and unversioned fonts use this path; other
queries fall back to HTTPD unchanged. Existing ETags/304/cache policy preserved.
No duplicate embedded asset copies and no SDK/upstream library changes.

ASan/UBSan font tests cover bytes,512B bound, cache/version queries,304, cancel,
allocation/header/write failure. Existing queue/tunnel-policy/auth/assets tests
pass. Actual vendored nghttp2/proxy versus direct streamer, same synthetic edge
and12KB origin payload, instrumented host allocations:4 downloads extra heap
23151->6440B (16711B saved);14 downloads34281->16670B (17611B saved).
Origin peak4->0 in both; byte-exact200 responses; all tracked allocations freed.
These are HOST allocator numbers, not measured ESP32 RAM savings; no kernel/TCP
memory in that counter. Harness/dependency paths/shims/results under
.cache/cloudflare-integration/direct-font-validation/.

SDK6.0.3 build passes,1534336bytes,1664bytes OTA headroom. Deployed
217c2145074ee3613b4d351cdbce527a16f194b933efe945e84c4c232c111ebe,
HTTP200 OK,rebooting at22:10:09UTC, MAC verified. Exact ELF/bin/map/sdkconfig,
source/test, host results, OTA/settings/telemetry and HTTP checks under
.cache/cloudflare-integration/deployment/direct-font-217c2145074ee361/.
Settings/auth retained, valid real sensor, increasing uptime and four tunnel
connections recovered; Sheets uploads confirmed. Hardware repeating four-font
loads:88/88 before and104/104 after returned200 with exact file content. Sampled
internal free minima102740->116316B; PSRAM minima1815820->1777188B.10s samples,
different uptime, network and Sheets activity make those hardware figures NOT
an isolated causal memory comparison. Do not claim a precise ESP32 saving.
An earlier faster pre-update probe gave502 and a WS client ping timeout; uptime
kept increasing (no device reset), and the slower recorded comparison above
completed. Keep that separate from candidate results.

Device HTTP checks:canonical font200 exact bytes,conditional304,wrong-version404
no-store,noncanonical query fallback200, protected dashboard.js401. Cloudflare
rewrites the unversioned/fallback public font browser Cache-Control to max-age14400;
LAN origin remains no-cache. Canonical direct private immutable policy preserved.
No full authenticated browser check was needed/repeated for this public-only
font change; owner credentials never retrieved. Extending direct dispatch to
protected assets/API remains future work and requires shared authentication and
transport-independent handlers, not simply calling existing HTTPD handlers from
the tunnel task.

## 2026-11-13 burn-session graph deployed via OTA

Owner requested flash. Verified candidate hash/size and monitor MAC before OTA.
Installed8a9861164c4d41c5e16659fd8b76a0b00cb31278f78183da0f051fba4df4dff6,
1533648bytes, HTTP200 OK,rebooting at21:44:24UTC. Exact bin/ELF/map/sdkconfig,
source snapshots, test, receipt and settings/telemetry verification in
.cache/cloudflare-integration/deployment/burn-session-8a9861164c4d41c5/.
Sensor valid, uptime increasing, reset_reason3(planned software restart), Sheets
upload and tunnel recovery observed. Chrome public/LAN login pages load; owner
asked to sign in for final device graph check. History is RAM-backed, so OTA
clears prior burn samples; the last3hours fallback will initially have little data.
No password/cookie changes or credential retrieval.

## 2026-11-13 automatic burn-session graph (local only)

Owner requested recent burn-session framing, otherwise last3hours, and removal
of remembered graph position. burnHistoryRange chooses activity at/above the
configured cold/optimal threshold; cold dips shorter than30minutes merge into
one burn. Latest active/recent burn gets15minutes padding, capped at now; a burn
ending more than3hours ago falls back to now-3hours..now. Minimum visible span
10minutes. Stale hot history without a valid live sensor is not treated as a
current burn. Existing24hour data and manual pan/zoom remain available. Automatic
view follows updates until manual zoom; double-click restores automatic framing.
Removed dashboard.graphState and all restored range state across graph openings;
dashboard link now says Burn history. No sensor/history-storage changes.

node tools/test_burn_graph.js passes recent/old/current/short burns, merged dips,
separate burns, compressed hot plateaus, custom threshold, stale data, auto-update,
manual zoom retention while open and fresh framing after reopen. Existing
settings-sync and compressed-assets tests pass. Local Chrome mock8017 visually
shows a4hour recent burn instead of24hours. SDK6.0.3 final build passes,
1533648bytes,2352bytes OTA headroom. Artifacts/source snapshots and candidate hash
in .cache/cloudflare-integration/burn-session-validation/. Not deployed.

## 2026-11-13 HTTP header limit raised and deployed

Owner approved raising the header bound after Chrome showed Header fields are too
long. rest_api_start explicitly sets config.max_req_hdr_len=4096; HTTPD allocates
its request scratch buffer on demand. No global SDK or other server changes.
SDK6.0.3 build and existing dashboard-auth/HTTP-buffer host tests pass. Hardware
boundary probe before OTA:padding0->200,1800->431,5000->431; after:200,200,431.
OTA HTTP200 at20:43:46UTC, planned software restart, image SHA256
83a488c6f85f02d409ffe2ed718ff6636e53c3cf3222e166cb4e923f5d6371e7,
1533392bytes. Exact artifacts/settings/boundary test and verification under
.cache/cloudflare-integration/deployment/header-limit-83a488c6f85f02d4/.
Settings/auth preserved; uptime20->50s, valid sensor, four CF connections and
Sheets upload confirmed. Chrome hard reload reaches the sign-in page without431.
Owner logged in; dashboard displayed current room/flue temperatures. A second
hard reload with DevTools Disable cache enabled also loaded the dashboard;
dashboard.js returned HTTP200 with9.3KB transferred (29KB decoded), and live
reading/history API requests returned200. No startup overlay or header error
remained. Restored Disable cache off, cleared filter and closed DevTools.
No credentials retrieved, cookies cleared or password changed.

## 2026-11-13 cold-load queue deployed via owner-authorized OTA

Owner requested flash. Final rebuild after comment update:SHA256
4231af524dccab401ecb5a1bbbe15e98e7af488e6837b80fe96d3233c0c5b276,
1533392bytes. Verified monitor MAC8c:94:df:0b:be:fc before upload; OTA HTTP200
OK,rebooting at20:03:29UTC. Exact bin/ELF/map/sdkconfig, OTA receipt, before/after
settings and verification in .cache/cloudflare-integration/deployment/
cold-start-4231af524dccab40/. Settings/auth preserved, sensor valid, increasing
uptime30->70s, reset_reason3(planned software restart), Sheets upload confirmed;
four tunnel connections restored (briefly3 during initial reconnect).
14 simultaneous real public asset/status downloads all200,0.68–2.11seconds.
Initial probe mistakenly requested two nonexistent assets (404); corrected
verified-route result saved separately. No503 in either post-OTA probe.
Chrome hard reload now reports Header fields are too long, a separate HTTPD
header limit problem (current CONFIG_HTTPD_MAX_REQ_HDR_LEN=1024). Therefore the
full authenticated cold-load browser check has NOT passed; no cookie clearing,
password access or authentication changes performed. No further firmware change
made for that issue. Earlier local validation entry below describes pre-OTA state.

## 2026-11-13 dashboard first-load 503 diagnosis and local fix

Chrome console confirmed dashboard.js, burn-graph.js, uplot and a font failing
with HTTP503 during first authenticated load. Alpine then reports app undefined;
its startup overlay never finishes. Concurrent public asset GETs reproduce503,
while sequential custom-user-agent probes return200. Four edge connections share
one four-origin poller; excess proxy starts were rejected immediately (PageKite
previously queued). Local fix adds a bounded FIFO for16 GETs/10seconds, raises
per-edge stream admission4->16 and retains four global origin sockets. POSTs
remain immediate and are never replayed. Queue cancellation/body rejection,
teardown and drain handling are covered. Vendored library adds an availability
query and initializes proxy body_ended from the stream, since queued GETs may
have already received END_STREAM. This is separate from the upstream PSRAM PR.

Actual vendored HTTP2/proxy core plus actual queue tested under ASan/UBSan against
upstream fake_edge and a strict HTTP1 origin:14 simultaneous GETs produce4x200 +
10x503 without queue,14x200 with queue, peak4 origins in both. Queue host tests
also cover FIFO, cancellation/reuse, cap, expiry, body rejection and proxy failure;
existing tunnel policy/restart tests pass. SDK6.0.3 firmware build passes,
1533392bytes,2608bytes OTA headroom. Artifacts and firmware hash are under
.cache/cloudflare-integration/cold-start-validation/. Test harness uses existing
/tmp upstream test dependencies and a macOS getrandom shim (arc4random_buf);
these are host-only. Not deployed; real cold authenticated load after OTA remains
to verify. No monitor reset, USB reopening or Cloudflare account change.

## 2026-11-13 upstream Cloudflare PR opened, author corrected

Owner explicitly requested creating the PR with the agreed concise body.
Opened https://github.com/igrr/esp-cf-tunnel/pull/1 (ready, not draft), base main,
head LeonB:psram, maintainer edits allowed. Title Use PSRAM for tunnel data
allocations on ESP-IDF; two agreed paragraphs only, no validation section or
allocator implementation paragraph. Owner then requested author LeonB instead
of Leon Bogaert. Amended author AND committer names to LeonB, preserving email
and identical source tree. New head 1acb87e9f501a1fabb21b23098fb5bce10cd5182; atomic exact d394339
leases updated main/psram. GitHub PR commits API verified both names LeonB.
Prior 67-test/8-build success applies to the identical tree at d394339; no new
CI success claimed for this metadata-only amendment. Publication record and
current PR git bundle in .cache/published-tunnel-libraries/. No device change.

## 2026-11-13 automatic PSRAM with configurable fallback

Owner initially accepted three allocator choices, then explicitly simplified:
use PSRAM automatically on CONFIG_SPIRAM; make only internal fallback configurable.
Published single fork commit d39433991269a14b5c68dcab7c82d74645df1b11 on main/psram
with exact 680a47f leases. New Kconfig CONFIG_CF_TUNNEL_PSRAM_FALLBACK depends on
SPIRAM, default y. Enabled uses SDK heap_caps_{malloc,calloc,realloc}_prefer with
PSRAM|8BIT first and INTERNAL|8BIT second; disabled requires PSRAM only. No PSRAM
retains libc. SDK prefer APIs prevent retry-after-free on zero-size realloc and
perform allocation-failure reporting after preference exhaustion. Official v5.4
header confirms these APIs exist. Public API/docs/workflows unchanged; no three-
choice mode published. Six CMake/pytest cases cover both PSRAM policies with/without
stats, normal host and ESP without PSRAM, overflow, available-internal fallback,
strict refusal, preserved realloc data, PSRAM recovery, zero-size realloc and real
nghttp2 sessions. Local ASan/UBSan/-Wundef/-Werror pass. ESP32 IDF6.0.3 builds pass:
automatic fallback(default), fallback off, and no PSRAM; generated flags verified.
GitHub43463299426 SUCCESS:67 tests and all8 existing IDF matrix builds. Formatter
WASM/whitespace pass locally; PR-only pre-commit CI skipped as usual. Bundles,
source archive, logs and publication.json in .cache/published-tunnel-libraries/.
Live monitor/vendored component not changed. When adopting this fork, disable
CF_TUNNEL_PSRAM_FALLBACK to retain the monitor's existing strict PSRAM policy.
No upstream PR opened.

## 2026-11-13 fork comment correction

Corrected the heap stub comment from psram_alloc.h to cft_alloc.h. Single
fork commit amended to 680a47ff5f4295b5eb37b6267432cd45f55d2916, atomically pushed
to main/psram with old-head leases. Comment only; no test rerun required.
Prior functional CI results apply to 939631a; no new CI success claimed.

## 2026-11-13 explicit Cloudflare allocators, production callbacks and coverage

Owner approved addressing critical review of the fork. Amended single fork
commit to 939631a87960b4336aebb4cfca91aa3352e85772, atomically pushed to main/psram with
exact cb5e239 leases. No forced -include or malloc/calloc/realloc/strdup aliases
in production. Private src/cft_alloc.h selects strict PSRAM on configured ESP
platforms, otherwise libc; call sites are explicit. CFT_ALLOC_PSRAM avoids raw
undefined CONFIG references. Extracted src/cft_h2_alloc.c/.h preserve accounting
only under CFT_DEBUG_STATS; production directly uses the allocator, including
heap_caps_realloc without wrapper copy/header. Public API/docs/workflows unchanged.
Host CMake tests cover PSRAM production/debug, normal host, ESP without PSRAM;
-Wundef/-Werror/ASan/UBSan pass. Tests directly exercise callbacks, overflow,
exhaustion/data retention, no production header, direct realloc, and actual
nghttp2 session construction/failure/destruction. nghttp2 new3 requires mutable
nghttp2_mem*: private getter matches this (caught by real ESP32 build).
Final SDK6.0.3 ESP32 builds with and without PSRAM pass; compilecommands show no
forced allocator include. GitHub43457283292 SUCCESS:65 host tests, all8 IDF
matrix builds(v5.4,v5.5,v6.0,latest x two apps). Pre-commit job is PR-only/skipped;
local exact upstream AStyle WASM via Node plus whitespace/EOF checks pass.
Artifacts, bundles, full CI logs and publication record in
.cache/published-tunnel-libraries/. Main monitor vendored code and device were
not changed; no upstream PR opened. Default fork branch remains psram.

## 2026-11-13 Cloudflare tests aligned with upstream and CI green

Owner requested upstream test structure/style for an acceptable patch. Fork
PSRAM commit amended to cb5e239678020c387dbab275df932e79fcfae942, still one
commit atop eb932667. Test now lives in psram_memory_test.c, built by host
CMake with cft_warnings, with SDK heap/config stubs and a small pytest wrapper
matching test_util.py (BUILD, timeout, captured diagnostics/sanitizer check).
New allocator header and overflow guards formatted to upstream AStyle settings.
Local CMake ASan/UBSan + pytest pass. Pinned astyle_py0.9.1 Python hook failed
installation on3.14; old WASM runtime was killed on3.9. Ran the identical pinned
upstream libastyle.wasm through Node WASI with identical options: clean on
second pass. Upstream whitespace/EOF checks pass. No formatter files published.
Pushed with old-head lease to psram; main fast-forwarded so unmodified upstream
push CI could run. Both branches same commit; default remains psram. GitHub run
43452222100 SUCCESS:62 host tests (including new allocator test), eight ESP-IDF
builds (v5.4,v5.5,v6.0,latest x ethernet/device). Pre-commit job is PR-only and
was skipped by upstream workflow. README, metadata, API, workflows unchanged.
CI log, current source archive/bundle and publication record preserved under
.cache/published-tunnel-libraries/. No upstream PR opened; no device changes.

## 2026-11-13 Cloudflare fork narrowed to PSRAM only

Owner requested a focused upstream-style fork. Replaced broad fork commit with
a4afa9fd166092f73acd50a39e0e2f31a29b8544 on default psram using an exact old-head lease.
Single commit atop eb932667c456a4435de7e8dab8ef2c4e4192478b; four files only:
CMakeLists.txt, psram_alloc.h, src/cft_conn.c and
 test_apps/host/test_psram_memory.py. README, metadata, workflows and public API
are byte-identical to upstream. No VALIDATION.json, copied README, extra examples
or on_poll callback in the fork commit. Allocator ASan/UBSan and ESP32/PSRAM
IDF6.0.3 build passed from an external project. Existing vendored monitor copy
and deployed firmware are unchanged and still contain on_poll. Old and new
source archives/bundles, build log and publication record retained in
.cache/published-tunnel-libraries/. PageKite repository unchanged.

## 2026-11-13 tunnel libraries published separately

Owner requested two public GitHub repositories with short usage documentation.
LeonB/esp-pagekite main65f86c412c63847bd686634162da28f46ffa3d34 extracts the
preserved native client into a standalone Apache-2.0 ESP-IDF component: explicit
copied configuration API, loopback port and deny-by-default route callback.
Original dashboard policy is an optional example; monitor settings/flight recorder
and stack-diagnostic dependencies removed only in the extracted copy. Config
comparisons use fields rather than struct padding. Host protocol/configuration
ASan/UBSan pass; minimal ESP32 example builds on IDF6.0.3. No live PageKite test
or hardware flash of extraction. GitHub host job also passed, build pending.
LeonB/esp-cf-tunnel is an actual fork of igrr/esp-cf-tunnel, default branch psram,
commit67b920eec03ad55f59ffed8e0b641df3ae168f79 over pinned eb932667. Preserves
upstream history/license/tests/API; overlays exact vendored PSRAM/on_poll changes,
short README, upstream README backup, allocator test and minimal ESP32 example.
ESP32/PSRAM/TLS1.3 build and allocator ASan/UBSan pass. Upstream Linux host suite
cannot compile on macOS(getrandom), retained in GitHub CI; CI running at record.
Removed inherited component-registry upload workflow to avoid publishing into
upstream author's namespace. Known credentials absent from publication files.
Both repos public, heads pushed; Cloudflare default psram confirmed. Source
archives/git bundles, logs and publication.json in .cache/published-tunnel-libraries/.
Main project code/dependencies were not switched to these standalone repositories.

## 2026-11-13 graph compression deployed by OTA

Owner requested flash. Verified monitor LAN .137/MAC8c:94:df:0b:be:fc; uploaded
50553ec2654d745d7fd863374d8d9d48688a26483ca49cb2e617d1ac4402e0b3 once.
HTTP200 OK/rebooting; image1532672 bytes,3328-byte OTA headroom. Saved settings
match before/after excluding randomized revision; dashboard auth retained.
Four readings at uptime30/40/50/60 confirm real20.5–20.6C readings, planned
software reset(reason3), four registered Cloudflare connections, and one
successful Sheets upload. Public /login HTTP200. Compression behavior tested
on host; this short boot check does not demonstrate long-term compression.
Exact ELF/bin/map/config, before/after and verification saved under
.cache/cloudflare-integration/deployment/history-50553ec2654d745d/.
Supersedes local-only/not-flashed note below. No commit or push.

## 2026-11-13 stable graph history compression (local only)

Owner requested skipping stable graph points and chose whole-degree graph
storage. history_push rounds only graph temperature to 1C, leaving live sensor
readings/regression/Sheets precision unchanged. Same rounded temperature and
zone, with rate within 0.05C/min of retained anchor, replaces only the newest
point of a stable run. Start/end timestamps remain; anchor comparisons avoid
cumulative drift. Four-minute cadence, 360-entry PSRAM allocation and API schema
are unchanged. This extends time coverage for quiet periods, not allocated RAM
savings or persistence across reset; chart UI time window unchanged.
Host ASan/UBSan actual-source test_history_compression.py covers stable year,
plateau endpoints, peaks, drift, zone/rate changes, negative rounding and ring
wrap; existing full-history API memory regression passes. Not flashed.

## 2026-11-13 four Cloudflare connections observed

Owner enabled four connections in settings. Read-only LAN WS samples over
188 seconds kept four registered connections, increasing uptime, and public
/login returned HTTP200 twice. Final internal free140708, largest110592;
PSRAM free1844044 /2097152 bytes. Boot minima: internal96328, PSRAM1778764.
Compared with earlier one-connection sample, about158KiB extra PSRAM and
3KiB extra internal RAM, approximate total-app comparison. Short observation,
not a stress/soak/reconnect test. No firmware or configuration changed by agent.
Evidence: .cache/cloudflare-integration/deployment/four-connections-*.json.

## 2026-11-13 production Cloudflare hostname added

Owner requested flue-monitor.vanutsteen.nl on existing tunnel
f5126ae1-d629-47b1-b61b-27dbf4816728. Added published application to
http://localhost:80 and proxied CNAME to the tunnel UUID; cf-test retained.
API read-back verified both, config version2. Only active connector is still
the S3 prototype (one connection). Real monitor remains Cloudflare-disabled
until owner configures its hostname/token; stop the prototype before enabling
the real monitor to avoid mixed backends. Evidence:
.cache/cloudflare-integration/deployment/cloudflare-route.json.


## 2026-11-13 Cloudflare integration deployed by OTA

Owner explicitly requested OTA to flue-monitor. Fresh LAN/mDNS and ARP matched
192.168.1.137 / MAC8c:94:df:0b:be:fc. Exact validated image
a8d61e078d2865f393f0e5f3834f146e20ac4dfbf87fdbe0f00051be2f846e49 uploaded once; OTA returned HTTP200
"OK, rebooting". New Cloudflare schema confirms the new app; four WS samples
at uptime60/70/80/90s show planned software reset(reason3), real22.1C readings,
2MiB PSRAM, strict buffer/TLS flags and automatic light sleep enabled. One
normal Sheets upload succeeded. Existing redacted settings compare unchanged
except revision and retired PageKite fields; dashboard remains configured.
New gzip /login returns200 and decodes correctly. Short recovery verification,
not a soak. No serial access, induced crash or monitoring restart.

Cloudflare is still DISABLED, hostname/token unset, connections1. The owner
must configure the new authenticated settings UI before remote access resumes;
PageKite is removed. No production Cloudflare/DNS settings changed. Existing
cf-test tunnel currently belongs to the separate S3 prototype; avoid serving
prototype and monitor from the same tunnel concurrently during cutover.
Integrated four-connection PSRAM runtime test is still pending. Normal app
configuration was deployed, without the optional UART core-dump overlay.
Evidence and exact ELF/bin/map/config: .cache/cloudflare-integration/deployment/.
This supersedes the earlier not-deployed note below. No commit/push.


## 2026-11-13 native Cloudflare integration built, NOT deployed

Owner requested replacing PageKite with Cloudflare and using PSRAM for up to
four connections. Applied to flue-monitor (PageKite's owner); flue-display's
LAN subscription is unchanged. No hardware flash, device configuration or
production DNS change during this integration. The earlier S3 prototype is
separate evidence; its no-PSRAM four-connection trial exhausted heap.

Vendored esp-cf-tunnel eb932667c456a4435de7e8dab8ef2c4e4192478b under components/.
UPSTREAM lists scoped PSRAM allocation, custom nghttp2 memory callbacks and an
optional per-poll callback. TLS/PSA retain the existing strict PSRAM hooks.
Stacks, synchronization and Wi-Fi/DMA remain internal. No global malloc change.
Settings UI/API provide enabled, hostname, write-only token/token_set and 1–4
connections (default1). New settings_v2 migrates known old blob/panel layouts,
leaving settings_v1 intact for app rollback. No token in GET/telemetry/build.
The worker defers unregistering one second after a save; generation checks
prevent publishing obsolete configurations. Status counts actual registered
connections. Public requests require the configured HTTPS hostname and a fixed
dashboard allowlist; origin is always loopback. Cookie/Origin/query retention,
remote authentication and settings redaction stay enforced. OTA/Wi-Fi/device WS
remain private. PageKite client and active tests removed; copies preserved in
.cache/cloudflare-integration/pagekite-legacy/ (includes preexisting dirty work).

Unchanged login C template is now gzip at build time, with byte-exact host
comparison including versioned font URLs. -Os and LTO scoped to the two new
protocol libraries retain existing partitions, SDK IRAM and watchdog objects.
Final normal ESP-IDF6.0.3 image: 1532320 bytes, 3680 bytes OTA headroom.
SHA256 a8d61e078d2865f393f0e5f3834f146e20ac4dfbf87fdbe0f00051be2f846e49.
Build/ELF/bin/config and validation.json: .cache/cloudflare-integration/.
Host sanitizer/policy/NVS/allocator, login, settings UI, assets, auth, Sheets,
Bosch and stack regressions pass (commands listed in validation.json).
Chrome UI QA subsequently passed via native CUA on localhost:8788 with only
synthetic data: save/reload, masked/cleared token, blank-token preservation
indicator, disable/re-enable, Undo and active-count feedback. Fixed Alpine
select hydration: literal option values now display the saved count after
reload (previously showed 1 while the saved value/status was 4). Token field
also has autocomplete/manager-ignore hints. ui-validation.json records cases.
Integrated PSRAM/four connection behavior and full-app runtime stability remain untested. Monitor
not attached via USB; only the prototype S3 and separate display were present.
No commit/push. Candidate normal config does not include the optional UART
dump overlay; do not treat this as a diagnostic production deployment.


## 2026-11-03 PR sleep-test rejection handling corrected

Only PR test_int_wdt.c changed: 100 successful sleeps per core within 1000
attempts, check restored IWDT mode after ESP_ERR_SLEEP_REJECT, fail on any
other error, and log attempt/success/rejection counts. Production code unchanged.
PR19359 remains one commit, now f90a92f1044022870ad151240805e246d8080014.
Master hardware confirmation on PICO-V3-02: 56 selected Unity cases passed,
0 failures/errors/runtime skips, 90.01s. Both cores: 100 attempts, 100 successes,
0 rejections. Thus real rejection rollback was not exercised by this run.
A local extracted-worker ASan/UBSan harness checks success, 1000-rejection
exhaustion, other errors, mixed retries and failed rollback. Official style
checks pass. Artifacts: .cache/iwdt-master-test/rejection-rerun-confirm/;
image/source/harness in sibling rejection-rerun/. First broader run had one
host-runner timeout; UART later contains PASS for that case. Confirmation
rerun with host kept awake passed. Preserve both runs; do not treat the first
runner failure as a firmware assertion failure. PR validation text updated.
Original app slot restored with verified hash; boot ELF91bbafd37, MCP9601 and
WiFi confirmed. Monitoring remains paused.



## 2026-11-03 final disable read-back reviewed locally

Owner approved investigating simplification. Compared current v3 against only
removing final disable register verification. Both pass all224 scenario
expectations /407950 runs in the existing bounded model. Synthetic post-commit
register corruption is detected as abort by current code and missed by the
variant; that is diagnostic coverage, not evidence of an actual hardware fault.
See tools/iwdt_review/DISABLE_CHECK_COMPARISON.md and reproducible scripts.
Conclusion: final disable check is defensive, not shown necessary under model
assumptions. Retry bound/pre-idle/enable failure paths unchanged. No production
source, PR or device changes in this investigation.

## 2026-11-03 master-port build and hardware regression completed

PR19359 head fe161f61a333507ba2d3d074fd42c6eb052218ab is built with master
0e6b480f858c69862ffb6001d96e9eef74599a6e and required Xtensa GCC16.1 toolchain.
Added explicit hal/mwdt_periph.h include for TIMG_WDT_WKEY_VALUE (master no
longer included it). All official pre-commit checks pass with submodules.
56 selected native esp_system Unity cases passed on connected rev3.1 monitor,
2MB PSRAM,160MHz default,800ms active IWDT; original v6.0.3 bootloader retained.
Artifacts .cache/iwdt-master-test/monitor-suite/ include bin/ELF/map, JUnit,
UART, sdkconfig, source commit and restoration proof. Original app693379f6 /
ELF91bbafd37 restored with flash hash check, sensor and WiFi boot confirmed.
No production candidate deployment; monitoring remains paused. PR text updated.

Minimal reorder+mode-flag alternative tested locally via
tools/iwdt_review/compare_minimal.py. Same bounded grid:216032 runs per variant;
minimal2144 bad final states and20644 panics; v3 allOK. Concrete WPROTECT
interleaving and limits in tools/iwdt_review/MINIMAL_COMPARISON.md. This is
model evidence, not hardware reproduction; no model claim added to PR.

## 2026-11-03 upstream draft PR published

Owner authorized fork/PR. Existing LeonB/esp-idf fork now has branch
codex/iwdt-livelock-transition, commit b8c32bacdfd69e7fa35d90768b06883cf76b7a69.
Draft PR https://github.com/espressif/esp-idf/pull/19359 targets master
0e6b480f858c69862ffb6001d96e9eef74599a6e. Checkout /tmp/esp-idf-iwdt-pr.
Six files only; retains upstream CPU1-idle tick handling. Extracted host C
ASan/UBSan passes after port, including CPU1-idle gating. Pre-commit passes
with cleanup-ignore-lists skipped because submodules are absent. Full master
build/hardware tests remain pending; PR distinguishes v6.0.3 hardware evidence.
No model claim or raw dump published; only relevant symbolized frames.
No device access or firmware change in PR preparation.

## 2026-11-03 native IWDT hardware tests passed; original firmware restored

Owner authorized hardware tests on the connected flue-monitor (ESP32-PICO-V3-02
rev3.1). The exported v3 SDK patch passed both added native Unity tests with
2 MB PSRAM, 160 MHz CPU and active 800 ms IWDT: 32 tick/mode rounds and 100
20 ms timer-woken sleeps per core. Test-only worker deletion was corrected
to wait for suspension after an initial teardown leak failure (4488 bytes).
The rerun passed including leak checks; production patch unchanged.
Exact artifacts and logs: .cache/iwdt-hardware-test/monitor-run2/.
Test image SHA256 c0d100234751fb22f3c4e9bf0e67e552211b7c6657258bbeb8aca27d9becaa39.
Only active app slot 0x20000 was written. Its full validated backup was restored
with flash hash verification; boot confirmed original ELF91bbafd37, MCP9601
and WiFi IP. Production remains image693379f6, not v3. Monitoring stays paused.
This is short integration coverage, not deterministic race injection, a soak,
or proof of hardware memory ordering. Owner then requested broader regression
coverage: 55 selected native esp_system cases passed in 91.49 seconds, with
zero failures/errors/runtime skips. Four upstream ignored cases and one
NVS-writing time test were excluded. Exact suite logs/JUnit/inventory and
restoration evidence: .cache/iwdt-hardware-test/monitor-suite/. After this run
the original full slot was again hash-verified and booted as ELF91bbafd37,
with MCP9601 and WiFi confirmed. Other targets/configurations and separate
UART-output/stack-smash pytest checks remain untested.

## 2026-11-02 IWDT v3 candidate built, NOT deployed; monitoring remains paused

Owner authorized correcting the host model, testing v3 and building a candidate.
No device/network/serial access, flash, OTA, induced crash or recorder restart
was performed. The previous image 693379f6 remains the last known deployed
image; monitoring was explicitly paused by the owner. Older “soak running”
notes below are historical, not current instructions to restart monitoring.

The current project-local patch observes INT_RAW and both handlers' app/pro/sync
bookkeeping under rsil5, writes/verifies a fresh long stage, checks idle again,
then changes the mode. It does not feed while it observes a handler in flight.
The tick uses the existing lock and the current mode, not the transition loop.
Read-backs cover WPROTECT and both stage values; they are checks, not a mutex.
The generated SHA-pinned highint_hdl.S only adds three .global declarations;
the SDK installation and handler instructions are unchanged. Explicit MEMW
compiler/hardware barriers surround the volatile handler-state observation.

Corrected host model and bounded regression matrix: tools/iwdt_review/.
Fixes include an active WDT stage with a per-stage counter, separate C shared
loads/stores, split handler cleanup/sync reads, both core scheduling orders,
periodic tick requests, and explicit per-scenario expected outcomes. The old
atomic IRQ smoke model is no longer used as evidence for race correctness.
224 scenarios / 407950 runs passed their explicit expectations: normal and
tick cases require no resets or invariant violations; deliberately expired
budgets panic, and hung-core cases reset. Injected long handler stalls can
panic/reset visibly; this is reported separately, never called healthy.
The original SDK race and deployed patch's CPU0 failure remain positive
regression controls (14 bad final states for deployed CPU0 in baseline sweep).
ASan/UBSan smoke tests, SDK fingerprint/assembly-source checks, safe dump and
flight-recorder regressions pass. Full safe diagnostic -Os build passes.

Candidate SHA256 3e34ad72c0f1c36774485d211dd46a79561aa42643836e8e2e84cd3fa263577c,
ELF SHA256 78a6450f41fca334887bea449477545636e5067c86831ea01ed79073c9090b32,
size 1424480 bytes. Exact bin/ELF/map, generated sources, patch/test snapshots,
model-results.json, transition-disassembly.txt and validation.json are in
.cache/watchdog-diagnostics/3e34ad72c0f1c367/. Relevant functions are in IRAM,
handler state in internal DRAM. 800ms IWDT, PSRAM, automatic light sleep,
flight recorder and safe UART dump retained; no crash self-test/full-heap dump.
Built from the current working tree, which contains unrelated preexisting work.

Limits: not hardware-tested. The host model assumes coherent DRAM and ordered
completed APB writes at SDK MEMW boundaries; it is not a weak-memory/silicon
proof. Cycle costs are parameters, several assembly operations remain grouped,
and sampled cross-products are not exhaustive. The separate SDK sync-miss
question is not repaired by this patch. The original incident cause remains
strongly indicated, not proven from uncaptured peripheral registers.

## 2026-11-01 IWDT sleep-transition candidate deployed; soak running

The complete spontaneous dump around15:56UTC (16:56 local) is preserved in
.cache/watchdog-captures/incident-20261101T1556Z/ with exact ELFf6be49cfc.
CPU0 IDLE0 was interrupted at the entry instruction of
wdt_hal_write_protect_disable, after the sleep helper reset the ECO3 livelock
counter/max to0 but BEFORE configuring/feeding the longer800ms hardware stage.
The level4 handler treats max0 as immediate panic. This is a strong transition
race candidate, not a proven hardware timeline: peripheral registers/last-feed
time are absent from the dump. Do not attribute the earlier06:04 reset to it
without further evidence. analysis.json and transition-evidence.txt distinguish
captured facts, control-flow inference, and missing state. GDB's hal=0xc80 at
the pre-entry PC is a windowed-register argument artifact, not a bad pointer.

Owner requested the next repair/regression step. Project-local CMake generation
now replaces int_wdt.c and eco3_livelock_workaround.c only for this monitor's
ESP32 ECO3 configuration; installed SDK is unchanged. Generator rejects changes
to the three reviewed SDK C/assembly source hashes. The candidate serializes
handler-mode updates and tick feeds with the same existing spinlock. It first
extends/feeds the hardware while keeping the OLD handler mode and high IRQs
enabled. It then briefly masks level4/5, reads pending BEFORE stage0, and retries
with high IRQs restored if pending or the recovery handler restored20ms.
Only after validating no pending IRQ plus the long hardware deadline does it
commit the new handler mode and hardware stage. No pending IRQ is cleared by
the patch. The tick respects sleep mode, including when CPU0 ticks just after
a CPU1 transition. The bounded masked commit must stay IRAM/internal-memory
only with no waits/locks; its hardware timing is not measured yet.

tools/test_iwdt_transition.py executes extracted SDK/generated C with an IRQ/HAL
model: old ordering panics;12 interrupt-boundary cases,6 delayed IRQ drains,
exhausted-watchdog behavior, enable/disable, both-CPU tick gating, and a queued
tick after sleep-mode unlock pass under ASan/UBSan. Changed SDK is rejected.
These are modeled interleavings, NOT an exhaustive Xtensa/silicon proof.
Existing dump-watchdog and flight-recorder regressions pass. Full6.0.3 safe
diagnostic size build passes; actual ELF confirms transition and called helpers
in IRAM, pending/stage read ordering, and rsil5/PS restore. Runtime IWDT remains
800ms; automatic light sleep, PSRAM, flight recorder, and safe UART dump stay
enabled; no self-test/crash command or full-DRAM heap capture.

Candidate binary SHA256693379f6eea4ccc7e7fec335ac02c4e4b5586f36a10ef8f9d46927734c875282,
ELF91bbafd370e18b1f3df88bd455bc8716ff20c0f6a43f42389559d60b7182225d,
size1424192 bytes, OTA headroom111808. Exact ELF/bin/map, generated source,
patch source, disassembly and validation.json are archived together at
.cache/watchdog-diagnostics/693379f6eea4ccc7/.
Owner subsequently explicitly approved OTA installation and ongoing soak.
Upload accepted2026-11-01T19:17:40UTC; planned software-reset(reason3) boot
around19:17:42UTC. UART confirms ELF91bbafd37; network telemetry confirms
reason3, light_sleep_enabled=true,2MiB PSRAM and real thermocouple readings.
LAN and public auth/status both200 at19:18:18UTC; PageKite reconnect succeeded;
Sheets logged status200 at uptime42s, telemetry successes1 at uptime50s.
This is a successful initial recovery check, NOT proof of long-term stability
or causal confirmation. .cache/watchdog-diagnostics/693379f6eea4ccc7/deployment.json
and validation.json record deployment; the prior8307c290 image remains archived.
USB/network recorders were not stopped/reopened; no device settings changed.
Automation prompt and watch-review.json now identify the new image and planned
OTA gap/reset. Continuous soak has no end time. No further deployment or
induced-crash test is authorized by this completed installation approval.

## 2026-11-01 safe dump hardware-verified and deployed

Owner explicitly requested hardware verification. Temporary self-test firmware
SHA25605d231c1c2c67ddf980fe8995f21bbe8fa3da1352e937e00f94fbd39aabb92ae,
ELFc9777b46a, installed by OTA around08:57UTC on confirmed monitor. Added
FLUE_DIAG_WDT only in the explicit self-test build: known stack/recorder markers,
then spin inside heap_caps_walk callback while multi_heap_walk owns its lock.
Interrupts are disabled there deliberately; runtime watchdog settings unchanged.
First UART command was not received (light sleep); a second, newline-delimited
command during LAN keep-awake traffic triggered exactly one controlled IWDT.

At08:59UTC this produced a COMPLETE Base64 UART dump, valid SDK checksum,
all4 stack marker words and102 committed recorder entries (4 sleep records).
Official ESP-IDF6.0.3 decoder identifies flight_test, watchdog_with_heap_locked
and the owning multi_heap_walk call. No nested panic. This verifies an actual
IWDT while holding a heap lock, not the original PM deadlock or all crash modes.
Exact test ELF, raw capture, source, decoded-info and verification.json are in
.cache/watchdog-captures/controlled-iwdt-20261101/. Heap patterns intentionally
not captured/verified; arbitrary memory remains private.

Normal safe diagnostic image8307c290e28d3f1a (ELFf6be49cfc) restored by OTA
around09:00UTC; UART confirms exact ELF. No test command/task in this image.
LAN/public auth endpoints both200 after startup. Real thermocouple readings
resumed. No saved settings/credentials changed. USB reader handed over cleanly
and restored to capture_readonly.py, DTR/RTSfalse, session25706. Network recorder
remains session74104. Automation now knows new firmware and planned test resets;
watch-review.json tracks cursors, per-boot minima and the test artifact.
During restoration of the read-only reader, a further power-on reset(reason1)
was observed around09:00:28UTC. Timing coincides with reader handover despite
DTR/RTSfalse; no reset command was sent, but reset-free opening is NOT proven.
Owner informed; same final ELF remains active. Subsequently PageKite connected,
real sensor readings and one successful Sheets upload confirmed. Do not blindly
reopen USB during monitoring.

## 2026-11-01 panic dump avoids heap locks, built but NOT deployed

Spontaneous IWDT around06:04:30UTC (07:04 local), network reset_reason5.
UART initial panic is partly garbled; CPU1 backtrace waits in the PM spinlock
while leaving idle. A subsequent CPU0 IWDT during core dump traverses
heap_caps_walk -> multi_heap_walk -> heap lock; it re-enters core dump and
reboots without a Base64 dump. Original watchdog cause remains unproven.
Incident fragment, matching deployed ELF and decoded backtraces are preserved
in .cache/watchdog-captures/incident-20261101T0604Z/.

Diagnostic overlay now DISABLES ESP_COREDUMP_CAPTURE_DRAM. IDF6.0.3 retains
task registers/TCBs/stacks, interrupted stack and explicit COREDUMP_DRAM_ATTR
regions, including flue_trace. Arbitrary heap/PSRAM and full globals are omitted.
dump_watchdog.c rejects full-DRAM capture at compile time when recorder enabled:
a halted core may own heap locks, so extending RTC timeout cannot fix this.
Panic-only RTC extension, runtime watchdogs, light sleep and task sizes unchanged.

Host timeout/negative-config and flight recorder regressions pass. Verifier
checks stack/recorder by default; --expect-heap additionally verifies archived
full-heap self-tests. Both paths pass against the archived controlled abort;
this is decoder regression evidence, not a new hardware crash test.
Official6.0.3 size build passes (1424064 bytes,111936 OTA headroom). Compiled
espcoredump archive has NO heap_caps_walk reference; ELF confirms flue_trace
inside the explicit dump region and no controlled_crash command.
Artifacts and safe-dump-validation.json: .cache/watchdog-diagnostics/8307c290e28d3f1a/.
Binary SHA256:8307c290e28d3f1a6743cefff1ed880250600f8af12c97f3607e025a1a7116e9.
NOT flashed/rebooted/crash-tested; live monitor remains b1659beb/ELF28191e655.
This removes the observed heap-lock failure route; it does not guarantee
successful capture for every corrupted-stack/cache-disabled/watchdog failure.

## 2026-10-31 extended dump + flight recorder deployed and crash-tested

Owner explicitly authorized implementing full heap capture/recorder and a
controlled hardware crash. USB /dev/cu.usbserial-5C671828951 was confirmed from
fresh boot logs: project flue-monitor, rev3.1, MAC8c:94:df:0b:be:fc, real MCP9601,
LAN192.168.1.137. A raw UART reader with DTR/RTS disabled started before OTA.

Diagnostic overlay now enables ESP_COREDUMP_CAPTURE_DRAM and FLUE_DIAG_RECORDER.
New shared flight_recorder component compiles to no-ops in normal/display builds.
Recorder: per CPU96 operational +32 sleep16-byte records (4120-byte internal
structure including metadata), with a separate528-byte RTC tail. Commit-last
sequence, local interrupt masking, no spinlock/heap/logging in write path.
Record/sleep functions verified in IRAM. Early sleep callbacks use cycle clocks;
normal events use low32-bit microseconds. Sleep banks prevent idle-cycle flooding
of network history. Events include sensors, WiFi, Sheets/Bosch, PageKite, settings
NVS, OTA, allocation failures and10-second heap samples. Values never contain
credentials/payloads. RTC tail validates magic/version/commit and replays at boot;
not guaranteed to survive all resets/power loss.

Explicit --self-test build adds only a physical UART FLUE_DIAG_CRASH command,
no HTTP endpoint or automatic crash. It creates known256-byte internal/PSRAM
patterns, volatile stack markers and300 recorder events before abort. First
attempt (artifactc1f527d8038c12aa) began dumping but hit the panic RTC watchdog
after about10s, ending in RTCWDT_RTC_RESET. This is a PLANNED diagnostic failure,
not a recurrence of the original spontaneous watchdog problem.

Fixed with a version-guarded project linker wrapper around esp_core_dump_write:
only during the dump, RTC timeout becomes600000ms, then returns to10000ms.
Runtime800ms IWDT/TWDT remain unchanged. Direct HAL tick calculation casts to
uint64 BEFORE multiplying: SDK helper's32-bit multiplication overflows for such
long timeouts. Feed before restoring the shorter timeout. No SDK files patched.
Host test_dump_watchdog verifies restore/call order and150kHz/32kHz arithmetic;
test_flight_recorder covers both cores, wrap/order/commit, isolated sleep banks,
IRQ restoration, failed allocations and RTC replay. Protocol/settings/Sheets/
OTA sanitizer regressions also pass. Display5.5.5 and normal monitor6.0.3 builds
pass with diagnostics disabled; normal binary remains0x175ff0.

Second controlled abort (artifact2525c1cea1d96e07, app ELF prefix2f108a192)
produced a COMPLETE UART dump with valid SDK checksum. verify_flight_dump.py
read back all256 internal bytes, all256 PSRAM bytes, all4 stack markers, and173
valid records including64 sleep records and wrapped/crash markers. Official
esp-coredump decoding identifies flight_test on core0 and controlled_crash at
flight_recorder_self_test.c:45. On reboot32 RTC records replayed, including the
crash marker. This validates abort capture with readable memory, NOT every IWDT
or cache-disabled failure. Allocated8-bit heap is captured, not raw unused2MiB.

Final non-self-test image deployed OTA successfully; no crash task/test markers
in ELF or boot. SHA256
b1659beb1025bd55aca2b199538338f20c5744ed1b66b3f8b065d53d807bc858;
ELF prefix28191e655; size1424704=0x15bd40,111296 bytes OTA headroom. Exact artifacts
in .cache/watchdog-diagnostics/b1659beb1025bd55/, test ELF in2525c1cea1d96e07/.
Postboot UART confirms real readings, PageKite AUTHENTICATED and one actual
Sheets200/ok upload. No credentials/settings erased, no task stack reductions.

Verified dump, decoded report, recorder JSON, raw UART and SHA metadata are
local in .cache/watchdog-captures/2525c1cea1d96e07/ (private permissions). Raw
memory can contain secrets: do not paste its arbitrary contents into tool output.
The ongoing raw UART file was renamed on the same filesystem while preserving
the open reader descriptor; /tmp/flue-flight-capture/serial.raw is a symlink to
it. Reader script/status/control files remain in /tmp/flue-flight-capture/.
Capture currently runs in exec session76652; a stop file in that directory stops
it cleanly. This is USB capture, not a restarted twelve-hour network automation.

## 2026-10-31 watchdog diagnostic build fits OTA with -Os, NOT flashed

Owner requested building UART core dumps, a separate internal dump stack,
stack-end watchpoint and light heap poisoning, and checking existing OTA fit.
main explicitly depends on espcoredump (inert when disabled). The tracked
sdkconfig.watchdog-diagnostics.defaults overlay is applied to a COPY of the
normal active sdkconfig by tools/build_watchdog_diagnostics.sh. No normal config
changes. UART dumps start automatically (delay0), include up to64 task snapshots,
use a2048-byte dedicated internal stack and IDF Monitor info decoding. Full DRAM
capture remains off; PSRAM heap is not included. Existing panic-in-IRAM/canary,
800ms IWDT, light sleep, PSRAM-only allocators and task reservations are retained.

Without size optimization the binary is0x1797d0=1546192 bytes:10192 bytes TOO BIG
for either existing0x177000=1536000-byte OTA slot. The successful --size variant
uses -Os with -ggdb retained, and includes all current working-tree PSRAM buffer
changes. Build/watchdog-diagnostics-size binary is0x15a520=1418528 bytes, leaving
117472 bytes (7.65%). SDK app size check passes. Partition-table binary matches
normal build byte for byte. Generated sdkconfig confirms all diagnostic flags;
ELF has debug_info and linked UART core-dump / heap-poisoning routines. These
are build/integration checks, not hardware crash-capture or stability validation.

Binary SHA256:80f0ae1dd9dd1a090311334ce33cff5b06629074b30b1b88a24f64045649b20a.
Exact binary/ELF/map/sdkconfig/compile commands/partition table and SHA manifest
are preserved together in .cache/watchdog-diagnostics/80f0ae1dd9dd1a09/.
Use THAT ELF for a dump from THAT binary, not normal build/flue-monitor.elf.
The normal ota_flash.sh still selects normal build/flue-monitor.bin, so explicit
diagnostic artifact selection is required for any later authorized deployment.
No device contacted, flashed, rebooted or deliberately crashed for this task.

## 2026-10-31 sensors/Sheets/Bosch stack buffers reduced, NOT flashed

Owner requested extending the PSRAM buffer work to these workers. Sensors'
360-point graph history already uses strict PSRAM. Its zone classifier now
obtains only the two thresholds through mutex-protected settings_get_zone_limits,
eliminating the full settings copy without introducing a sensor allocation.
Small regression arrays, I2C/ISR state and all task stacks remain internal.

Sheets uses a single boot-lifetime strict-PSRAM workspace for its settings
snapshot and576-byte URL. Initialization failure frees partial allocations;
event submission returns false until the worker is ready. Queue/task creation
failure is checked and retrying init is safe. HTTP client allocation failure
returns without advancing the upload baseline. Bosch's1024-byte callback code
and256-byte resource URLs now use strict buffer_memory allocations; callbacks
wipe/free code on rejection and after form creation. Existing responses/tokens/
forms remain in PSRAM. No credentials, settings or cloud resources changed.

Compiler frame sizes (bytes) before/after this change: classify_zone832->64,
log_to_sheets880->304, sheets_logger_task960->176, command1104->112,
discover_zones288->32, poll_temperature304->48. These are not measured task
peaks. Sheets' earlier6928-byte minimum was FREE space within its12288-byte
reserved internal stack (estimated peak5360), not6928 bytes used. Stack
reservations remain unchanged until runtime normal/error/reconnect paths are
measured again.

ASan/UBSan test_sheets_memory.py runs actual worker/upload/init and classifier:
zone boundaries, PSRAM/queue/task/client allocation failures, complete periodic
and event URLs, snapshot age/temperature, unchanged retry baseline on rejected
or failed transport, and resource cleanup pass. Bosch sanitizer tests cover
callback-code and URL exhaustion without network calls, valid code exchange
and existing protocol/token lifecycle. Actual settings getter/validation tests
also pass. Official6.0.3 build passes:0x175ff0,4112 bytes OTA headroom. Not flashed.

## 2026-10-31 PageKite and HTTP local buffers moved to PSRAM, NOT flashed

Owner requested moving large local PageKite buffers and the same for HTTP.
PageKite allocates a single 6392-byte private workspace using psram_buffer,
without internal fallback. DNS, authentication and session phases overlap in
a union; simultaneously live receive/prepare/reject buffers are separate.
Workspace allocation happens once before stack registration, with complete
partial-startup cleanup. Reconnect/longjmp reuses it without allocating again.
Challenge answers must be explicitly NUL-terminated after each append: the
workspace is reused and is not zero-initialized like the previous local array.

HTTP login bodies and settings GET/POST snapshots use buffer_memory with
per-request ownership and cleanup on every exit. Existing JSON/body/history/
asset/WS allocations retain their strict policy. Shared OTA's 1024-byte input
buffer also uses buffer_memory, allocated before esp_ota_begin and released on
all failures and before finalization/reboot. ESP-IDF 6.0.3 esp_flash_write stages
non-DRAM input in a small internal buffer before disabling the cache; this
does not permit external task stacks or cache-disabled code to access PSRAM.
OTA now depends on captive_portal for buffer_memory. The display's build-time
non-PSRAM policy still uses internal RAM; there is no runtime fallback.

Compared with the preserved deployed ELF, compiler frame sizes in bytes:
authenticate3920->224, auth_header_for1104->80, prepare2656->272,
receive1616->592, session_loop2256->64, reply816->48,
settings_post_handler1776->240, settings_get_handler816->32,
auth_form_handler704->192, ota_post_handler1088->80.
These are individual compiler frames, not measured task peaks. Reserved stack
sizes remain unchanged; no internal heap saving from stack shrinking is claimed.

ASan/UBSan PageKite tests cover all three startup allocation failures,
dual-domain challenges after dirtying/reusing workspace, rejection/reconnect,
existing routing/framing/queue tests and exact buffer capacities. Settings tests
cover snapshot allocation failure without NVS writes and existing validation/
redaction. test_http_psram_buffers.py checks fragmented login/OTA input,
allocation/read/write/begin/end/boot failures, timeout retries and cleanup.
PSA known vectors, strict TLS allocation and stack diagnostic tests pass.
Monitor6.0.3 build passes:0x175df0 bytes,4624 bytes OTA headroom. No flash,
reboot, device settings changes or runtime stability claim for these changes.
Shared OTA compatibility also builds with display5.5.5 (0x10afb0 bytes,
29% OTA headroom), using its existing Python3.14 environment. No display flash.

## 2026-10-31 six-task stack telemetry deployed

Owner requested adding actual stack measurements. stack_diagnostics registers
the long-lived main/sensor/Sheets/Bosch/PageKite/HTTP task handles; main scans
uxTaskGetStackHighWaterMark every10s outside critical sections. No extra task or
FreeRTOS trace facility. HTTP registers through its own queued callback; failed
diagnostic registration only logs, never aborts boot. PageKite registers after
startup allocation succeeds, so a deleted failed worker cannot leave a handle.
Registered tasks must remain alive until reboot; unregister before introducing
any future task deletion. Explicit sizes are shared with creation sites; all
stack sizes stay unchanged. Unknown/unmeasured slots are omitted.

memory.stacks contains size_bytes/min_free_bytes/peak_used_estimate_bytes per
task. ESP-IDF high-water marks are bytes; peak use is estimated from untouched
fill bytes and resets each reboot. It does not prove worst-case usage. OTA's
last HTTP peak cannot survive its reboot without a separate pre-reset capture.
Current JSONL recorder automatically retains the nested fields. Heartbeat
updated to track them and distinguish both planned OTA resets.

ASan/UBSan host test_stack_diagnostics.py executes actual implementation with
real cJSON/task shims: byte arithmetic, lifetime minima, absent/invalid slots,
zero headroom, scanning outside locks, failed JSON allocation and2048-byte WS
frame budget pass. PageKite routing/queue regression passes. Build0x175e80
(1531520 bytes,4480 OTA headroom); SHA256
6bca784e6445002c48f41f67aa7dc56df997916bafbd3e8034c78af36e96775e.
OTA to confirmed .137/MAC8c:94:df:0b:be:fc returned OK, rebooting. First recorded
stack sample23:23:17UTC uptime20/reset_reason3 (planned OTA) includes all6 tasks;
both PSRAM-only flags/light sleep remain true, PageKite and real43.7C working.
LAN/public auth endpoints200 and dashboard password retained. Initial minimum
free stacks: main632, sensor2064, Sheets10880, Bosch4204, PageKite5720, HTTP5040
bytes. Sheets had not uploaded yet in that sample; do not trim based on it.
Main is already much tighter than other tasks. Keep measuring normal/error/
reconnect/login paths before any stack reduction. No stack sizes reduced.
At uptime60s, one real Sheets upload succeeded; minimum free Sheets7136 bytes,
PageKite4488, sensor2048, Bosch4204, HTTP5040 and main632. Both strict PSRAM
flags remain true, internal minimum119360. Verified deployment event recorded
with the six-task snapshot. Existing recorder continues through11:05UTC.

## 2026-10-31 full PSRAM-only firmware deployed

Owner explicitly authorized deploying during the twelve-hour capture, superseding
the earlier no-deployment constraint. Normal sdkconfig AND sdkconfig.defaults
now select MBEDTLS_CUSTOM_MEM_ALLOC; all application buffers, PageKite and
Mbed TLS/PSA use strict PSRAM allocations without internal fallback. No services
disabled; PSRAM2MiB, automatic light sleep and800ms IWDT remain enabled.
Memory telemetry now exposes buffer_psram_only and tls_psram_only.

Official6.0.3 build0x175af0 (1530608 bytes,5392 bytes OTA headroom), SHA256
ed49a89fcd474567bc23c111f178b2f5514ed7b2c03605e6380055f47dcb4a85.
OTA sent23:13:34UTC to confirmed monitor .137/MAC8c:94:df:0b:be:fc;
full upload returned OK, rebooting. First new WS sample23:14:12UTC uptime20,
reset_reason3 (planned software reset), both strict flags=true, PageKite
connected and real45.4C thermocouple. LAN/public auth status succeed and saved
dashboard password remains configured. This verifies deployment, not a soak.
First internal minimum99756 versus1124 before deploy; early sampled largest
block98304 versus49152 previously. Different boot ages/workloads; await actual
cloud/Sheets activity before drawing memory or stability conclusions.

Postboot uptime50–70s confirms one real Sheets attempt/completion/success,
PageKite connected and both strict flags true. Internal free about139kB,
minimum96504 bytes, largest110592, sampled largest minimum94208. PSRAM free
2047532/minimum1981012. LAN/public auth endpoints200; public identity loading
asset200/5170 bytes verifies PSRAM-backed inflation through the tunnel. This
is a short smoke test, not long-term stability proof. Bosch's authenticated
room-temperature status was not read; no owner session/credentials accessed.
deployments.jsonl includes planned_ota_verified with the successful telemetry.

Recorder continues in /tmp/flue-watch-12h through11:05UTC, deployments.jsonl
marks planned OTA and first new sample. Heartbeat prompt updated to distinguish
this intentional reset and compare pre/post firmware separately. Prior snapshots
under /tmp/flue-psram-candidates remain available. No credentials/settings erased.

## 2026-10-31 all application buffer allocators made strict, NOT flashed

Owner requested the other allocators follow the same no-internal-fallback
policy. Shared buffer_memory now uses SPIRAM|8BIT exclusively when CONFIG_SPIRAM
is enabled; absent/full PSRAM returns NULL and logs an allocation failure.
Builds without PSRAM (display) explicitly allocate INTERNAL|8BIT instead. This
is a build-time hardware policy, not a runtime fallback. History, cJSON hooks,
Bosch payloads/tokens/forms and asset inflation therefore become strict too.
Settings POST bodies and WS queued work/payload copies also use buffer_memory;
WS drops NULL JSON safely and frees partial allocations/failed queues.
Internal diagnostic overrides and SDK/task/driver allocations remain separate.
This supersedes the earlier paragraph saying the other buffer policy is unchanged.

Sanitizer history tests verify full data/cleanup, exhausted-copy503 and auth;
settings tests cover failed-body500 before receiving/writing data; WS tests
cover both allocation failures, payload ownership, queue/send failure, stale
sessions and NULL JSON. Actual asset decoder tests cover strict monitor PSRAM
failure with no internal fallback and internal-only display success. Bosch
protocol/lifecycle regressions also pass. Normal monitor6.0.3 build0x175a60
(5536 bytes OTA headroom); TLS variant0x175ab0 (5456 bytes). Display5.5.5 builds.
Snapshots: /tmp/flue-psram-candidates/application-buffers.{bin,elf}; latest TLS
variant remains tls-build/flue-monitor.bin. No hardware deployment or measured
RAM savings yet. Twelve-hour recorder/automation remains on existing firmware.

## 2026-10-31 PSRAM candidates built, NOT flashed

Owner approved moving PageKite buffers first and preparing TLS separately.
PageKite now allocates its4097-byte scratch buffer, stream table and queued
requests through psram_buffer (PSRAM only, per owner correction). Growth uses
allocate/copy/free instead of plain realloc, retains bytes/NUL and the old
allocation on failure. Startup frees partial allocations and reports failure.
Do not use sizeof(response_buffer) now that it is a pointer.

tls_memory_init runs first in app_main. Normal CONFIG_MBEDTLS_INTERNAL_MEM_ALLOC
is unchanged; only CONFIG_MBEDTLS_CUSTOM_MEM_ALLOC enables the boot-lifetime
PSRAM-only Mbed TLS/PSA hooks. Failed allocations are logged and never use
internal RAM. This changes all allocations
using these hooks, not only record buffers. No runtime hook switching.
Owner explicitly rejected internal fallback for these network buffers. Existing
history/JSON/assets/Bosch buffer policy is unchanged; only PageKite and the TLS
candidate use the strict helper. Task stacks, DMA, Wi-Fi and drivers stay internal.

ASan/UBSan PageKite routing/frame/queue tests pass, including failed request
growth and data retention. TLS host tests cover both config modes, hook failure,
strict PSRAM capability selection and logged exhaustion with heap/platform
shims, even while internal RAM remains available. Actual TF-PSA
credential/relay/DDNS known-vector test also passes. These are not hardware TLS
or stability tests. Both official6.0.3 builds pass and fit unchanged OTA slots:
PageKite-only0x1758d0 (5936 bytes free). TLS candidate rebuilt with the same
strict PSRAM policy; see /tmp/flue-psram-candidates/tls-strict-build.log for size.
Snapshots: /tmp/flue-psram-candidates/pagekite.{bin,elf,sdkconfig}; TLS config
tls.sdkconfig and tls-build/{flue-monitor.bin,flue-monitor.elf} in same folder.
The config diff consists only of internal→custom TLS allocator selection.
README documents separate config/build usage. Normal sdkconfig stays internal.

Neither candidate flashed, so actual RAM savings and hardware stability remain
unmeasured. Preserve the owner's twelve-hour existing-firmware capture through
2026-10-31 11:05UTC; recorder /tmp/flue-watch-12h/recorder.cjs and automation
flue-monitor-twaalf-uur-bewaken remain active. Do not silently deploy during it.

## 2026-10-31 reported outage, watchdog not yet confirmed

Owner reported monitor/webpage unreachable and explicitly confirmed interrupting
power before this inspection. Live WS at 2026-10-30 23:00:10 UTC showed IDF6.0.3,
uptime139s, reset_reason1 (POWERON), PSRAM2MiB and automatic light sleep enabled.
This explains the latest boot but cannot diagnose the pre-power-cycle outage.
Subsequent samples uptime169/179/189s remained on the same boot; LAN and public
root both returned303 (expected login redirect). PageKite connected, real flue
readings49C, three Sheets attempts/completions/successes.
Internal allocator minimum fell8400→1124 bytes; sampled largest-block minimum
6400 and Sheets sampled free minimum8368. Current free recovered to about99kB.
This is evidence of substantial transient memory pressure, not proof of its
cause or a watchdog. Bosch and Sheets have separate HTTP/TLS workers; active
sdkconfig keeps TLS internal with16KiB RX/4KiB TX and dynamic buffers disabled.
Concurrent TLS is an investigation lead, not a demonstrated cause. No firmware
or settings changed. Evidence: /tmp/flue-watchdog-20261031.jsonl. Monitor USB
CH9102 was absent; do not treat the other available USB board as the monitor.
Earlier30min IDF6.0.3 soak does not establish long-term stability.

## 2026-10-30 owner verification of final login flow

User confirms retained-startup + real /login navigation works on the iPhone
home-screen app without the redundant 1Password save prompt. Mac field
recognition also confirmed earlier. Final firmware deployed, public root303
/login, login HTML and updated startup source verified. Temporary AutoFill
routes/buttons removed. Bosch live room-temperature display confirmed by owner
screenshot; generic Sheets script updated by owner, firmware upload success
observed. These statements supersede earlier pending/deployment notes below.

## 2026-10-30 real login navigation, startup retained

Owner confirms direct-login test inside home-screen app does NOT trigger the
1Password save prompt. Keep the startup shell: root now redirects unauthenticated
requests303 to /login. loading.html recognizes the fetch's final /login URL and
uses location.replace rather than document.write for login HTML. Authenticated
dashboard insertion stays unchanged; offline/retry behavior stays unchanged.
/login uses the same handler/fields/authentication and is allowed by PageKite;
service worker intercepts only root navigations. Login script also navigates
from non-/login paths before touching fields, supporting old cached startup
shells. This makes login a real document navigation even during SW updates.
Temporary /autofill-direct and ?autofill_test=single routing and test buttons
removed. Tests cover startup navigation versus insertion, offline retry, legacy
shell guard, first-time setup/login/error flows, and worker/tunnel allowlists.
Final owner iPhone confirmation of this retained-startup flow still pending.

## 2026-10-30 home-screen direct-login experiment

Owner reports normal Safari does NOT show repeated save prompt. Added
/autofill-direct alias to the same authenticated root handler, allowlisted
through PageKite. Existing worker intercepts only pathname '/', so this alias
loads HTML directly without cached loading shell/document.write even with an
old active worker. Same login markup, fields, JSON authentication and success
redirect to '/'; default login unchanged. Test direct login links from login
and settings allow same-window navigation inside the home-screen app. Settings
button logs out current session first; failed logout shows error and does not
navigate. No credential or password changes. Host tests cover worker bypass,
PageKite routing, absent-confirm variant, login/setup and test logout behavior.
Path differs (same origin); if result changes, follow up to isolate path versus
shell loading. Owner iPhone/1Password result remains pending.

## 2026-10-30 controlled iPhone AutoFill experiment

Owner confirms Mac recognition fixed, repeated iPhone save prompt persists,
same PageKite URL in 1Password. Uses home-screen app and 1Password extension.
Do not assume iOS bug proves root cause. Normal login retains baseline form;
/?autofill_test=single removes only the unused confirmation input from the
server HTML when a password is already configured. Setup remains unchanged.
JS tolerates absent confirmation via detached input. PageKite preserves only
this exact root test query, other existing routing unchanged. Host login tests
include absent confirmation, PageKite tests include exact test-link forwarding.
First compare normal URL in Safari versus home-screen app. If Safari reproduces,
compare baseline and single-field test in same Safari context/autofill method.
Real iOS outcome requires owner; do not claim cause or solution yet. Candidate
remaining variables: password-only identity, async login, service-worker loading
shell document.write. Do not change all at once or invent a username.

## 2026-10-30 password-manager form semantics

User screenshot now shows live room19.9C after Bosch TX-buffer correction.
Reported repeated 1Password save prompt on iPhone and missed recognition on
Mac. Login form now has stable id/name, method=post, explicit login/setup
 action and submit button type. Hidden confirmation is disabled, aria-hidden
and autocomplete=off during normal login; enabled/new-password only for initial
enrollment. Password remains current-password for login. Actual inline-script
regression covers both modes and existing login/error flows. No account name
invented and no credentials accessed. End-to-end 1Password behavior still
needs owner testing; differing saved website origins may also matter.

## 2026-10-30 Bosch HTTP header buffer fix deployed

Owner paired but reported retrying/unavailable. Found authorized requests used
IDF default512-byte TX buffer; strict header buffering rejects longer Bearer
headers. TX capacity now token length+256 for authenticated resource requests.
Actual IDF header serializer regression (tools/test_bosch_header.py) reproduces
failure at512 and passes new capacity with synthetic600–8192-byte tokens;
protocol/UI tests also pass. Added nonsecret stage + HTTP/transport/JSON/size
failure detail to retry status. OTA completed and auth endpoint available.
Owner must reopen authenticated dashboard to confirm live Bosch temperature;
no authenticated status/actual token size read, so this remains a demonstrated
client bug and plausible cause, not confirmed full cloud recovery.

## 2026-10-30 asynchronous Bosch result feedback

UI tracks pending action through status polls, keeping explicit checking,
failure or connected-with-temperature feedback beside the controls. Callback
input clears only after connected+available, not merely HTTP202. Invalid or
old-link errors persist, with a clearer instruction to start a new sign-in.
C/UI host tests pass, including delayed connecting→connected and login_error.

## 2026-10-30 Bosch input feedback

Dashboard rejects malformed callback URLs before POST, retains the input and
shows an alert. Action errors persist across five-second status polls until
another action; previously fetchBosch erased them. Host UI tests cover malformed
input and persistent HTTP errors. Built and OTA uploaded to the same confirmed
monitor .137; local preview serves changed JS without server restart.

## 2026-10-30 Bosch + Sheets firmware deployed

User confirmed the generic Apps Script was updated, then requested OTA.
Built official IDF6.0.3 image0x175070 (8080 bytes free in OTA slot); Bosch C/UI
and actual Apps Script host tests pass. OTA to192.168.1.137 confirmed first by
ARP MAC8c:94:df:0b:be:fc returned OK, rebooting. Postboot WebSocket at uptime
30/40/50s reports real thermocouple23.4C, light_sleep_enabled=true,2MiB PSRAM,
PageKite connected and one Sheets attempt/completion/success. Public login
returns200; dashboard password remains configured. Internal low-water28520
bytes during first Sheets upload. This is a short smoke check, not a soak.
Bosch pairing/actual room-temperature transmission on device still requires
owner login and linking from the real monitor dashboard; mock preview is not
that device. No tokens/passwords transferred or owner session accessed.
Supersedes earlier not-flashed notes for these firmware/UI/Sheets changes.

## 2026-10-30 generic Sheets webhook (not deployed)

Code.gs now maps data by header name and appends new query keys automatically.
Legacy labels remain stable; secret/event_ts/age_ms are excluded, new keys must
match [a-z][a-z0-9_]{0,63}. Decimal values become numbers, absent values blank,
text is escaped against formula interpretation. Existing rows are untouched;
column reordering works, renaming a header creates a new original-name column.
ScriptLock covers header discovery, expansion, append and flush. Future fields
need only firmware query additions (and enough URL buffer); no script edits.
Actual-handler mock tests cover dynamic/reordered/wide schemas, secret rejection,
lock contention/release, text escaping and room-temperature validation.
Still requires one live Apps Script deployment update; no Google writes made.

## 2026-10-30 Sheets room-temperature field (not deployed)

Every periodic/event upload now includes room_temperature. Bosch exposes a
mutex-protected snapshot getter (no network); absent, failed, out-of-range or
>180s-old readings stay NAN internally and serialize as an empty query value.
Queued events capture it at enqueue time alongside the flue sample, not at
transmission time. URL buffer grows512→576 bytes; event queue adds one double
per item. Code.gs appends Room Temperature (C) as column G and separately sets
its one-decimal format even when existing B formatting already matches.
Missing/invalid data stays blank, valid zero survives, previous columns/rows
retain their meaning. Tests cover getter freshness and actual Apps Script
append/format/backfill behavior without Google writes.

The live Apps Script deployment is NOT changed. Preserve its real secret when
copying Code.gs, then Deploy → Manage deployments → New version. Firmware also
still needs flashing/pairing. Do not claim live Sheets rows contain this field.
The earlier room badge was rejected: approved UI is now a small house icon and
19,6° in the top-right toolbar beside Settings, without a card or frame.

## 2026-10-30 room-temperature presentation and zone dropdown

Dashboard room reading now sits in a neutral rounded badge immediately below
the flue glow, with a house icon, heading font and explicit unavailable state.
Room zone is a native accessible select. GET /api/bosch includes zones discovered
from validated /zones/zn* references, cached ten minutes per gateway, deduplicated
and capped at32. Discovery failure preserves prior options without blocking the
actual temperature read. UI retains saved/draft selection and numerically sorts
options. Mock provides zn1/zn2; browser verified selecting/saving each and
returning to the dashboard. C sanitizer test covers discovery/path rejection,
deduplication/cache/failure retention; JS covers dropdown fallback/sorting.
Preview server restarted on localhost:8777 with simulated connected19.6C.
Not flashed.

## 2026-10-30 Bosch POINTT cloud integration (built; not flashed)

Final ESP-IDF6.0.3 build: 0x1749c0 (1526208 bytes), 9792 bytes free in the
unchanged OTA slot; +10592 bytes versus the preceding full-feature image.
Existing optimization, certificate bundle, PSRAM and light-sleep settings unchanged.

`bosch_client.c` owns a read-only cloud worker and authenticated GET/POST
/api/bosch (also allowlisted through PageKite). UI uses the manually pasted
app callback from the proven Mac test; firmware generates fresh 256-bit PKCE,
state and nonce per attempt. Callbacks require the exact scheme/host/path,
matching state and a 20-minute lifetime. Tokens/codes are not in API responses,
settings or the device WebSocket. Do not add credentials to those device
surfaces. POST requires dashboard authentication and Origin; queued commands
keep the HTTP task free of cloud I/O. Only one user operation may be queued.

A separate `bosch` NVS namespace stores one credentials JSON record
(refresh token, device, zone). Rotated refresh tokens are saved immediately;
access tokens remain in RAM and are reacquired after boot. NVS is currently
unencrypted. Disconnect deletes local credentials, not cloud-side grants.
Polling is 60 seconds, bounded 24 KiB HTTP response, full certificate verification
and no redirects; transient failures back off 30–900 seconds, rejected refresh
credentials require reauthorization. Room values must be finite within -40…60C;
the observed unused-zone 1000 sentinel is rejected. Failed or >180s-old samples
are unavailable. A single discovered gateway is selected automatically; manual
serial/zone selection covers multiple gateways. Room temperature is shown
separately without changing flue classification, history, Sheets or display.

Task stack is 8192 bytes in internal RAM; response/token/form buffers prefer
PSRAM with internal fallback. Actual TLS peak memory, stack headroom, reboot
persistence and long-term cloud operation remain unverified on the ESP32.
No firmware was flashed and no real credentials were added to source/tests.
The earlier Mac test proves CT200 firmware05.04.00 cloud login, refresh and
zn1=19.6C, not this C implementation on hardware.

Host checks execute actual C under ASan/UBSan with NVS/network/RTOS shims:
test_bosch.py covers PKCE URL against independent SHA256, callback validation,
response limits, token rotation/restart loading, storage failure, auth/CSRF,
stale/invalid readings and disconnect. test_bosch_ui.js covers freshness,
callback clearing, selection and errors. test_pagekite.py covers Bosch route
forwarding with Cookie/Origin. Existing settings-sync regression passes.
Browser mock verified disconnected → pairing → connected, invalid zn2,
recovery to zn1 and dashboard temperature with no console errors.


## 2026-10-30 official ESP-IDF 6.0.3 migration (30-minute full-feature soak passed)

User requested 6.0.3 with all features. Official SDK installed alongside old
versions; activate-idf.sh and manifest select6.0.3. Removed custom5.5.6 sleep
backport and obsolete trace wrappers; SDK source diff is empty. cJSON now
comes from espressif/cjson1.7.19~2, with conditional shared portal dependency
so display5.5.5 still builds. PBKDF2/SHA1 calls use PSA APIs, preserving
credential/signature formats. Actual TF-PSA host-library known-vector checks
pass for credential hashing, relay auth and DDNS (tools/test_psa_crypto.py).
Auth/history/settings/assets/PageKite host regressions pass. Display builds.
Full monitor binary0x172060 (1515616 bytes),20384 bytes free in OTA slot.
PSRAM2MiB, automatic light sleep,800ms IWDT, all services and all full roots
remain enabled; no feature isolation, custom SDK patch or size optimization.
OTA to confirmed .137/MAC8c:94:df:0b:be:fc succeeded. Final boot about
10:05:01 UTC; WS confirmsv6.0.3 and light_sleep_enabled=true, real thermocouple
and PageKite. Earlier first6.0.3 trial boot at10:01 was deliberately replaced
at10:05 to add runtime sleep configuration telemetry, NOT a watchdog reset.
Display passive log confirms received measurements and settings acknowledgement.
Saved dashboard password remains configured; owner-authenticated dashboard
interaction is not tested (no password/session available).
Soak logs /tmp/flue-idf603/{telemetry.jsonl,web-soak.jsonl,display.log}.
At10:35:03 UTC, final-build uptime1806s with no unexpected reset. All telemetry
samples report light_sleep_enabled=true; sensor and PageKite remain active.
175 post-reboot web requests succeeded, alternating LAN/public and gzip/identity.
Only earlier request failure overlapped the intentional OTA reboot. Large startup
asset bytes, immutable caching and304 validated separately. Seven held HTTP
sessions plus ten abrupt WS disconnects leave server available. Display mid-soak
logs real23.5-23.6C readings, current settings acknowledgement and zero LED
refresh failures. One Sheets upload received the actual webhook "ok" response;
saved heartbeat is60min, so one is expected in this30min run.21 comparable
saved settings match earlier snapshot. Internal minimum55144 bytes, steady free
about111532 bytes. This passes a bounded30min test, not proof against future
long-delayed resets. Final binary SHA256:
5a71aa673a04031fd294b26ce43c6b6c9fd6f8db1056a2ad7028c299be4df0e6.
Activation script selects installed Python3.14 environment despite Homebrew3.15;
fresh-shell idf.py --version reportsv6.0.3.


## 2026-10-30 upstream PSRAM/light-sleep research (no firmware changes)

- d45606bf1d450924fbba25eb692ab7d7e27dee77 and parent6f1bea6a move the
  ECO3 watchdog back to its regular timeout while the other CPU is stalled.
  Merge8220859330 references internal IDFCI-7791 / MR45645; no public issue
  reproduction obtained. Our patch uses equivalent light-sleep call ordering.
- afbe171f481c777a13d72b626a427b123dc77f73 (July2026, PM-814) corrects lock
  ordering for DEEP sleep, not an additional missing light-sleep change.
- d4e3109c1b9c31f43c6f44d02c64e58878a46ed8 / merge344edcd13f37c5806f9559aca93bc4e99e1c3931
  (PM-779) changes critical-section handling during sleep using
  xPortThreadSafeClaim/Disclaim, also changes esp_timer lock order. Separate
  possible investigation lead, NOT established cause or safe standalone backport.
- Official raw sleep_modes.c tags checked: v5.5.6 lacks cache-sleep helper;
  v6.0.3 and v6.1 contain it. Neither inspected release contains the thread-safe
  claim calls; both retain IDF-5257 lock warning. An official6.x minimal A/B
  would remove our custom backport as a variable, not guarantee a fix.
- Issue11315 reports same PICO-V3-02 family and long-delayed RTC watchdogs,
  but with Bluetooth. Suggested XTAL wait/idle threshold changes did not solve
  original report; closed for lack of feedback, not confirmed fixed.
- Generic PSRAM power fixes2ceddff9 and29b51468 only change ESP32-P4 files.
  Not applicable to our ESP32. Half-sleep config is enabled but the ESP32
  PSRAM enter/exit/resume functions are empty stubs: not a useful first toggle.
- Actual config already has PSRAM/flash CS pullups, internal stacks,800ms IWDT,
  100Hz tick,40MHz PSRAM and IRAM panic handler; core dumps disabled.
  Auto light sleep with Wi-Fi is explicitly supported; manual sleep advice
  to stop radios does not apply to our power-management setup.
Sources: https://github.com/espressif/esp-idf/commit/d45606bf1d450924fbba25eb692ab7d7e27dee77
https://github.com/espressif/esp-idf/commit/afbe171f481c777a13d72b626a427b123dc77f73
https://github.com/espressif/esp-idf/commit/d4e3109c1b9c31f43c6f44d02c64e58878a46ed8
https://github.com/espressif/esp-idf/issues/11315
https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/sleep_modes.html


## 2026-10-30 full PSRAM soak FAILED after about23.5min

Telemetry at09:33:14 UTC reports uptime30/reset_reason5 (interrupt watchdog),
following last observed uptime1408s. Thus the full patched firmware has NOT
passed its30min soak; commit5963670 is not evidence of a complete fix.
Current deployed monitor remains the full PSRAM/light-sleep build541b1d5cc.
Continue diagnosis after completing the separately requested display update.
Evidence: /tmp/flue-sleep-ab/telemetry.jsonl. No automatic rollback performed.


## 2026-10-30 smaller app icons (built, not flashed)

Manifest now lists the existing stove SVG with sizes:any after PNG fallbacks.
Existing SVG route, MIME type, public PageKite access and asset versioning are
reused. Apple 180px and manifest 192/512px PNGs retain dimensions and are
palette encoded with ImageMagick (+dither -colors 256, PNG8, compression9).
Gzipped PNG total shrank from56187 to21352 bytes. Visual512px inspection
passed; normalized RMSE0.001561. Existing startup images and favicon unchanged.
Actual normal-config firmware1510096 ->1475296 bytes:34800 saved;60704 free
in OTA slot. Build and test_asset_versions.py passed. NOT flashed during
ongoing PSRAM/light-sleep stability soak; deployed image remains541b1d5cc.
Pre-change binary and PNGs preserved at /tmp/flue-icons-before.
Alpine already minified3.17.4,55891 raw bytes,about19.5KiB gzip, shared once
between portal and dashboard. No Alpine changes made.

## 2026-10-30 size exploration while stability soak runs

User asked to think about reducing firmware size. Separate, NOT FLASHED,
build-size-experiment uses /tmp/flue-sleep-ab/size-experiment.sdkconfig,
changing compiler DEBUG optimization to SIZE only. Measured binaries:
normal1510096 bytes; size1377984; saving132112 bytes (8.7%,129KiB).
OTA-slot free space25904 ->158016 bytes. Current normal sdkconfig/build
and deployed firmware retain DEBUG optimization to avoid confounding soak.
Do not claim size build runtime-tested. Assets from ELF: gzip payloads198306
bytes total, startup PNGs60826, icons60470; embedded fonts55168 bytes;
full root certificate bundle68983 bytes. These are occupied sizes, not
promised savings. Compiler optimization is first candidate; certificate
reduction must preserve verification and Google/PageKite trust paths.

USB reader93341 ended Device not configured after09:08:58 UTC. Wifi
reconnected at09:09:31 uptime20 reset_reason1 (power-on, not watchdog).
Soak start for uninterrupted full run is approximately09:09:11 UTC;
continue through09:39:11 or later. Telemetry7042 remains active via Wi-Fi.
Public identity/gzip loading HTML and font matched local source bytes.


## 2026-10-30 full patched firmware deployed (latest; soak running)

User reconnected actual CH9102 monitor. Full flue-monitor/build/flue-monitor.bin
written to active0x20000, chip/MAC confirmed, hash verified. Intentional
POWERON 09:07:47 UTC; app ELF541b1d5cc SDK5.5.6,2MiB PSRAM and automatic
light sleep ON confirmed. Full services restored: LAN/public root HTTP200,
PageKite authenticated, real MCP9601 readings, first Sheets upload success.
Saved settings match /tmp/flue-watchdog800-settings.json except randomized
settings_revision. No longer minimal firmware: OTA/network monitoring available.
USB reader93341, wifi telemetry7042 (measure-long.cjs -> telemetry.jsonl).
Continue >=30min since09:07:47 and check monotonic uptime, no resets, real
Sheets successes, public responses/asset decoding, then record final result.
User may disconnect USB for work; wifi now sufficient if monitor stays powered.
Do not confuse USB removal/power reset with watchdog. No commits/push.


## 2026-10-30 patched trial interrupted by USB removal (latest)

User reconnected monitor; correct CH9102 /dev/cu.usbserial-5C671828951
returned. Patched minimal boot 08:45:01 UTC, ELF c0f9acbd9, SDK5.5.6,
2MiB PSRAM + Wi-Fi + automatic light sleep confirmed. Logs continued
without watchdog reset through 09:00:18 UTC (15m17s). Reader session14433
then exited with Device not configured. At 09:01:28 inventory showed only
CH340 /dev/cu.usbserial-21130 again (previously identified other board
MAC84:0d:8e:d2:a6:ec). NOT proof of a watchdog failure. User asked to
reconnect monitor and leave it attached; async answer pending. Do not flash
other board. Monitor still has minimal patched firmware, no HTTP/OTA.

During soak, production CMake now includes cmake/sleep_livelock_backport.cmake;
activate-idf.sh selects5.5.6; sdkconfig copied from all-services-on candidate
(PSRAM on, all FLUE_DIAG off, PM_SLP_IRAM_OPT/cache assertion off, I2C/RMT
IRAM-safe on). Defaults explicitly retain those driver settings. Old build
archived at /tmp/flue-sleep-ab/monitor-build-before-556-final. Fresh normal
flue-monitor/build succeeds, image0x170b10 (2% slot headroom). Generated
watchdog helper/reconfigure/chip predicate confirmed IRAM. New test
 tools/test_sleep_livelock.py compiles actual generated functions with
ASan/UBSan register stubs; both-core feeding,20ms/800ms stage switching,
1600ms reset stage, locking and changed-SDK rejection pass. README updated
with backport explanation, explicitly hardware validation in progress.
No full patched firmware flashed yet. Full built candidate ready at
flue-monitor/build/flue-monitor.bin. Next after monitor reconnect: deploy
full candidate so network monitoring/OTA are available again, then >=30min
with real sensor/Sheets/PageKite/PSRAM telemetry and public assets. Minimal
15m17s clean is encouraging but not a completed30min proof; report honestly.
Restore /tmp/flue-sleep-ab/off/flue-monitor.bin if candidate fails. Do not
leave minimal firmware when completing task. No source commits/push.


## 2026-10-30 ESP-IDF 5.5.6 and sleep backport — awaiting monitor USB

User requested fixing PSRAM/light sleep, then suggested 5.5.6. Official
5.5.6 installed alongside 5.5.5 at the existing SDK cache frameworks/5.5.6;
required tools installed with idf_tools.py --targets esp32. Existing project
activate-idf.sh still selects 5.5.5: do not claim upgrade finalized.
Plain 5.5.6 minimal Wi-Fi/PSRAM/sensor/light-sleep build passed compilation
but reset TG1 at 08:13:01 UTC after POWERON 08:10:02 (2m59s), then again
08:15:52. Snapshot /tmp/flue-sleep-ab/minimal-5.5.6. Full unpatched monitor
also builds (repo-root build-5.5.6; SDKCONFIG=/tmp/flue-sleep-ab/full-5.5.6.sdkconfig),
not flashed; dependencies.lock now records IDF 5.5.6.

New tools/backport_sleep_livelock.py and cmake/sleep_livelock_backport.cmake
adapt upstream d45606bf + 8220859330 to the exact SHA-guarded 5.5.6 sources.
Installed SDK untouched; generated sources retain basenames/linker rules.
Backport changes only light sleep, suspends ECO3 workaround before CPU stall
and restores after release, serializes tick/helper WDT configuration and
places helper/chip-info code in IRAM. Does NOT disable either watchdog.
Included only by temporary minimal/main/CMakeLists.txt so far; production
main/CMakeLists.txt does NOT yet include it. Build passed after adding stdbool.
NM confirms helper/reconfigure/chip predicate at 0x4008... . Normal sleep
entry remains flash just as unpatched baseline (PM_SLP_IRAM_OPT=n).
Patched snapshot: /tmp/flue-sleep-ab/minimal-5.5.6-patched.

Patched minimal was flashed to confirmed monitor MAC 8c:94:df:0b:be:fc,
active app 0x20000; esptool completed hash verification. Subsequent USB
reader failed: /dev/cu.usbserial-5C671828951 disappeared. Inventory now only
/dev/cu.usbserial-21130 (CH340), read_mac positively identified DIFFERENT
ESP32-D0WD rev1 MAC 84:0d:8e:d2:a6:ec. That board bootloops; no firmware
was written to it. User asked to reconnect actual monitor, async question
pending. Monitor currently has minimal patched firmware, no HTTP/OTA,
so USB is required to validate and restore complete firmware. Do not end
claiming fixed/restored. Earlier full recovery binary remains off/flue-monitor.bin.
No patched run duration has been observed yet. Next: identify monitor USB,
run patched minimal >=30min; then integrate/build/flash full app with PSRAM
and automatic light sleep, all services, test >=30min plus real Sheets and
LAN/public responses. If failure/block, restore full PSRAM-off firmware via
confirmed monitor USB. Remove/disable temporary diagnostics for normal build.


## 2026-10-30 Wi-Fi A/B experiment results

Minimal sensor + Wi-Fi with normal SDK sleep path reset at 00:52:50 UTC,
5m10s after intentional POWERON 00:47:40. User authorized Wi-Fi off/on
comparison (30 minutes each unless reset earlier), repeated, plus online
bug research. Temporary minimal project now has CONFIG_MINIMAL_WIFI;
OFF skips driver/netif initialization entirely, keeps PSRAM/automatic light
sleep/raw sensor unchanged. Snapshots minimal-wifi-off/on under
/tmp/flue-sleep-ab contain binaries, ELFs, sdkconfigs and main sources;
sdkconfig diff is only MINIMAL_WIFI. OFF began intentional POWERON
2026-10-30 01:00:36 UTC and ran through 01:31:10 (30m34s) without
a reset; raw sensor samples continued. Reader 43796 was then closed
intentionally to flash the saved Wi-Fi-ON comparison image.
Wi-Fi ON began POWERON at 01:48:07 UTC and reset repeatedly: TG1 at
01:48:21 (14s), RTCWDT at 01:48:59, TG1 at 01:49:13, RTCWDT at 01:49:21.
Strong signal -49 dBm, PSRAM/light sleep enabled, no HTTP/WS/services.
This strongly implicates the Wi-Fi/PSRAM/light-sleep combination, but does
not prove the exact fault or indefinite stability without Wi-Fi. The
planned 30-minute cap was stopped at failure as agreed; several automatic
reboots reproduced the ON failure. Full off/flue-monitor.bin restoration
completed, intentional POWERON at 01:50:38 UTC (PSRAM off, automatic
light sleep ON, all app services). Serial confirms live MCP9601 readings;
LAN and public HTTPS root both returned 200, PageKite authenticated after
one retry. No fresh Sheets acknowledgment awaited in this recovery check.
The unpatched SDK A/B is complete; upstream candidate remains untested.
No web/temperature service is available during the minimal trial; restore
full application before ending debugging. Active app offset 0x20000.

Online research found upstream d45606bf1d450924fbba25eb692ab7d7e27dee77:
"disable esp32eco3 livelock workaround to sleep process". It adjusts the
20-ms cache workaround around light-sleep CPU stalling; absent from local
5.5.5 source. Related merge 8220859330da141d860defece8aed1f414459bfa
includes prerequisites. Candidate ONLY: not applied, not validated. Follow-up
68bb4a1c446f1c19948c2d15af9626563a828908 fixes deep-sleep lock ordering.
Evidence and URLs saved in /tmp/flue-sleep-ab/research.txt and upstream JSONs.
Do not alter the running A/B variables to apply this candidate mid-test.


## 2026-10-30 controlled PSRAM comparison and feature isolation (in progress)

Owner steered away from merely replaying the full PSRAM build: disable
PageKite, then Sheets, then individual PSRAM users; if that fails, start
minimal and restore features one at a time. Follow that sequence. Temporary
main/Kconfig.projbuild flags disable each service at its start function,
without changing NVS settings; the PageKite guard also covers settings-save
restart calls, and the Sheets event guard avoids using an uncreated queue.
While PageKite is disabled, the public URL is intentionally offline; LAN
remains available. When Sheets is disabled, real uploads are intentionally
paused (do not insert fake samples or events).

PSRAM-off run completed over 13 minutes / 7000 sleep cycles without any
watchdog reset, with PageKite connected and two acknowledged Sheets uploads.
Next, PSRAM-on with only PageKite disabled still reset at stages 114, 14
and 51. Two resets happened before the first Sheets upload in those boots.
PageKite activity is therefore not required to reproduce the failure.
The next flashed build disables both services, keeping PSRAM/light sleep on.
That no-services build also reset (stage 114, 952 entries/951 exits), with
over 180 kB internal allocator low-water and no Sheets attempt. Next, JSON
allocations were forced internal using FLUE_DIAG_JSON_INTERNAL. This also
failed: OTA boot 23:26:47 UTC, RTCWDT reset 23:32:54 UTC (6m07s), stage 50,
3661 entries/3660 exits. Therefore five clean minutes is not sufficient to
claim a fix. Next individual exclusion is FLUE_DIAG_SKIP_PSRAM_STATS;
it omits live external-heap queries rather than reporting fake zero values.
Skipping those queries also failed after about 6m40s, TG1WDT, stage 12
(4000 entries/3999 exits). Current next variant puts the history ring
internal too; startup confirms this and I2C handles still use 0x3f80... .
Owner asked whether web traffic matters. A first timed reset occurred before
any WS client was logged, but HTTP traffic was not fully ruled out. A
FLUE_DIAG_DISABLE_HTTP option is prepared in source to skip HTTP/WS/OTA
startup. It is NOT enabled in the current ring trial. If the ring trial
fails, test that option using USB logs; recovery then requires writing the
confirmed active app partition over USB. Preserve NVS/bootloader/partitions.
Ring-internal also failed (TG1WDT, stage 14, 587 entries/586 exits). The
HTTP/WS/OTA-disabled build was then deployed; app validation completed and
the USB reader was renewed (intentional POWERON at 23:52:07 UTC). It reset
at 23:52:52 UTC (RTCWDT, stage 112, 399 entries/398 exits). No measurement
WebSocket or HTTP server was running. Web traffic is therefore not required
for the failure. Both unused HTTP-side allocation paths (history API copy
and asset decompression) also cannot be required for that reset.
Active app is confirmed at 0x20000. USB recorder session 81684 runs
/tmp/flue-sleep-ab/serial_reader.py for an hour, appending the same serial.log.
LAN telemetry process was stopped for this test. Next build enables only
CONFIG_I2C_ISR_IRAM_SAFE, making the SDK sensor objects internal/cache-safe;
it also changes interrupt cache-safety policy, not only allocation caps.
I2C-internal was written to active 0x20000 over USB, validated by bus/device
handles at 0x3ffc2124/0x3ffc271c and working sensor samples. It still reset
at 00:00:13 UTC after the intentional 23:56:18 start, RTCWDT stage 110,
2476 entries/2475 exits. Next isolated build enables CONFIG_RMT_ISR_IRAM_SAFE
as well, keeping the LED driver's SDK context/encoders internal. LED-strip
pixel storage already uses ordinary calloc (internal in our CAPS_ALLOC mode).
The current USB reader session is 73936; use active slot 0x20000 for recovery.
RMT-internal also failed within 29 seconds (RTCWDT stage 36, 236 entries/
235 exits). Following the owner's "start from zero" direction, a separate
minimal ESP-IDF project now lives at /tmp/flue-sleep-ab/minimal. It contains
only direct SDK Wi-Fi station startup (NVS wifi_cfg/ssid/pass read-only,
WIFI_STORAGE_RAM), the same 240/80 MHz automatic light sleep and a 100-ms
delay loop with 30-second alive logs. No sensor/LED/JSON/history/HTTP/Sheets/
PageKite or our SDK trace copies/wrappers/callbacks. compile_commands.json
confirms original SDK rtc_clk.c and sleep_modes.c. Config copies SDK choices
from the failing build but prunes app-only FLUE_DIAG symbols. Image 0xcad70
was written to active 0x20000; intentional reader-start POWERON at
2026-10-30 00:14:15 UTC. Sensor readings are intentionally unavailable during
this minimal trial. USB reader is now session 16979; file remains serial.log.
Restore a full app over USB before finishing; backups under off/ include
all services with PSRAM disabled (previous 13+ minute successful control).
The untouched-SDK minimal build itself reset at 00:16:15 UTC, two minutes
after the intentional 00:14:15 start, RTCWDT. Thus our app modules and custom
SDK trace copies are not required for reproduction. The minimal config
still inherited ESP_SLEEP_CACHE_SAFE_ASSERTION=y, so the next one-variable
test disables just that standard SDK debug option. A cached original minimal
image/ELF/sdkconfig is under minimal-cachecheck/. USB reader is session 16979.
Cache-check disabled minimal also reset: intentional start 00:22:00 UTC,
RTCWDT 00:27:25 UTC (5m25s). Thus neither our SDK copies nor that debug
check are necessary. Next minimal build disables only PM_SLP_IRAM_OPT to
return to the normal SDK sleep path. No sensor feature is enabled. A guarded
MINIMAL_SENSOR raw-I2C task is prepared in the temporary project for later
stepwise additions, but do not deploy it until the base passes. Its baseline
main.c is saved under minimal-no-cachecheck/. Reader is now session 92654.
Monitor project's SDK trace is now explicit opt-in FLUE_DIAG_TRACE_SDK,
default n; normal builds use untouched SDK source and omit sleep callbacks.
Minimal normal sleep (PM_SLP_IRAM_OPT=n, cache assertion=n, sensor=n) started
00:35:05 UTC and passed over 10 minutes (alive uptime 619 at 00:45:24), no
reset. This is a short control, not long-term proof. First feature restored
is MINIMAL_SENSOR: only direct SDK MCP9601 I2C prepare/read and one 4-KiB
stack task at priority 1, raw samples every 10 seconds. No JSON/history/LED/
web/upload code. Same original SDK, same PSRAM/PM configuration, existing
I2C IRAM-safe setting preserved. Source is in temporary minimal/main/main.c;
image/ELF/config are under minimal-sensor/. Active slot remains 0x20000.

Owner approved investigating clock restore and comparing PSRAM on/off with
automatic light sleep kept on. Both builds now use the same additional
guarded local rtc_clk.c trace (tools/trace_rtc_clock_sdk.py), preserving its
basename/linker placement. Stages 100–117 surround clock-restore calls;
120–129 cover switching back to PLL. They only update DRAM breadcrumbs
while the sleep clock-restore call is active. Installed SDK is untouched.

PSRAM-on image 0x170a10, ELF hash prefix f70d4b662, reset twice in the
timed trial: RTCWDT at stage 114 (PLL configuration, 44 entries/43 exits)
and RTCWDT at stage 51 (RTC-time read returned, 545 entries/544 exits).
Thus the fault is not demonstrated to be confined to clock restore.
Saved on/off images, ELFs and sdkconfig snapshots are in /tmp/flue-sleep-ab;
serial.log has UTC timestamps and telemetry.jsonl records actual PSRAM totals.
Off image 0x161670 was deployed next. Only CONFIG_SPIRAM was explicitly
changed; Kconfig also removed its dependent options (including old silicon
cache libraries/ECO3 PSRAM cache-lock workaround and FATFS EXTRAM preference).
Light sleep, 800-ms IWDT, 100-Hz tick, IRAM sleep/cache checks and Wi-Fi RX
optimization setting remain equal. Do not interpret an intentional OTA
SW_CPU_RESET as a watchdog failure. The off soak is still in progress.

## 2026-10-29 ongoing automatic-light-sleep diagnosis

Follow-up: existing sdkconfig retained CONFIG_ESP_INT_WDT_TIMEOUT_MS=300
after enabling PSRAM. This SDK's esp_system/Kconfig defaults to 300 without
SPIRAM and 800 with it; defaults do not overwrite existing sdkconfig values.
Both sdkconfig.defaults and the active sdkconfig now explicitly use 800 ms.
FreeRTOS ticks remain 100 Hz and external task stacks remain disabled;
FreeRTOS heap_idf.c allocates stacks/TCBs from internal 8-bit RAM. No radio
shutdown was added: automatic light sleep coordinates with Wi-Fi modem sleep.
The SDK sleep code temporarily enables a 1-second RTC watchdog as a wakeup
safety net, so do not assume the RTC watchdog is disabled throughout sleep.
The detailed 300-ms trial reset after roughly 6 minutes / 3342 entries,
TG1WDT_SYS_RESET, breadcrumb 45 (MSPI clock synchronization returned, sleep
transition not fully completed). Image 0x170ad0 with 800 ms was built and
deployed next. This configuration correction is not yet proof of root cause.
The 800-ms image also reset after about 4 minutes: RTCWDT_RTC_RESET,
breadcrumb 50, 2095 sleep entries / 2094 exits (inside/around rtc_time_get
after waking). Thus 800 ms alone does not fix the problem. Also, this SDK
already keeps RTC_PERIPH on via ESP_SLEEP_RTC_BUS_ISO_WORKAROUND, so our
explicit esp_sleep_pd_config call is redundant, not a newly discovered fix.

Important diagnostic correction: enabling ESP_SLEEP_CACHE_SAFE_ASSERTION
immediately exposed a fault introduced by the temporary renamed source:
ESP-IDF's esp_pm/linker.lf selects `sleep_modes:esp_light_sleep_start`
by object basename. `sleep_modes_traced.c` lost that placement, leaving the
entry function in flash (PC 0x400d5f8e). The generated copy now preserves
`sleep_trace/sleep_modes.c`. Therefore detailed-trace reset locations above
must not be treated as the established original fault. Watchdog resets
before the SDK copy was introduced remain independent evidence. The fixed
cache-check build overflowed IRAM by 672 bytes; temporarily disable the
optional ESP_WIFI_RX_IRAM_OPT in active sdkconfig to fit the diagnostic
check/panic handler. This is another diagnostic change, not a release fix.
Corrected diagnostic image 0x1708f0 was written over USB to confirmed active
slot 0x1a0000, preserving NVS/bootloader. Link symbols now confirm
esp_light_sleep_start=0x4008ee14 and timer-wakeup entry=0x4008f1d4 (IRAM).
That corrected RTC-memory trace build also reset (TG1WDT_SYS_RESET) after
1584 entries, breadcrumb 14 (RTC calibration call). No cache-access panic
was reported. Next image 0x170910 moves breadcrumbs to internal DRAM
__NOINIT_ATTR, magic 0x534c5032, avoiding RTC-bus writes in the critical
path and logging CPU core. It was deployed OTA; initial trace uses core 0.
Warm-reset breadcrumbs are useful only if their magic survives; a power-on
reset deliberately ignores them. Root cause remains unproven.

This supersedes the disabled-sleep mitigation below: the owner explicitly
requested automatic light sleep be restored and the fault debugged. It is
enabled in main.c. Keeping RTC_PERIPH powered for RTC-126 did not prevent
resets; neither did CONFIG_PM_SLP_IRAM_OPT=y (currently enabled in ignored
sdkconfig). Do not claim either experiment fixed the problem or established
its cause. Before PSRAM there were also unexplained restarts in older notes,
but there is no evidence those had the same cause.

RTC no-init breadcrumbs show interrupted sleep transitions, with both TG1
and RTC watchdog reset reasons. Temporary sleep_diagnostics.c callbacks and
an rtc_sleep_start linker wrapper record progress without logging/locks in
the sleep path. tools/trace_sleep_sdk.py now generates a guarded local copy
of ESP-IDF sleep_modes.c, compiled by main/CMakeLists.txt instead of the SDK
original. Installed SDK files are untouched. Even stages in that script
mark entry to a call; the next odd stage marks its return. The detailed
trace image is 0x170a70, deployed OTA to confirmed monitor .137. Serial
evidence is appended to /tmp/flue-light-sleep-debug.log. These are temporary
diagnostics to remove after identifying the fault, not a release solution.

## 2026-10-29 PSRAM buffers and RTC-watchdog mitigation

USB follow-up identified the actual monitor as CH9102 port
`/dev/cu.usbserial-5C671828951`, MAC 8c:94:df:0b:be:fc, ESP32-PICO-V3-02
revision 3.1. PSRAM boot initialization and the SPI SRAM memory test pass.
The former CH340 port was the display; never use its logs as monitor evidence.

Two separate problems appeared during diagnosis. Fast WiFi scanning chose an
AP at -79 dBm and logged beacon timeouts; shared boot/test-connect settings
now scan all channels and select by signal. A subsequent boot chose a
different AP at -52 dBm. Both builds pass; only the monitor was updated.
A weak-link OTA returned 408; after confirming the monitor's active app at
0x1a0000 in its boot log, esptool wrote only that app partition over USB,
preserving NVS, partition table and bootloader (image 0x16ff40).

Even with the strong AP, serial then captured `RTCWDT_RTC_RESET` after about
110 seconds, without an exception backtrace. Thus WiFi alone cannot explain
all failures. `configure_power_management()` now disables automatic light
sleep on the monitor while keeping DFS and WiFi modem power saving. The
exact sleep/wakeup failure mechanism is not yet established. Memory telemetry
also reports esp_reset_reason(). Current image 0x170150 was deployed by OTA;
serial confirms Light sleep: DISABLED. Do not re-enable automatic light sleep
without diagnosing the failure on this Feather V2. Evidence spans multiple
boots in /tmp/flue-psram-wifi-fixed-serial.log; no-sleep uptime/memory is in
/tmp/flue-psram-no-lightsleep.jsonl. Saved settings still match except revision.

No-sleep follow-up: continuous telemetry reached uptime 393 s with no drops
or further reset; PageKite remained connected and Sheets acknowledged one
real periodic sample. Internal free RAM was about 113–115 kB, allocator
low-water 64828 bytes, sampled largest-block minimum 63488 bytes; PSRAM
total 2097152/free 2086724 bytes (low-water 2043916 after asset decoding).
Repeated LAN/public requests returned 200 and identity loading bytes matched
source. Final saved-settings comparison changed only revision. This is a
short recovery test, not proof of long-term stability or the precise watchdog
root cause. Current app leaves 28336 bytes in its OTA slot. The monitor is
running the PSRAM + all-channel-scan + automatic-light-sleep-disabled build.

The Feather V2's 2 MiB PSRAM is now initialized/tested at boot at 40 MHz.
Use `SPIRAM_USE_CAPS_ALLOC`, not automatic malloc integration: task stacks,
DMA/network/TLS allocations stay internal. `SPIRAM_IGNORE_NOTFOUND` allows
boot without PSRAM. Defaults AND the existing ignored sdkconfig were updated;
defaults alone cannot override the previous disabled SPIRAM setting.
Qualification: ordinary malloc/task-stack allocation stays internal, but
SDK code that explicitly requests MALLOC_CAP_DEFAULT can still allocate
from the external heap in CAPS_ALLOC mode. Boot logs show I2C bus/device
handles at 0x3f80...; those SDK allocations must also be considered during
isolation. Do not claim that only our four selected buffers use PSRAM.

The shared `buffer_memory.h` uses the IDF preferred-capabilities allocator:
PSRAM/8-bit first, internal/8-bit fallback. Only ordinary task-context data
belongs here. The history ring is allocated once (5760 bytes), and the
history API copy is allocated/freed per request instead of reserving another
5760-byte static array. History allocation failure leaves live sampling
working; API copy failure returns 503. cJSON hooks are installed once at the
very start of app_main, before application tasks or JSON allocations, so
JSON trees and serialized responses use the same PSRAM preference. Never
switch global cJSON hooks per request. Both buffers for identity asset
inflation (32 KiB dictionary plus ROM inflater state) also prefer PSRAM.
Asset payloads remain in flash. The shared helper still works on the display
without PSRAM enabled; its build passes, but the display was not flashed.

Memory telemetry adds psram_total/free/min_free. Corrected monitor image
0x16ff30 deployed over OTA to confirmed .137; it leaves 28880 bytes (1.9%)
in the existing slot. PSRAM support/cache workarounds grew the image by
63520 bytes; revisit the partition/asset arrangement before adding large
dependencies. No partition or bootloader update was needed for this trial.

Hardware recognized 2097152 PSRAM bytes. All exposed saved settings matched
the pre-PSRAM snapshot except boot-randomized revision. With PageKite connected
and one successful Sheets log, internal free RAM held around 114–115 kB.
Allocator low-water was 63844 bytes; sampled minimum largest block 63488,
compared with 40344/38912 before PSRAM under the earlier short-run test.
The same three concurrent public GETs all returned 200; loading-page identity
and gzip bytes plus font bytes matched source. The identity request lowered
PSRAM low-water to 2043916 bytes without lowering the internal minima.
History still returns 401 without login. These are short-run observations,
not a soak or an XMPP capacity test. Evidence: /tmp/flue-psram-measure.jsonl.

Host verification: `tools/test_history_memory.py` runs the actual history
handler with 360 points/64 events and the JSON hooks under ASan/UBSan, including
cleanup after send failure, exhausted-copy-buffer 503, and authentication.
`tools/test_compressed_assets.py /tmp/flue-miniz-v114.c` checks actual inflater
output, preferred allocation/fallback, exhausted allocations, disconnect and
malformed headers. The miniz reference is upstream richgel999/miniz v114.
Settings migration tests and both firmware builds pass.

Historical first-trial outage (subsequently investigated above): after the
5-minute telemetry capture ended (last sample
uptime 290 s, stable memory, PageKite connected, one successful Sheets log),
final LAN checks timed out/refused and the public URL returned relay 503.
The display remained reachable. The Mac has both en7 and en0 on this subnet;
explicit curl via en0 also failed, so choosing that interface did not recover
the monitor. This does not establish a crash, reset, or PSRAM root cause.
At that point USB was attached to the display, so monitor boot logs were
unavailable until the owner connected the monitor. The first trial must not
be described as stable. Known-good pre-PSRAM app image remains preserved at
`/tmp/flue-before-psram.bin` (1443600 bytes). The earlier saved NVS settings
were confirmed intact before the outage.

## 2026-10-29 memory measurement and reverted-settings compatibility

`memory_diagnostics.c` samples internal 8-bit RAM every 100 ms from the
existing main task, plus Sheets HTTP callbacks. Reading JSON (REST and the
existing LAN device WS) includes `memory`: current free bytes/largest block,
allocator low-water bytes, sampled largest-block minima, Sheets sampled
minimum free/largest bytes, request outcome counters, uptime and PageKite
connection state. No new endpoint, task, credential or auth bypass. Sampling
can miss sub-100-ms peaks; allocator low-water bytes sum per-heap minima.
One measurement WS connection consumes a normal HTTP server socket.

The checkout had reverted panel calibration while the monitor still ran
that firmware and retained its longer NVS blob. An initial diagnostic OTA
therefore fell back to defaults (no Sheets or PageKite); its numbers are
not representative. Settings initialization never overwrote the saved blob.
The loader now accepts the two known reverted tails (16/20 bytes beyond
the current prefix), validates/retains the current prefix and does not
rewrite NVS. Unknown tail sizes remain rejected. ASan/UBSan settings tests
verify exact prefix/credential retention and unchanged stored bytes.
After the corrected OTA, every exposed saved setting matched the pre-update
snapshot except boot-randomized revision and removed panel-calibration keys;
PageKite enabled/secret-set were restored and Sheets logged successfully.

Corrected image 0x160710 fits the existing OTA slot with 92400 bytes free.
Early live readings with PageKite connected showed roughly 98–102 kB free
and a 51200-byte largest block. One successful Sheets request sampled a
53104-byte minimum free and 47104-byte minimum largest block. Three concurrent
public GETs (login, loading screen, font; all HTTP 200) reduced the allocator
low-water to 40344 bytes and sampled largest-block minimum to 38912 bytes.
These are short-run observations, not an XMPP capacity test or authenticated
dashboard stress/long-term soak. Measurements were captured in
`/tmp/flue-memory-measure.jsonl`; that temporary file includes the excluded
initial boot without services, so filter for the corrected boot.

See the repo root `CLAUDE.md` for the bigger-picture project this is one half
of, and `README.md` (this folder) for day-to-day build/flash/OTA commands and
the REST API. This file covers implementation-specific gotchas, most of them
hard-won on real hardware.

## Why this rewrite exists

This folder was originally `flue-monitor-idf/`, a ground-up rewrite of an
earlier ESPHome version of this same sidecar (then itself named
`flue-monitor/`) that ran alongside it as the rollback path throughout the
rewrite. The rewrite happened because the rate-of-change regression and zone
classification became real algorithmic C++ living inside a YAML multiline
lambda string — no separate compile step, awkward to iterate. Plain ESP-IDF,
matching `../flue-display/`'s own architecture, fixes that. API-first, OTA,
captive portal, mDNS were all part of the same ask; no MQTT broker exists on
this network, so WebSocket is the mechanism for pushing live readings to
`flue-display` instead. Once the rewrite caught up (see Status below) and a
BMP581 sensor originally alongside the MCP9601 was physically removed (see
"BMP581 removed" below), the ESPHome version was retired and removed
entirely, and this folder renamed from `flue-monitor-idf/` to take its place.

## Status

**Adopted as the production sidecar** (this folder's rename from
`flue-monitor-idf/` to `flue-monitor/`, and the ESPHome version's removal, was
that cutover). **Milestones 1-5 done and verified on the real Feather
board:**
- **Milestone 1**: WiFi (stored creds) + captive portal fallback (scanned
  network list, live test-connect-before-save, a dedicated failure screen) +
  mDNS + OTA.
- **Milestone 2**: BMP581 + MCP9601 both reading correctly, verified
  side-by-side against the ESPHome sidecar's own values on the same physical
  sensors. (The BMP581 was later physically removed from the board -- its
  ambient temperature reading was almost a duplicate of the MCP9601's own
  cold-junction reading -- and all BMP581 code has since been removed; see
  "BMP581 removed" below.)
- **Milestone 3**: NVS-backed settings (replacing ESPHome's YAML
  `substitutions:`), the rate/zone regression ported from the ESPHome
  lambda, and a REST API (`GET /api/reading`, `GET`/`POST /api/settings`).
- **Milestone 4**: a `/ws` broadcast endpoint (reading every ~30s,
  `settings_changed` on a successful settings POST), consumed by
  `../flue-display/`'s own Milestone 4 (WS subscription replacing its old 3s
  REST poll) -- verified end to end on both real devices.
- **Milestone 5**: periodic (deadband/heartbeat-gated) + event-triggered
  Google Sheets logging (`sheets_logger.c/.h`), ported from the ESPHome
  sidecar's own logic onto a dedicated FreeRTOS task so a slow Apps Script
  response never blocks sensor sampling or the REST/WS servers -- verified
  against the real production webhook (a real row logged, status 200) after
  fixing a missing TLS cert bundle attachment (see below).
- **Milestone 7**: `POST /api/event` + `GET /api/events` (`rest_api.c`'s
  `EVENTS[]`), the fixed woodstove-event taxonomy ported verbatim from the
  ESPHome sidecar's own template buttons (same slugs, e.g. `cold_start`,
  `added_wood` -- see "The woodstove-event taxonomy is a closed set" below)
  -- verified against the real production webhook (a real row logged,
  status 200, event=`added_wood`). No physical buttons or web UI to trigger
  these yet -- just the REST endpoint, per the plan's "at minimum" scope.
- **Milestone 6**: the embedded web UI (`main/web_ui/`) -- dashboard (glow
  circle, pulse math ported from `flue-display/main/led_display.c`), 24h
  graph (`GET /api/history`, a new downsampled ring buffer in `sensors.c`),
  settings, and the event-log bottom sheet, all one Alpine.js page with no
  build step, served from `/`. Visually verified live in a real browser
  (Chrome, via the Claude Code Chrome extension) -- dashboard glow,
  settings steppers/save-bar/undo, the 24h graph, and the event sheet
  (a real row logged: `added_wood`) all confirmed working end to end. Three
  real bugs only showed up once actually rendered (static checks alone
  missed all of them) -- see "Three real bugs only a real browser caught"
  below.

## STEMMA QT power (GPIO2) — the single biggest time sink so far

**GPIO2 gates power to the entire STEMMA QT connector (both sensors) and
must be driven HIGH before touching the I2C bus at all.** Without it, the
bus reads stuck low on every single line/every bias condition (floating,
internal pull-down, *and* internal pull-up all read 0) — indistinguishable
from a genuinely wedged/shorted bus by any software-level test. `sensors.c`'s
`sensors_init()` does this first, before anything else. The original
ESPHome sidecar did the same thing via a `switch: platform: gpio` with
`restore_mode: ALWAYS_ON` and `setup_priority: 1200` (higher than i2c's own
1000) -- without that ordering, the sensors were unpowered when the i2c bus
initialized, showing up as `SCL is held LOW on the bus` bus-recovery
failures at boot, the same failure mode this port's own explicit
before-anything-else ordering avoids.

## I2C bus recovery is needed on every boot, not just after a crash

`sensors.c`'s `i2c_bus_recover()` is a faithful port of ESPHome's own
`i2c_bus_esp_idf.cpp`'s `recover_()` (same NXP/Analog Devices bus-recovery
procedure: bit-bang 9 clock pulses, each waiting out clock-stretching, then a
START immediately followed by a STOP) — ESPHome's own boot log shows
"Performing bus recovery" on every single boot of this same hardware too,
not just after a bad state. An earlier, simpler version of this function
that didn't wait for clock-stretch release on each pulse (just toggled SCL
on a fixed delay) failed to unstick a genuinely stuck bus; matching the
proven ESPHome implementation exactly, rather than reinventing it, is what
actually worked.

## MCP960x errata: 85kHz nominal wasn't safe in practice

The MCP960x family has a real, documented Microchip silicon errata
("Intermittent I2C Read Command Clock Stretching Failure") that above
~85kHz can make a read silently return stale duplicate register data --
it manifests as **stale/frozen register reads**, not a bus error, so a read
looks completely valid, just wrong (or just never updating). Background:
rikeshkkpatel.co.uk/diy-reflow-oven/problems-with-the-mcp9600-thermocouple-amplifier.
Two more things learned the hard way, on top of that:

- **Requesting exactly 85000 Hz still hit the errata.** The ESP32's clock
  divider rounds the *requested* rate to the nearest achievable one, which
  can land slightly above it. `config.h`'s `I2C_FREQ_HZ` is `50000`, leaving
  real margin instead of sitting right on the threshold.
- **ESPHome's own `i2c:` component defaults `sda_pullup_enabled`/
  `scl_pullup_enabled` to `true` on ESP32** (`cv.SplitDefault(...,
  esp32=True)` in its own schema), and the sidecar's config never overrides
  that — so its bus has the ESP32's internal weak pull-up engaged *in
  parallel with* the breakout boards' own pull-ups. This rewrite wasn't
  doing that at first. The extra pull-up speeds up the bus's rise time,
  which matters here: slower edges distort SCL's effective duty cycle
  enough to trip the errata even at a "safe" nominal frequency.
  `init_mcp9601()` explicitly sets `sda_pullup_en`/`scl_pullup_en = true` on
  its `i2c_dev_t` before the first real transaction, matching ESPHome's
  default rather than relying on the driver's own default of `false` (the
  now-removed BMP581 init did the same, for the same reason, while it was
  still on the board).
- **The MCP9601's device-config register (mode/ADC-resolution/burst count)
  is never touched by esp-idf-lib's `mcp960x` driver** — it's left at
  whatever the power-on-reset default is. ESPHome's own `mcp9600.cpp`
  explicitly writes this register to `0x00` (Normal mode, 18-bit ADC, 1
  burst sample) rather than trusting the default; `sensors.c` now does the
  same via `mcp960x_set_device_config()`, since earlier debugging on this
  exact chip (while the bus was still stuck low, before the GPIO2 fix)
  involved I2C writes that could have left this register in an unknown
  state.
- **The 18-bit ADC's first conversion takes ~320ms.** Without an explicit
  wait, the very first `sensors_read()` call (which can happen only tens of
  ms after `sensors_init()` returns) reads back the register's
  pre-conversion `0x0000` default — which passes the plausibility clamp
  fine (`0.00°C` is well inside `-40..600`) and was getting admitted into
  the rate-regression window as a real sample, producing a wildly wrong
  initial rate once a genuine second sample arrived 30s later.
  `init_mcp9601()` now waits 400ms after writing the device-config register,
  before returning, specifically to avoid this.

## The "GPIO is not usable, maybe conflict with others" warning is benign

Every boot logs `W (xxx) i2c.common: GPIO 22/20 is not usable, maybe
conflict with others` right after the I2C bus/device come up. Traced this
down to `esp_gpio_reserve()`'s bookkeeping: `esp-idf-lib/i2cdev`'s new
i2c_master-driver backend re-asserts its own bus's SDA/SCL pin reservation
every time a *new device* is added to an already-installed bus (not just
once at bus creation) — so the second sensor's device-add trips the "already
reserved" warning against the *bus's own* prior reservation of the same
pins, not a real external conflict. Confirmed empirically: dumping the
reservation mask (`esp_gpio_reserve(0)`) immediately before bus setup showed
bits 20/22 genuinely unset. Don't chase this warning as a real bug.

## Live WiFi test-connect-before-save (captive portal)

`wifi_setup.c`/`captive_portal.c`/`dns_server.c` now live in `../components/`,
shared with `../flue-display/` (see the repo root `CLAUDE.md`'s "Shared
components" section) -- this section's description of the test-connect
design is unchanged, just no longer specific to this folder alone.

`wifi_setup.c`'s `wifi_sta_test_connect()` attempts the real STA connection
*while the setup AP stays up* (both possible simultaneously in
`WIFI_MODE_APSTA`, already needed for the network-scan feature), and
`captive_portal.c`'s `/save` handler only persists credentials + reboots on
a *successful* test. A wrong password now shows an inline error on the same
screen instead of triggering a blind reboot that may or may not come back —
this was a deliberate design change mid-project (the original Milestone 1
design saved-then-rebooted-then-recorded-failure-for-next-boot, working but
worse UX for the common case of a typo).

## (Historical) Reflashing the old ESPHome sidecar changed the NVS layout

No longer a live concern -- the ESPHome sidecar has been retired and its
firmware/project files removed entirely, so there's nothing left to
reflash back and forth against. Kept for the underlying NVS-namespace fact,
in case it's ever relevant again: ESPHome's own partition table placed
`nvs` differently than this project's `partitions_ota.csv`, and even where
they'd coincidentally overlap, ESPHome's own WiFi-credential storage
format/keys differed from this project's own `wifi_cfg` namespace --
flashing ESPHome and then flashing back meant this project's stored WiFi
credentials were gone, requiring the captive portal setup flow to be redone.

## Only one HTTP server can bind port 80

`rest_api.c`'s `rest_api_start()` owns the single shared `httpd_handle_t` for
normal running state (once connected to WiFi); `ota_server_register()` and
`ws_server_register()` just add their own URI handlers onto that same server
instead of each starting their own. The captive portal's own server
(setup-time only, never running at the same time as the connected-state
server) is separate and unaffected.

## The REST API server is single-threaded, with an unresolved intermittent full hang

`rest_api_start()` explicitly sets `max_open_sockets = REST_API_MAX_OPEN_SOCKETS`
(7, matching `HTTPD_DEFAULT_CONFIG()`'s own default, but named so
`rest_api_log_socket_usage()` below can size its buffer correctly rather
than guessing), so up to 7 clients can have a socket open at once (plus
`ws_server.c`'s own separate `WS_MAX_CLIENTS = 8` cap on broadcast
fan-out). But `esp_http_server` here runs as a single FreeRTOS task --
`HTTPD_DEFAULT_CONFIG()` only has one `task_priority`/`stack_size`/
`core_id`, no thread pool -- so it services one HTTP request at a time,
serially, even with several sockets open simultaneously. `POST /ota`
writing firmware to flash in a loop on that same task is the one handler
long enough for this to matter in the ordinary case: during an OTA push,
the dashboard/REST API/WS are unresponsive to everyone else until it
finishes (Google Sheets logging is deliberately exempt -- `sheets_logger.c`
runs on its own task for exactly this reason).

Beyond that ordinary case, this server has hung completely at least twice,
under real usage, for reasons not yet fully root-caused:

- **First time**: `GET /api/reading` took 15-20s (past `curl`'s own
  timeout, `HTTP 000`), but a raw TCP connect succeeded and ping was
  normal. Looked exactly like a wedged httpd task. Wasn't (this time) --
  the boot log (captured by attaching serial *during* a fresh reset, not
  after) showed the device had roamed to a different AP within the same
  SSID at `rssi: -88`, a genuinely weak signal. A request that DID
  eventually respond, just after 5+ seconds, from a real client (not a
  synthetic one that gives up early) is what proved it was a slow/lossy
  link rather than a stuck task -- a truly deadlocked task would never
  respond no matter how long you wait. `GET /api/wifi` (queries
  `esp_wifi_sta_get_ap_info()` fresh on every call, not cached, unlike
  RSSI, which the WiFi driver only ever logs once at association) exists
  specifically so this can be checked on demand, without forcing a reboot
  to catch that one-shot boot-time log line.
- **Second time, shortly after (same boot)**: every request hung
  completely -- including using the bare IP (ruling out mDNS, see below)
  and a fresh `nc -zv` TCP-only probe (which eventually succeeded, after
  10+ seconds, meaning the TCP handshake itself was also slow). Crucially,
  **the device's own serial log showed nothing at all** for any of these
  attempts -- not even a warning, whereas a normal 404 (e.g. a browser's
  `/favicon.ico` request) does get logged. Multiple consecutive attempts
  over several minutes all failed identically, with the pattern getting
  *worse* over time rather than being randomly intermittent like the RSSI
  case -- consistent with some kind of accumulating resource exhaustion,
  not (just) signal quality. `POST /ota` was also affected at this point
  (`curl: (56) Recv failure: Connection reset by peer`), forcing a USB
  reflash instead to get diagnostics onto the device. Also confirmed mDNS
  was not the cause despite the symptom's obvious resemblance to this
  project's own documented mDNS flakiness (`../flue-display/CLAUDE.md`):
  `dns-sd -G v4 flue-monitor.local` resolved essentially instantly, and the
  hang persisted identically when hitting the bare IP directly (no
  hostname resolution involved at all).

`rest_api_log_socket_usage()` (called every ~30s from `main.c`'s own
`sensor_log_task`, piggybacking its cadence -- no dedicated timer) logs
the current open-socket count via `httpd_get_client_list()`, specifically
to catch this in the act next time: a count climbing toward 7 and staying
pinned there would confirm socket/resource exhaustion; a low, stable count
during a hang would point at something else (a genuinely wedged task, not
a resource leak). Deliberately synthetic load right after adding this
(sequential and concurrent `curl` bursts) did **not** reproduce either
hang, and the socket count stayed low (2-3) throughout -- whatever
triggers the second failure mode needed something closer to the original
real-world condition, not short scripted request bursts.

**Root cause found and fixed the next time it recurred.** The diagnostic
caught it directly: `Open sockets: 7/7`, pinned across multiple 30s ticks,
while `ws_server.c`'s own client count showed only 1-2 -- meaning most of
those 7 httpd sessions weren't legitimate, currently-tracked WS clients at
all. The bug: `ws_server.c`'s `clients_remove()` (called when a broadcast
send to a client fails, or a clean WS close frame arrives) only removed
the fd from *its own* bookkeeping array -- it never told httpd to actually
close the underlying session. A WS client going away uncleanly (a WiFi
drop with no close frame -- the normal case on this network, not the
exception) permanently leaked one httpd socket slot, every single time.
Fixed by also calling `httpd_sess_trigger_close(s_server, fd)` (the
documented API for closing a session from a context other than the httpd
worker task itself) in `clients_remove()`.

Verified live: before the fix, a pinned 7/7 never recovered on its own,
not even after many minutes with zero new client activity. After the fix,
a post-reboot burst of reconnect activity (`flue-display` re-establishing
its WS connection after `flue-monitor`'s own restart) still spiked the
count to 7/7 briefly, but it now **recovers** -- settling back down and
holding steady (observed at 4/7, stable for 2+ minutes) instead of staying
pinned. That settled count is still higher than the "just 1 legitimate
WS client" baseline would suggest, which points at some remaining
churn/slow-to-detect staleness (each stale fd is only pruned reactively,
on the *next* failed broadcast attempt against it specifically, up to a
30s wait) -- worth continued attention via this same logging, but the
severe failure mode (permanent, total lockup with zero recovery) is
confirmed fixed.

## `EMBED_FILES` collides on basename, not full path

`main/web_ui/`'s first attempt named its copies of the shared design-system
assets `styles.css` and `alpine.min.js` -- the same basenames
`../components/captive_portal/` already uses for its own, *different*, copies
of those files. Build failed with `ninja: error: ... multiple rules
generate styles.css.S`. ESP-IDF's `EMBED_FILES` generates an intermediate
`<basename>.S`/`.o` pair per embedded file, and that intermediate filename
is derived from the basename only, dropping the directory -- so two
different components each embedding their own `styles.css` collide in the
same build tree even though the source files live in entirely different
directories and neither component references the other's copy. Fixed by
renaming `main/web_ui/`'s copies to `dashboard.css`/`alpinejs.min.js`
(also updates the extern symbol names, e.g. `_binary_dashboard_css_start`
-- the symbol name is derived from this same intermediate basename).
Anything else embedding files across multiple components needs basenames
unique across the *whole* build, not just within its own directory.

**Confirmed by direct experiment: this collision happens even when both
components' `EMBED_FILES` point at the exact same file on disk** (tried
pointing `main/`'s own `EMBED_FILES` at `../../components/captive_portal/
styles.css` directly, to physically de-duplicate `dashboard.css` from it --
same `ninja: error: ... multiple rules generate styles.css.S`). Each
component's own `idf_component_register(EMBED_FILES ...)` call independently
generates a build rule for `<basename>.S` in the shared build tree,
regardless of whether the underlying source content is identical -- so
sharing one physical file across two components' embeds isn't possible
without a bigger restructure (e.g. one component embedding it and exporting
an accessor the other calls), not just picking the same path. `dashboard.css`
and `components/captive_portal/styles.css` are instead kept
*byte-identical in content* (the Google Fonts `@import` that used to be
dashboard.css-only was moved out into a `<link>` in `dashboard.html`'s own
`<head>`, since only the connected-mode page has real internet to load it)
but stay two separate embedded files under different names, kept in sync by
hand -- there's no way to make ESP-IDF treat them as one without an
`EMBED_FILES`-level rename/alias facility it doesn't have.

## Three real bugs only a real browser caught

`main/web_ui/` built cleanly, and every backing REST endpoint tested fine
via `curl`, but the page itself rendered completely blank when actually
opened in Chrome (visual verification was flagged as pending in an earlier
commit -- this is what turned up once it happened). None of these three
would have been caught by static checks (`node --check`, balanced-tag
counting) -- only a live browser, console errors, and screenshots surfaced
them:

- **`dashboard.js` must load (and define `app()` on `window`) *before*
  `alpinejs.min.js` runs**, not after, even though both are
  `<script defer>` and `defer` preserves *document* order. Alpine
  auto-starts synchronously at the end of its own script -- scanning the
  DOM and evaluating `x-data="app()"` immediately -- which happens before a
  *later* deferred script gets a chance to execute. With
  `<script src="/alpinejs.min.js" defer>` listed first, Alpine scanned the
  DOM and threw `ReferenceError: app is not defined` on every directive,
  leaving the whole page unrendered. Fixed by swapping the two `<script>`
  tags' order. `../components/captive_portal/root.html` never hit this because
  its own data function is inline (no `src`, no `defer`), which executes
  synchronously at its position in the parse -- before any deferred script
  runs at all.
- **A CSS `transition` on an element whose inline style is rewritten every
  animation frame fights the animation instead of smoothing it.**
  `.glow-outer`/`.glow-inner` had `transition: box-shadow .3s ease` /
  `transition: background-color .15s linear, color .15s linear` -- looked
  like reasonable general-purpose polish, copied without thinking through
  the interaction. `dashboard.js`'s `runGlowFrame()` already writes a new
  inline `background-color`/`box-shadow` value ~30 times a second via
  `requestAnimationFrame`; each write restarted a new CSS transition before
  the previous one finished, so the rendered color perpetually chased a
  moving target and never reached it -- rendered as a barely-visible,
  washed-out near-transparent blend instead of the real zone color. The
  glow circle was there, just practically invisible. Fixed by removing
  both `transition` declarations -- the JS's own envelope-curve
  interpolation already provides all the smoothness needed.
- **`:viewBox="..."` (Alpine's dynamic attribute binding) silently produces
  a lowercase `viewbox` attribute, which SVG does not recognize** (SVG
  attribute names are case-sensitive). A directive attribute like
  `:viewBox` isn't on the browser's fixed allowlist of camelCase SVG
  attributes preserved during HTML parsing -- only a bare, statically-
  written `viewBox="..."` is -- so the HTML parser lowercases the
  *directive's own attribute name* to `:viewbox` before Alpine ever reads
  it, and Alpine's `setAttribute` call inherits that already-lowercased
  name. Confirmed via `element.getAttribute('viewbox')` (lowercase)
  returning the value while `getAttribute('viewBox')` returned `null`. The
  graph's `<svg>` rendered at a tiny fixed intrinsic size instead of
  stretching to its container, with the drawn content confined to a small
  corner. Fixed by hardcoding `viewBox="0 0 342 230"` as a static literal
  instead of binding it (`graphHeight` was always a fixed 230 anyway, so
  there was nothing that actually needed to be dynamic). General lesson: 
  never bind SVG's camelCase presentation attributes (`viewBox`,
  `preserveAspectRatio`, etc.) dynamically via `:attr` in Alpine (or likely
  any framework using plain `setAttribute` off an HTML-parsed directive
  name) -- keep them static, or set them via the SVG DOM's own typed
  properties (e.g. `svgEl.viewBox.baseVal`) instead of `setAttribute`.

## The woodstove-event taxonomy is a closed set, not free text

`rest_api.c`'s `POST /api/event` validates the request's `event` field
against a fixed `EVENTS[]` list (`cold_start`, `opened_stove`, `added_wood`,
`damper_up`, `damper_down`, `burning_optimally`, `roaring`, `dying_down`,
`fire_out`, `stove_off`) and rejects anything else with a `400`, rather than
logging whatever string a caller sends. Deliberate: per the repo root
`CLAUDE.md`'s "Current phase is data-gathering" section, the whole point of
these annotations is correlating burns against each other later, which
needs a consistent, known vocabulary -- free-text labels from a rushed tap
at the stove wouldn't reliably give that. The slugs are ported verbatim
from the original ESPHome sidecar's own template buttons (`GET
/api/events` exposes both the slug and a human-readable label, e.g.
`{"slug":"roaring","label":"Stove Roaring"}` -- note the slug/label mismatch
on that one specifically, carried over as-is from the ESPHome config rather
than "fixed" to match, since any existing Sheets data already uses `roaring`).

## A WebSocket URI handler is never called for its own handshake

`ws_server.c`'s first version tracked new clients with `if (req->method ==
HTTP_GET) { ...; return ESP_OK; }` inside the registered handler, reasoning
(wrongly) that the handshake request itself would arrive as a `GET` and could
be detected that way. It compiled fine and looked reasonable, but silently
never worked: a client could connect and the server would broadcast forever
without ever reaching it. Confirmed straight from `esp_http_server`'s own
source (`httpd_uri.c`): once `is_websocket` is set, the framework completes
the entire WS handshake internally and explicitly does **not** call the
registered handler for it (its own comment: *"If the request is websocket
handshake, then do not call the uri->handler"*) — the handler is only ever
invoked later, for an actual client→server data frame. `req->method` on such
a later invocation is just the URI's own statically-registered method
(`HTTP_GET`), not a live signal distinguishing "this is the handshake" —
there's no invocation where that branch's premise is even true. Since a
broadcast-only client like `flue-display` never sends anything, the handler
was never entered at all, and the client list stayed empty forever.

The actual hook that fires once a connection is open is
`ws_post_handshake_cb` (a separate callback field on `httpd_uri_t`, gated by
`CONFIG_HTTPD_WS_POST_HANDSHAKE_CB_SUPPORT` — off by default, on in this
project's `sdkconfig.defaults`). Client tracking lives there now;
`ws_handler()` itself only ever runs for a real subsequent frame (a client
CLOSE, or draining an unexpected data frame).

## The onboard NeoPixel's power line is shared with STEMMA QT

`status_led.c` drives the onboard NeoPixel (GPIO0) as a solid WiFi-status
color, but doesn't do any power-enable sequencing of its own -- Adafruit's
own pinout docs confirm the NeoPixel and STEMMA QT connector share the same
power-enable pin (`STEMMA_QT_POWER_GPIO`/GPIO2), and `sensors_init()`
already drives it high, unconditionally, before `status_led_init()` is ever
called in `main.c`. If `status_led_init()` is ever reordered to run before
`sensors_init()`, the NeoPixel would stay dark regardless of what color it's
told to show.

## `esp_http_client` needs its TLS cert bundle attached explicitly

`sheets_logger.c`'s first version against the real Google Sheets webhook
failed every single attempt with `ESP_ERR_HTTP_CONNECT`, even though
`CONFIG_MBEDTLS_CERTIFICATE_BUNDLE=y` (and `..._DEFAULT_FULL=y`) were already
on in `sdkconfig` -- that config only makes the bundle *available*, esp-tls
still has no way to verify `script.google.com`'s certificate unless
`esp_http_client_config_t.crt_bundle_attach` is explicitly set to
`esp_crt_bundle_attach` (from `esp_crt_bundle.h`, `mbedtls` component).
ESPHome's own `http_request` component does this wiring automatically, which
is why the equivalent ESPHome config never needed to think about it. Fixed
by setting `.crt_bundle_attach = esp_crt_bundle_attach` on the config and
adding `mbedtls` to `main/CMakeLists.txt`'s `PRIV_REQUIRES`.

## The regression window assumes a fixed, sensor-matching read cadence

`sensors_read()` admits the thermocouple reading into the rate-regression
window on *every call* — it must only be called on the sensor's own true
update cadence (currently every 30s, from `main.c`'s `sensor_log_task`), not
from an arbitrary poller. This is exactly the rate-inflation bug
`flue-display/CLAUDE.md` documents for its own polling-based rate calc:
timestamping a value that only actually changes once per 30s as if every
poll were a fresh sample makes any real delta look many times faster than
it is. `GET /api/reading` (and any future WebSocket broadcast) must call
`sensors_get_last_reading()` instead — a thread-safe copy of whatever the
periodic task last computed, no I2C traffic, no window mutation.

An implausible reading (outside `-40..600°C`) leaves the rate/zone at their
last-known-good values rather than resetting them, exactly matching the
ESPHome lambda's own `return;`-on-glitch behavior — the raw
`thermocouple_c`/`cold_junction_c` fields are still reported as read either
way; only the *derived* rate/zone are protected from a single glitch
poisoning the ~3-minute window.

## Sensor drivers: vendored official/registry drivers, not copied ESPHome components

MCP9601 uses `esp-idf-lib/mcp960x` via the component registry. Deliberately
*not* copying ESPHome's own `mcp9600.cpp` directly, even though its source
was extremely useful for finding the gotchas above: ESPHome is GPL-3.0 (a
real copyleft concern for otherwise permissively-licensed vendored code),
and that file is written against ESPHome's own `Component`/`i2c::I2CDevice`
base classes and HAL — not standalone, and pulling it in would drag along a
meaningful slice of ESPHome's own core, working against the entire reason
this rewrite exists. Reading ESPHome's source for the *procedural knowledge*
(which register, which pin, which order) while keeping the actual driver
code as the manufacturer's/registry's own reference implementation got the
same debugging value without either problem. (The BMP581 previously used the
same approach -- Bosch's own official `BMP5_SensorAPI`, vendored verbatim --
before the sensor and all its code were removed; see "BMP581 removed"
below.)

## BMP581 removed

The BMP581 (pressure/ambient-temperature sensor) was physically removed from
the board -- its ambient temperature reading was almost a duplicate of the
MCP9601's own cold-junction reading, so it wasn't earning its board space.
All BMP581 code was removed to match: `sensors.c/.h`'s `bmp581_*` fields and
`init_bmp581()`/`read_bmp581()`, `rest_api.c`'s `bmp581_*` JSON fields, the
vendored `components/bmp5/` directory, and its `bmp5`/`BMP581_I2C_ADDR`
references in `CMakeLists.txt`/`config.h`. `sheets_logger.c`'s webhook URL
also dropped its `temperature`/`pressure` query params, which were sourced
from the BMP581 -- **the Google Apps Script webhook itself (external to this
repo) may still expect those params**; not updated here since its source
isn't tracked in this repo.

## `ota_server.c` moved to `../components/`

Was a near-duplicate of `../flue-display/main/ota_server.c` (113 of ~120
lines byte-identical -- the auth check and the entire streaming-OTA-write
handler). Now the shared `components/ota_server/`. The one real difference
between the two projects' old copies -- flue-monitor already has a shared
httpd server to register onto (`rest_api_start()`'s handle), flue-display has
none of its own -- became two entry points on the same component:
`ota_server_register(server, secret)` for a caller with a server already
running, `ota_server_start(secret)` (starts its own dedicated 8192-stack
httpd first) for a caller with none. Each project still keeps its own
`secrets.h`/`OTA_SECRET` (the two devices' secrets are intentionally
different values) -- the shared component takes `secret` as a parameter
rather than including a project-private header itself, so it carries no
secret of its own and doesn't need visibility into either project's
`main/secrets.h`.

## LED/glow pulse-tuning constants now live in settings

`settings_t` (see `settings.h`) gained four fields flue-monitor itself never
reads -- `idle_pulse_period_ms`, `fast_pulse_period_ms`,
`rate_deadband_c_per_min`, `color_transition_exponent` -- purely to be the
one live source both `../flue-display/main/led_display.c`'s physical LED
ring and this device's own `main/web_ui/dashboard.js` glow now fetch via
`GET /api/settings`, the same mechanism `zone_cold_max_c`/
`zone_optimal_max_c`/`fast_rise_c_per_min` already used. Before this, all
four were hardcoded independently in `flue-display/main/config.h` *and*
`dashboard.js` -- two copies with no mechanism keeping them in sync.

That duplication had already drifted: `flue-display/CLAUDE.md`'s own tuning
history describes `COLOR_TRANSITION_EXPONENT` being live-tuned on real
hardware up through **11** ("a longer amber hold, quicker ramp"), but both
hardcoded copies had `3.0` -- the original, untuned guess. **This refactor
deliberately did NOT change the value** -- `DEFAULT_COLOR_TRANSITION_EXPONENT`
in `config.h` is `3.0f`, a behavior-preserving default matching what was
already running, not a silent retune. Whether `3.0` or `11` (or something
re-tuned fresh) is actually correct on the real hardware is still an open
question, now answerable by changing exactly one NVS-backed value instead
of two hardcoded ones.

## `max_uri_handlers` must cover every endpoint on this server

Adding the 4 embedded-font routes (see the web UI section above) pushed
this server's total registered handler count from 13 to 17 -- `rest_api.c`
registers 15 of its own (10 REST endpoints + 5 static assets), plus
`ota_server_register()` (1) and `ws_server_register()` (1), all onto the
same shared `httpd_handle_t`. `rest_api_start()`'s `config.max_uri_handlers`
was already explicitly bumped from `HTTPD_DEFAULT_CONFIG()`'s default of 8
to 16 once before, for exactly this reason (see the comment history) --
but 16 wasn't enough headroom, and 17 > 16 silently wasn't caught by the
build. **The actual failure mode on real hardware: an immediate,
permanent boot crash-loop.** `httpd_register_uri_handler()` fails with
`ESP_ERR_HTTPD_HANDLERS_FULL` once the ceiling is hit; every registration
call is wrapped in `ESP_ERROR_CHECK`, so the *last* one registered --
`ws_server_register()`, called after `rest_api_start()` and
`ota_server_register()` in `main.c` -- is the one that aborts. The device
reboots roughly every 3 seconds forever, re-hitting the identical assert
each time, `esp_ota_mark_app_valid_cancel_rollback()` never being reached
(it's later in `main.c`, after this line) meaning the bootloader's OTA
rollback safety net would eventually have kicked in on its own too, given
enough failed-boot cycles -- caught first via a serial boot log instead of
waiting for that. `POST /ota` is also a registered handler on this exact
same server, so **OTA cannot recover from this failure mode** -- the crash
happens within ~10-20ms of the server starting, before there's any
practical window to push a whole new firmware image through; a USB
reflash (`idf.py -p <port> flash`) was required. Fixed by raising
`max_uri_handlers` to 24, with real headroom above the current count
rather than the exact number, specifically so the next endpoint added
doesn't silently repeat this. **Any future change adding a new
`httpd_register_uri_handler()` call anywhere on this shared server should
double check the total against this ceiling.**

Also discovered while chasing this, but unrelated to `max_uri_handlers`
itself -- see the next section.

## A failed WiFi connect attempt left stale WiFi/netif state for the captive portal fallback

Found on the very first boot after the `max_uri_handlers` fix above's OTA
push: weak WiFi (rssi -77 on this network, see "The REST API server is
single-threaded..." above for prior weak-signal history) caused the
*initial* STA connect attempt to genuinely fail, and `main.c` fell back to
`captive_portal_start()` per its designed failure path -- which then
itself crashed, on `wifi_init_softap()`'s call to
`esp_netif_create_default_wifi_sta()` (`assert failed: ... config or
if_key is NULL or duplicate key`). Root cause: `wifi_setup.c`'s
`wifi_sta_try_connect()` (which just failed) already called
`esp_netif_create_default_wifi_sta()` earlier in the very same boot --
`wifi_init_softap()` unconditionally calls it again, unaware a STA netif
already exists from the failed connect attempt, and the duplicate
registration aborts.

**Fixed**: `wifi_sta_try_connect()`'s own doc comment already said it
"leaves WiFi running in STA mode either way (caller decides what to do
next on failure)" -- the missing half was that no caller ever actually did
anything with that. Added `wifi_sta_teardown()` (`components/wifi_setup/`):
`esp_wifi_stop()` + `esp_wifi_deinit()` + `esp_netif_destroy_default_wifi()`
on the STA netif captured from `wifi_sta_try_connect()`'s own return value
(previously discarded) -- the documented, symmetric counterpart to
`esp_netif_create_default_wifi_sta()`, not a guess at undocumented
behavior. Both `main.c`s now call it in the `have_creds && !connected`
branch, right where `wifi_mark_attempt_failed()` already was, before
falling through to `captive_portal_start()`.

**Verified on real hardware, not just by reasoning about the fix**: forced
a deterministic connect failure (`STA_CONNECT_TIMEOUT_MS` temporarily set
to `1` for one test build/flash, reverted immediately after) and confirmed
via serial log a clean teardown (`wifi:stop sw txq`, `wifi:Deinit lldesc
rx mblock:10`, no assertion) followed by `captive_portal: SoftAP started`
-- no crash. Separately, `flue-display` then hit this exact failure path
*for real* (genuine rssi -89 on a later boot, not the artificial test) and
recovered the same clean way, entering its own setup AP instead of
crashing -- a second, independent, non-artificial confirmation.

## A stale, gitignored `sdkconfig` turned a new Kconfig default into a permanent boot crash-loop

`main.c`'s `configure_power_management()` (added by the "Enable automatic
light sleep on both devices" commit) originally wrapped `esp_pm_configure()`
in `ESP_ERROR_CHECK` -- fine as long as that call could never fail, which
turned out not to be true. That same commit added `CONFIG_PM_ENABLE=y` to
`sdkconfig.defaults`, but the actual `sdkconfig` (gitignored, locally
generated, last regenerated before that commit existed) still had
`# CONFIG_PM_ENABLE is not set` baked in from an earlier build --
`sdkconfig.defaults` only seeds keys *missing* from `sdkconfig`, it never
overrides a key that's already present, so the stale value won silently.
With `CONFIG_PM_ENABLE` actually off, `esp_pm_configure()` returned
`ESP_ERR_NOT_SUPPORTED` (confirmed directly against the installed ESP-IDF
5.5.5 source -- `esp_pm/pm_impl.c`'s own `#ifndef CONFIG_PM_ENABLE`
early-return) on every single boot, right after WiFi connected --
`ESP_ERROR_CHECK` turned that into a hard `abort()`, rebooting forever
before the REST/WS servers ever registered. The symptom that actually
surfaced from this was confusing by itself: `GET /api/reading`/`/ws`
intermittently showed `thermocouple_ok:false` with every field zeroed and
`thermocouple_zone:"unknown"`, which looked like a sensor/I2C problem (the
zone classifier can only read "unknown" if no read has ever succeeded since
the last reset) but was actually just whichever request happened to land
during the reboot window.

Fixed two ways: deleting the stale `sdkconfig` and letting `idf.py build`
regenerate it fresh from `sdkconfig.defaults` resolved this specific
occurrence (verified via a clean serial boot log and 5+ minutes of
uninterrupted sensor reads afterward), and `configure_power_management()`
itself no longer uses `ESP_ERROR_CHECK` -- it logs a warning and continues
without automatic light sleep on any future `esp_pm_configure()` failure,
since that's a far better fallback than bricking the device over a
recoverable power-management config problem. Any future addition to
`sdkconfig.defaults` carries the same latent staleness risk on a machine
with an already-generated `sdkconfig` sitting around -- seeding is one-way,
not a sync, so this exact failure mode can recur for a *different* Kconfig
option later even with this specific fix in place.

## The 24h graph had three real gaps vs. the original design, only one of them a genuine logic bug

Caught by comparing a live screenshot against the original design mockup
(`design-import/Flue Monitor.dc.html`) side by side:

- **Missing status pill.** The graph screen's topbar only ever had a
  settings-gear button on the right; the design shows a colored-dot +
  temp + rate pill there too (same info as the dashboard's own glow
  circle, just compact). Added `.status-pill` next to the gear, reusing
  `zoneColor()`/`rateLabel` that already existed for the dashboard.
- **Missing in-band zone labels.** The bottom-of-screen Cold/Optimal/Hot
  dot legend (`.graph-legend`) was the wrong shape of information -- the
  design puts the actual threshold numbers (e.g. "Hot above 280°C")
  directly on each colored band. Replaced the external legend with
  in-band `<text>` labels drawn inside `graphSvg`'s own band-rendering
  loop (skipped when a band's too thin to hold text legibly).
- **A logged event could visually appear to be "in the future."** This
  one **is not a timestamp bug** -- an event's `age_s` is never negative,
  confirmed by fetching `/api/history` immediately after `POST
  /api/event` on the real device (`events: [[0, "stove_off"]]`, never
  negative). The real cause: temperature *samples* only land every ~4min
  (`HISTORY_PUSH_EVERY_N`), but *events* are logged with second-level
  precision -- so a just-logged event (age 0) legitimately has a smaller
  age than the most recent temperature sample (age up to ~4min), landing
  its marker to the *right* of the curve's last plotted point on the
  x-axis. Visually indistinguishable from "in the future" even though the
  underlying number is correct. Fixed by extending the plotted curve
  itself with a synthetic age-0 point sourced from the already-live
  `GET /api/reading` value (`dashboard.js`'s `graphSvg` getter builds
  `plotSamples = [...samples, [0, reading.thermocouple_c]]` when the
  reading is valid) -- the curve now visibly reaches "now" instead of
  stopping ~4min short of it, and any recent event naturally lands on or
  right at that endpoint instead of past it. Also clamped `xOf()`'s input
  to `[0, maxAgeS]` as a defensive belt-and-suspenders measure. The
  current-reading dot at the curve's end is now colored by the live zone
  too (previously a fixed accent color), matching the design.

## Local mock server for iterating on the web UI without real hardware

`tools/mock_server.py` (stdlib-only Python) serves the real, unmodified
`main/web_ui/` files with synthetic REST responses standing in for the
device -- no ESP32, no flashing, no reboot needed for a CSS/layout/JS-only
change. This exists because the three graph-screen bugs above were hard to
iterate on against the real device: each fix attempt meant a full
build/flash/reboot/reconnect cycle just to see a CSS tweak, and the
"event in the future" bug specifically needed a *freshly logged* event
(age near 0) to reproduce, which the real device's RAM-only event log
loses on every reflash. The mock server's `POST /api/event` handler
reproduces that exact edge case on demand (log an event through the real
UI, it lands at true age 0 immediately) without touching hardware at all.
Verified working end-to-end via a headless Playwright run (`npx playwright
install chromium` -- no project dependency added, this is a one-off dev
tool, not shipped code) that loaded the mock server, clicked into the
graph view, logged a fresh event through the real "Log what you did" flow,
and screenshotted before/after to confirm the marker landed on the curve's
endpoint rather than past it.

## Misc

- **`idf.py monitor` exits with Ctrl+], not Ctrl+C.** Ctrl+C is intercepted
  by the monitor for other purposes. Ctrl+T then Ctrl+H shows its full
  shortcut menu.
- **A background `idf.py monitor`/`esphome logs` session holds the serial
  port open exclusively** — a concurrent `idf.py flash`/`ota_flash.sh` from
  another shell will fail with "Resource temporarily unavailable" until it's
  stopped.


## Zone colours are saved settings

`zone_cold_color`, `zone_optimal_color`, and `zone_hot_color` are eight-byte
NUL-terminated `#RRGGBB` strings appended to `settings_t`. The prior NVS blob
layout is its exact prefix: load it over default-initialized settings and
accept the old prefix length as well as the new full size. This preserves
thresholds, logging credentials, and pulse tuning rather than resetting
them when the palette fields are introduced. Future layout changes must
retain or explicitly migrate this prefix; do not silently reinterpret it.

The settings page uses native colour pickers with the existing draft, Save,
and Undo flow. Defaults match the physical ring's blue/amber/red. Saved
colours drive the glow, status dot, and tinted graph bands. The LED firmware
fetches them through the existing settings_changed notification and snapshots
the palette under its rendering lock. Older sidecars omit these fields, so
the ring retains its current palette; older API clients can omit colours
without resetting them. Explicit invalid colours are rejected.

Both settings POST and the display's HTTP response buffer allow 1024 bytes
so the palette plus maximum-length logging URL/secret fit. Host checks cover
legacy blob migration, persistence/validation, and app save/undo/reload. Both
ESP-IDF builds pass. Chrome visual QA against the local mock server confirms
the native pickers, Save/Undo, reload persistence, and graph palette, with no
console warnings/errors. Both devices were subsequently updated on hardware; the monitor retained
all previous settings and the display fetched settings and real readings.
Physical colour appearance remains for the user to judge.


## Breathing pulse precision and timing

`flue-display/main/led_display.c` keeps colour interpolation and brightness
in floating point until one final rounded conversion per 8-bit channel.
The old path truncated brightness, interpolated colour, and scaled colour
separately, causing a downward bias and coarse steps near the dim trough.
This reduces avoidable quantization; it does not add hardware brightness
resolution or prove physical flicker is eliminated. No dithering or brightness
floor changes were introduced.

The render loop uses an absolute 30ms FreeRTOS schedule and monotonic elapsed
time for pulse phase, so LED transmission time is included in the frame
budget instead of added to the sleep, and scheduling jitter does not stretch
the pulse period. Every 30s it logs observed FPS, average/minimum/maximum
frame interval, and refresh failure count. Read those measurements on hardware
before attributing residual flicker to low frame rate.


Hardware verification on 2026-10-04: boot logs identify display on
`/dev/cu.usbserial-1140` (192.168.1.138) and monitor on
`/dev/cu.usbserial-5C671828951` (192.168.1.137). Verify these anew before any
future flash rather than treating this mapping as permanent. Display updated
over USB after a failed WiFi join put its old firmware into setup mode;
monitor updated over OTA. All prior monitor settings were compared before
and after and retained, including logging credentials. Re-saving the unchanged
settings produced settings_changed and a successful fetch on the display.

With valid thermocouple readings arriving, three consecutive diagnostic
samples measured 33.9–34.0 FPS, average intervals 29.38–29.49ms, minimum
intervals 13.43–16.46ms, maximum intervals 40.76–45.20ms, zero refresh failures.
There is scheduling jitter, but no sustained low frame rate in this test.
Physical flicker improvement has not been judged visually. Initial mDNS
queries and a subsequent HTTP/WS connection timed out; restarting the
display after the monitor was running recovered resolution and subscription.
That existing startup/network flakiness remains a separate issue.


## Adjustable breathing shape

`breathing_exponent` ranges from 0.3 to 3.0 and defaults to 1.0. Apply
`pow(envelope, breathing_exponent)` to brightness and the UI halo only; colour
interpolation continues to use the raw envelope and its separate exponent.
The settings control uses 0.1 steps with rounding and existing Save/Undo.

The float is appended after the palette fields. NVS loading accepts the current
size, the pre-palette prefix, and the palette-only prefix over initialized
defaults. Existing tuning, colours, and logging credentials are preserved.
Older POST clients preserve the current shape when omitting it; the display
defaults to 1.0 when an older monitor omits the field. Reject non-numeric,
non-finite, and out-of-range values. Both firmware builds and host migration/
validation checks pass. Chrome Save/Undo/reload checks pass without console
warnings or errors.

Both devices updated over OTA on 2026-10-04. All monitor settings were
compared before/after and preserved. Display logs confirmed shape 1.0, a
live change to 0.7, then restoration to 1.0, alongside real readings and
33.9 FPS with zero refresh failures. After an OTA upload, allow startup to
complete before opening idf monitor: it resets the board, and resetting a
pending image before WiFi confirmation can trigger rollback. The first
display attempt rolled back; retrying with startup time succeeded.


## LED brightness limits

`maximum_brightness` and `minimum_brightness` are appended uint32 fields,
validated as integers with 0 <= minimum <= maximum <= 255. Defaults 20/255
preserve the previous LED curve. Missing API fields retain saved values;
older monitors give the display default limits. NVS also accepts the
breathing-shape-era prefix ending before maximum_brightness. Limits are
snapshotted under the rendering lock and interpolated with the shaped
envelope, including the neutral no-data pulse. Colour transitions remain
independent and the UI halo keeps its screen-specific treatment.

Both firmware builds pass. Host checks cover migration of all previous
layouts, persistence, equal/off/full bounds and reversed-limit rejection.
Chrome confirms both steppers, Undo, Save and reload persistence.


## Zone theme presets

`ZONE_THEMES` in dashboard.js defines five palettes in `ZONE_ORDER`. The
selector derives its name from the draft colours with case-insensitive
matching, so manual edits and Undo automatically select Custom or a matching
preset. `applyZoneTheme` only fills the three draft colour fields. No theme
identifier is stored or sent to the API: saved colours remain the single
source for the dashboard, graph and ring. Menu buttons show swatches, the
selected state, and support Tab/Enter plus Escape and outside-click dismissal.

The Fire preset uses amber #f29900, orange #f66d00 and red #ff0000 in
cold/optimal/hot order. The matrix applies its colour gamma correction.


## Settings delivery acknowledgement and HTTP session recovery

A successful settings POST confirms NVS persistence, not display delivery.
The response and settings GET include a boot-randomized uint32
`settings_revision`; each successful POST advances it. The display sends
`{"type":"settings_applied","revision":...}` over its WebSocket only after
fetching and applying that revision. `GET /api/settings/status` returns the
current revision and `display_applied`. The UI checks the exact submitted
revision for up to 20 seconds, reports confirmed delivery only on matching
acknowledgement, and otherwise shows a persistent alert while retaining the
saved settings. This proves firmware application, not physical LED appearance.
The display refreshes on reconnect, retries failures after five seconds and
periodically refreshes every 30 seconds to recover missed notifications.

The seven-slot HTTP server formerly used default `lru_purge_enable=false`
and TCP keepalive disabled. Idle HTTP keepalive connections could fill all
slots and prevent new settings fetches, independently of WebSocket leakage.
LRU eviction now permits new requests, with streaming WS clients refreshed
when requests arrive so idle HTTP sessions are preferred. TCP keepalive
uses 30s idle / 10s interval / three retries. The close callback removes WS
bookkeeping for every server session teardown and explicitly closes the fd.
Queued broadcasts carry a client generation to reject reused descriptors.
Diagnostics report peer address, port and HTTP/WS classification; the old
count-only log cannot establish what occupied the original seven slots.

Verification on hardware: unchanged settings were re-saved, applied and
acknowledged by the display (minimum 0, maximum 45). Seven held HTTP
connections did not block a new status request. Ten TCP WS disconnects
without close frames were each removed by the close callback; the server
returned to one WS connection. Both builds pass. Chrome verified the
persistent missing-acknowledgement alert using the mock server with
`MOCK_DISPLAY_APPLIED=false`. Host checks: `node tools/test_settings_sync.js`.
Live socket check: `python3 tools/test_http_socket_recovery.py <monitor-ip>`.


## Ten-second temperature sampling

`SENSOR_READ_INTERVAL_MS` is now 10000. The continuously converting MCP9601
is read and broadcast on an absolute FreeRTOS ten-second schedule. The UI
already polls every five seconds; the LED display consumes each WS reading.
Rate regression now keeps 16 samples instead of six, preserving the original
150-second first-to-last span and using actual timestamps. History still
pushes every four minutes (24 sampling ticks), keeping its 24-hour capacity.
Socket diagnostics remain at 30-second intervals. Sheets logging still uses
its configured deadband/heartbeat, not one log per sensor tick. Earlier
30-second references in this file describe the previous configuration.

## Compressed web assets and cache validation

`tools/generate_web_assets.py` generates deterministic gzip payloads for
HTML/CSS/JS and content-hash ETags for all static assets, including fonts.
The main component's custom build dependency regenerates the header whenever
an asset changes. Text assets are stored only as gzip. Clients that do not accept gzip
(including `gzip;q=0`) receive a chunked identity response decoded using the
ESP32 ROM inflater with a temporary 32 KiB dictionary plus inflater state. WOFF2 fonts are already compressed
and are served unchanged. Compression takes place on the build machine.

Static responses use `Cache-Control: no-cache`, which permits storage but
requires validation, with `If-None-Match` returning an empty 304 when content
is unchanged. Compressed and identity representations have separate ETags
and `Vary: Accept-Encoding`. Changed assets get new tags, so an OTA cannot
leave a browser using stale UI files. REST settings/reading responses do not
use this static-asset handler.

Built and flashed on 2026-10-08. `python3 tools/test_web_assets.py <monitor-ip>`
verified every static payload against source, 304 responses, stale-tag
recovery, identity fallback and gzip refusal. Chrome rendered the live UI.
The four text assets shrank from 117534 to 37340 bytes. Same-firmware
sequential direct-IP tests measured 0.29–0.36s compressed versus 0.72s
identity on the then-current link; these are transfer timings, not full
browser load times. Saved settings were preserved. Hostname resolution is
unchanged by this update.


## Settings acknowledgement follows setting ownership

`DISPLAY_SETTING_KEYS` in dashboard.js lists colours, zone/rate thresholds,
brightness and breathing controls consumed by the display. Save compares the
submitted snapshot against the last saved settings before issuing the POST.
Only changes to those keys wait for the matching display revision. Logging
heartbeat, thermocouple logging deadband and Sheets URL/secret need only the
monitor's successful settings POST; mixed saves still wait for the display.
The save bar says Saving rather than checking display for monitor-only edits.
`node tools/test_settings_sync.js` covers each monitor-only field plus mixed
logging/colour changes and existing acknowledgement success/failure cases.

## Live WiFi indicators for both devices

The dashboard shows Monitor and Display signal bars, a strength label and
RSSI in dBm. `GET /api/devices/wifi` returns the monitor's current AP RSSI and
the display's latest `wifi_status` WS report; the UI polls every ten seconds.
The display uses its existing WS connection, not an extra HTTP connection.
The monitor invalidates the display value immediately when its reporting
session closes, or after 35 seconds without a report. Offline means the
display link/report is unavailable, not a measured RF signal of zero. Failed
UI status requests clear the cards to Unavailable instead of retaining stale
values. Strength labels use >= -60 Strong, >= -70 Good, >= -80 Fair,
otherwise Weak; labels are a heuristic, not a throughput measurement.

Local mock data is configurable with MOCK_MONITOR_RSSI, MOCK_DISPLAY_RSSI,
MOCK_MONITOR_CONNECTED and MOCK_DISPLAY_CONNECTED. The approved prototype
was visually checked in Chrome with weak/strong and offline states. Both
firmware builds pass. `python3 tools/test_wifi_status.py` compiles the actual
freshness and session-close functions to verify expiry, close and descriptor
reuse invalidate old RSSI.

Hardware updated on 2026-10-08: monitor over OTA, display over confirmed USB
84:0d:8e:d2:a6:ec after its OTA request redirected to the setup portal.
Live API and Chrome showed both connected, roughly monitor -81/display -69
dBm. Saved settings matched the pre-flash snapshot and display acknowledgement
was true. Chrome also confirmed a logging-heartbeat-only save immediately
succeeded with the mock display acknowledgement disabled.


## uPlot burn graph local preview

The SVG history renderer is replaced by vendored uPlot 1.6.32 (MIT license
in main/web_ui/vendor). burn-graph.js owns an unproxied chart in a child
Alpine component; it destroys the chart and ResizeObserver when leaving
the graph. It preserves zone bands/threshold labels and event markers, adds
time/temperature axes, drag/wheel zoom and touch pinch/pan. Event captions
are drawn beside their markers with collision spacing and leader lines;
overcrowded captions reappear when zoomed. Double-click restores the full
24h window. Preset/zoom/reset buttons, custom date inputs and event chips
were removed after local review.
Browser wall-clock time anchors the device's monotonic ages when history
is fetched; clock labels are approximate and history remains four-minute
samples for 24 hours. Zoom does not create finer sensor history.

Local live preview: `python3 tools/ui_proxy.py http://192.168.1.137 8773`.
The proxy serves local assets and forwards only GET /api requests; POSTs
are rejected so preview settings/event actions cannot change the monitor.
Synthetic burn preview: `python3 tools/mock_server.py 8774`. Both bind only
to localhost. New graph assets are embedded/compressed with ETags for a
future flash, but neither device was flashed for this preview.

Preview verification: Chrome checked live history, sample-burn rendering,
clustered inline event captions, removal of graph controls, gesture zoom,
double-click reset and leaving/reopening the graph without a loading blank;
no console errors. Host checks cover shared in-flight history requests,
30s cache reuse, retained data on refresh failure and initial load failure. Touch
gestures are implemented but have not been verified on a physical phone.
The firmware builds with about 4% app-partition headroom; revisit asset
storage/partition sizing before adding further substantial dependencies.

History preloads after the initial dashboard requests and is reused for 30s.
Overlapping loads share one request. Background refreshes preserve the old
curve; failed refreshes retain it too. The history receipt time anchors its
monotonic ages, so opening prefetched history later does not shift events.


## Single-copy compressed assets

Dashboard text files and captive-portal HTML/CSS/Alpine are now embedded only
as gzip. The monitor reuses the shared portal's compressed CSS and Alpine;
`generate_web_assets.py` asserts the dashboard CSS is byte-identical to the
portal stylesheet. Fonts remain single-copy WOFF2. The shared
`compressed_assets.c` uses ESP32 ROM miniz for streaming identity responses;
normal gzip browser responses allocate no decompression buffer. Identity
fallback allocates a 32 KiB dictionary plus inflater state on the heap,
frees both after completion or send failure, and returns 503 on allocation
failure. Representation-specific ETags, no-cache validation, and gzip refusal
continue to work through the existing monitor response handler.

2026-10-10 build: monitor image shrank from 0x1671b0 to 0x1375c0, saving
195568 bytes (191 KiB); free OTA-slot space grew from 4% to 17%. Both monitor
and display builds pass. `python3 tools/test_compressed_assets.py` checks
build-generated payloads, tags, and sharing. Passing an upstream miniz v114
source path also compiles the actual C fallback against its reference tinfl
implementation and checks byte-exact multi-chunk decoding, gzip negotiation,
disconnect handling and invalid headers. The existing
`tools/test_web_assets.py` remains the on-device gzip/identity/cache check.
These asset changes have not yet been flashed; ROM/runtime verification and
captive portal browser verification remain for hardware deployment.


## Experimental on-device PageKite dashboard

The monitor runs PageKite directly (`main/pagekite_tunnel.c`) with verified
ESP-TLS relay identity `frontends.b5p.us`, the existing CA bundle and an SNTP
wait before certificate validation. It starts after the REST API when enabled
in NVS settings. Settings → PageKite edits enabled/domain/shared secret;
no build-time credentials or private include directory remain. First enable
creates the tunnel task; after disable it waits without open relay/backend
sockets. Settings changes allow one second for the save response, then clean
up all sockets and reconnect with a fresh settings snapshot. Notifications
interrupt backoff/disabled waits. The monitor resolves the pool, probes every
returned IPv4 relay with TLS verification, chooses the lowest handshake
latency, updates kite DNS via
`https://up.pagekite.net/` using the PageKite SHA-1 signed update, then opens
a fresh verified tunnel to the selected relay. TLS contexts are sequential to
keep memory bounded. DNS update failures keep the tunnel closed and retry.

Public `https://flumonitor-vanutsteen.pagekite.me/` supports the dashboard,
settings edits and event logging. GET/POST /api/settings map to
/api/tunnel/settings. GET strips Sheets secret/webhook URL and adds
credentials_redacted; POST preserves omitted credentials and accepts explicit
replacements. Placeholder text explains that unchanged fields retain saved
values. GET /api/settings/status exposes the normal display acknowledgement
flow. Dashboard authentication is implemented; see the "Dashboard
authentication" section below for its routes, limitations, and USB recovery
status. OTA and WiFi setup remain outside dashboard routing. The display
retains its existing LAN WebSocket, which is not gated by the dashboard
session.

Eight streams, two local backend sockets and a 4 KiB receive buffer bound
memory. Combined request/header buffers grow in 512-byte increments to at
most 4 KiB only while collecting/queueing, and are freed after forwarding.
POST bodies must be application/json with one explicit Content-Length below
2048 bytes (the settings handler allocates its body on the heap). Fragmented
bodies are collected before local forwarding; upgrades, duplicate lengths, pipelined and truncated requests are
rejected. Each socket is half-closed for writing after its complete request:
ESP-IDF HTTPD does not close just because Connection: close was requested.
TLS failures close all backend sockets before 2–60 second reconnect retries.
HTTP server max_uri_handlers is now 32, leaving room beyond the new POST route.

2026-10-10 hardware: editable dashboard API, six-client concurrency and all
eleven public asset gzip/identity/ETag checks passed. Public monitor-only and
display-setting saves/restoration passed; stored credentials retained and the
display acknowledged matching revisions. Event POST transport was tested with
an invalid slug to avoid inserting fake burn data. Image 0x1395b0 leaves 16%
app-slot space. A 9260-byte mixed-traffic heap minimum led to temporary request
buffer allocation; final hardware checks were repeated after that improvement.
Automatic relay selection and signed DNS updates are implemented in firmware,
but have not yet been deployed or verified on hardware. Long-term soak, forced
WiFi loss and visitor authentication remain unfinished. See tools/pagekite-prototype/README.md,
tools/test_pagekite.py and tools/test_pagekite_dashboard.py. Temporary tunnel
credentials are removed after tests; rebuilding no longer requires a secret.

PageKite configuration is an appended settings_t tail. NVS migration accepts
the earlier PageKite structure without custom_domain and seeds that new field
empty; earlier settings prefixes remain supported. The primary pagekite.me
name is still used for DDNS, while an optional custom CNAME hostname is
registered as a second kite on the same tunnel. Both LAN and public GETs expose
only pagekite_secret_set; POST preserves blank/omitted secrets and omitted
PageKite fields. The legacy relay slot remains for blob migration but is not
exposed or used. Strict type/length and domain validation reject protocol
injection. Successful UI saves discard the submitted secret while retaining
any newer edit. PageKite keys are monitor-only. Tests:
`tools/test_pagekite_settings.py` executes actual settings/REST code with NVS
shims and cJSON under ASan/UBSan; `tools/test_pagekite_configuration.py`
reversibly verifies live configure/disable/re-enable/secret replacement.

Final editable-firmware check: free heap 106548 bytes; minimum 28232 bytes; reconnects 0. Temporary settings changes were restored and both device links remained healthy.

2026-10-10 configurable tunnel: first OTA image 0x139d70 passed hardware NVS
migration (every preceding field retained), configure/blank-secret saves,
remote disable acknowledgement, LAN re-enable and secret replacement/restore.
Chrome mock settings save cleared the password field and dirty bar. A later
probe unexpectedly showed uptime 16 seconds, followed by network loss at
192.168.1.137; no USB serial port was available to determine reset cause.
Compiler stack frames show Sheets task snapshot 816 bytes plus log_to_sheets
784 bytes before HTTP/TLS calls. Prepared extra logging-task stack headroom
(4096 → 6144) and a reset_reason in /probe; image 0x139f80 leaves 16% free.
This additional image and reboot/persistence verification still need deployment
once the monitor is reachable. Do not claim the low-uptime restart diagnosed.


## Dashboard authentication

The embedded monitor dashboard and its REST API use a password stored as a
salted PBKDF2-HMAC-SHA-256 hash in the separate `dashboard_auth` NVS namespace.
`GET /api/auth/status` exposes only whether initial setup is complete. The
first password can be set only from the LAN address; the peer socket identifies
IPv4/IPv6-mapped loopback tunnel requests, so forged Host headers cannot bypass setup
protection. Socket lookup errors fail closed. Login creates one in-RAM, high-entropy
cookie: a browser-session cookie by default (no Max-Age/Expires), or a
persistent cookie with Keep me signed in (only one browser session is active at a time). Both modes end on monitor
restart; no sessions are stored in NVS. Remembered cookies use a 400-day
browser lifetime renewed during authenticated requests; browser cookie
removal/expiry can still require sign-in. Five
failed logins trigger a 30-second global lockout. Changing the password
requires the current value and matching confirmation, then invalidates the
session. Cookie-authenticated state-changing requests require an exact matching
http(s) Origin; remote writes require HTTPS and remote cookies are Secure. Authentication covers the dashboard assets and REST
endpoints; OTA retains its separate secret. The display's device WebSocket
remains compatible and is not gated by dashboard sessions. Unauthenticated
LAN GET /api/settings strips credentials for the display. Initial LAN
commissioning POST /api/settings is allowed only before password enrollment
and requires Origin. Omitted Sheets credentials always retain stored values.
The tunnel forwards Cookie/Origin and accepts only configured Host names.
The custom HTTP domain redirects to the primary HTTPS hostname. The old
unauthenticated /probe diagnostic shortcut was removed.

Important limitations: the local dashboard uses plain HTTP, so LAN observers
can capture credentials and session cookies. There is not yet a USB-serial
password recovery command; app-only flashing preserves the password and a full
flash erase clears all NVS settings. Do not describe either as a safe recovery
path.

The local proxy in `tools/ui_proxy.py` remains a separate design/demo server;
its `review` password does not authenticate the firmware.

Auth checks: tools/test_dashboard_auth.py runs actual auth code with real
PBKDF2 via CommonCrypto plus HTTP/NVS/clock shims under ASan/UBSan;
tools/test_login_page.js executes the actual inline login script.
Settings/tunnel tests also cover credential-free LAN reads, unauthorized
writes, first-use commissioning, Host spoofing and Cookie/Origin forwarding.
Crypto errors fail closed; cookies require exact names/64-character values.
Firmware build 0x13cb80 leaves 16% application-slot space and was deployed
by OTA. The first transfer temporarily served the setup portal and returned
to previous firmware; the cause was not established. Final hardware checks
confirmed LAN enrollment allowed, remote enrollment denied (403), remote
reading/settings GET and settings POST denied without login (401), and
/probe removed (404). The custom HTTP hostname redirects (303) to the
primary HTTPS hostname. Existing settings were retained when correcting
the primary/alias configuration. The owner must choose the first password
locally; real-device authenticated login awaits that enrollment.

The server can report IPv4 HTTP peers as IPv6-mapped addresses; auth locality
handles both families. Only RFC1918/link-local IPv4 and IPv6 ULA/link-local
clients can enroll locally, and loopback always counts as tunnel/remote.
Hardware initially reported setup_local_only=true even over LAN until this
mapped-address correction; the final image reports local enrollment correctly.

2026-10-12 login fix: ESP-IDF's httpd_resp_set_hdr retains the value pointer
until the response is sent; a stack-local Set-Cookie in dashboard_auth_login
expired before auth_form_handler sent its JSON. The cookie buffer now has
static lifetime (the single HTTP server task serializes handlers). The auth
test shim now retains the pointer instead of copying it, and forces ASan
stack-use-after-return detection: it fails on the previous implementation and
passes with the fix. Login uses explicit DOM references, progress/success
messages, catches network/non-JSON errors, and aborts after 20 seconds.
Firmware 0x13d120 builds with 15% slot space remaining. Final OTA succeeded; LAN and HTTPS serve the new page and both report the
existing password configured after reboot. Owner login must be verified with
their own password, which was not reset or requested.

2026-10-12 login design: warm dashboard palette, Caprasimo/Figtree, responsive full-height form and accessible password visibility toggle.
Login fonts are public credential-free assets; dashboard data/assets remain
session-protected. Initial enrollment and login keep progress/error feedback.
No pretend remember-me or recovery controls were added. Actual inline page
previewed in Chrome at localhost:8876; script regression checks and firmware
build pass. The glow was removed at the owner’s request; image 0x13dc30 was flashed
by OTA and verified after reboot: new login HTML without glow, all three
login fonts available without a session, existing password still configured.

2026-10-13 sessions: unchecked login expires at exactly 24 hours; Keep me
signed in skips server expiry until restart. Logout/password change still
revoke access, and a later login still replaces the single active session.
Host tests cover the 24-hour boundary, long remembered uptime, restart,
logout and password-change revocation; actual login script tests cover both
checkbox payloads. Image 0x13df10 (15% slot free) built and flashed via OTA.
After reboot the new checkbox/duration HTML and retained password were
verified on the monitor. No owner password was requested or reset.

2026-10-15 tunnel outage: both public names returned relay-generated 503
(offline, FE); LAN auth status remained reachable. Local and public DNS
resolvers agreed on 95.216.158.189, so no DNS mismatch was observed.
Previously connected meant successful initial relay authentication only;
there was no active probe, so a silently lost tunnel could remain connected
in the UI indefinitely. Added a PING every 30 seconds and a 15-second matching
PONG deadline; timeout goes through existing socket cleanup/reconnect.
Only a matching PONG clears the pending probe. UI now says Relay connected
and explicitly does not claim public availability is checked. Host routing/
framing/queue tests cover heartbeat success, wrong PONG and exact timeout,
and pass with ASan/UBSan. Initial live failure cause cannot be proven without
relay/device logs; heartbeat is not an end-to-end public-hostname check.
Final image 0x13e290 (15% slot free) deployed successfully by OTA. Both
public URLs returned the login page in six checks spaced 15 seconds apart
(across multiple probe cycles); the custom HTTP hostname redirects to the
primary HTTPS hostname. Existing password configuration survived reboot.
This is a short live availability check, not a long-term soak or proof of
the original outage cause.

Browser-session update: unchecked login now uses a standard session cookie
without Max-Age/Expires, with no separate 24-hour server cutoff. The browser
manages session lifetime (session restoration can preserve such cookies).
Checked retains the persistent cookie until monitor restart. Both modes
remain in RAM and are revoked by logout/password change/new login.
Image 0x13e250 built and flashed; login copy and retained password
configuration verified after reboot. Host auth tests verify omitted expiry
attributes for unchecked login, persistent-cookie attributes for checked
login, no 24-hour cutoff, missing-cookie rejection and restart revocation.

2026-10-16 naming: user-facing product text is Flue Monitor/Flue Display;
setup AP names are Flue Monitor Setup / Flue Display Setup, with existing
setup passwords preserved. mDNS names are flue-monitor / flue-display;
display monitor discovery matches the new monitor name. Monitor flashed by
confirmed IP .137; new flue-monitor.local and login branding verified.
Display OTA to confirmed .138 completed but its post-OTA /status reports
failed Wi-Fi association and it serves the setup portal. Neither old nor
new display mDNS name responds. A power cycle has been requested to retry
stored credentials (pending-verify rollback may require another OTA). No
serial device is available and no credentials were erased or replaced.
Do not claim display discovery/settings acknowledgement verified.

Owner renamed GitHub repo to LeonB/flue-monitor. Local origin now uses
git@github.com:LeonB/flue-monitor.git and ls-remote succeeds. Checkout is
/Users/leon/Workspaces/go/src/github.com/LeonB/flue-monitor, with flue-monitor/
and flue-display/ subfolders; CMake projects and artifact names match.
Both fresh builds pass at the new paths; old generated caches are preserved
in /tmp/flue-monitor-rename-builds-20261016. Ignored main/secrets.h files
are preserved and still ignored. Production display WS override is empty.
Public PageKite/DNS names are unchanged; remaining inventory is in README.
The Codex workspace is now open at the renamed checkout. No changes committed or pushed in this rename.

Naming cleanup: setup AP passwords in source now use flue-monitor-setup /
flue-display-setup. This supersedes the earlier password-preservation notes;
these changes have not been flashed.

2026-10-16 deployment after naming cleanup: rename committed as b39b0be.
Both production firmware builds pass (monitor 15% / display 29% OTA-slot
headroom); display test WS override is empty. Login-page and settings-sync
host checks pass. Monitor OTA to confirmed .137 returned OK, rebooting;
flue-monitor.local auth status and redacted settings respond after reboot,
with saved settings retained. Display OTA to confirmed .138 redirected to
the captive portal instead of accepting firmware. Its /status still reports
failed Wi-Fi association to the stored SSID. Display remains unflashed for
this cleanup; power-cycle or USB recovery is needed. No USB serial device
is currently available. The new setup password is therefore deployed on the
monitor only. Untracked design-import files and resume.txt were not committed.

2026-10-16 display recovery: owner power-cycled the display. Confirmed .138
returned normal HTTP 404 for /status instead of captive-portal JSON. Retried
OTA with the built flue-display.bin: full upload returned OK, rebooting.
After reboot flue-display.local resolves to .138 and serves the normal
HTTP 404 response; /status no longer reports setup failure. The code starts
mDNS after Wi-Fi connection and rollback cancellation. Naming cleanup is
now flashed on both devices, including their new setup passwords. Monitor
settings acknowledgement and display RSSI endpoints require dashboard login;
no authenticated session is available, so end-to-end settings acknowledgement
and physical display output remain unverified.

2026-10-16 cached startup: HTTPS/localhost pages register /service-worker.js.
The worker caches only the public, self-contained /loading.html connecting
screen and serves it for root navigations. That screen fetches fresh root
HTML with the current session cookie, then replaces its document with the
live dashboard/sign-in page. API data and authenticated HTML are never put
in Cache Storage. HTTP LAN origins keep the ordinary network startup. The
asset generator substitutes a hash of the worker and loading screen into
the cache name; activation removes only older flue-startup-* caches. Both
new public routes are explicitly allowed through PageKite. Chrome preview
verified immediate shell with an 8-second server delay, unavailable-server
message and retry recovery. Actual iPhone launch behavior still needs testing.

2026-10-17 dashboard sessions: dashboard_auth.c now keeps eight independent
RAM session slots with per-session remember flags and last-use timestamps.
Successful re-login rotates only the requesting session; a new client uses
a free slot or evicts the least recently used one at capacity. Logout clears
only the matching token. Password changes and initialization revoke all
sessions. Credential NVS format is unchanged. The host auth regression
exercises desktop/phone coexistence, independent cookie lifetimes/logout,
re-login at capacity, LRU eviction and all-session revocation.


2026-10-26 versioned assets (local, not flashed): the asset generator adds
?v=<24-character SHA-256 content hash> to dashboard and manifest references;
login HTML uses the same generated URL macros. Launch images retain size and
append &v. Matching static versions receive private, max-age=31536000,
immutable; stale/malformed versions return 404 with no-store. Unversioned
URLs, HTML and the fixed service-worker URL retain no-cache validation.
Hashes identify identity content; gzip/identity ETags remain representation
specific. PageKite preserves queries for allowed static paths after exact
route validation, while API remapping remains unchanged.

The dashboard preloads all four fonts and explicitly loads the faces before
removing its startup overlay, bounded to two seconds on slow/failing fonts.
The worker still caches only the public loading screen. Host checks include
actual serve_asset C under ASan/UBSan, generated dependency invalidation,
PageKite forwarding, compressed assets, login and worker behavior. Chromium
at phone viewport verified 700ms delayed fonts finish before reveal and
3000ms fonts cannot hold the overlay indefinitely, with no page errors.
Firmware builds at 0x160340 (6% app-slot free). Real-device cache headers and
iPhone home-screen launch behavior await deployment/verification.

2026-10-26 deployment: versioned-assets image 0x160340 uploaded successfully
by OTA to confirmed monitor .137 (OK, rebooting). LAN auth status reports
existing password configured and the exposed saved settings match the
pre-flash snapshot, excluding boot-randomized settings_revision. Public HTTPS
checks verified current versioned sign-in URLs, all four font payloads,
manifest, touch icon and 1179x2556 launch image against generated bytes;
matching URLs return immutable headers and 304, stale versions return
404/no-store. Legacy font and service-worker URLs still use no-cache.
Direct LAN curl also confirmed the versioned font immutable header. The
Python LAN verifier could not connect while curl succeeded; do not interpret
that tool failure as proven monitor unavailability. Owner iPhone launch and
authenticated dashboard behavior still require owner verification after login.

2026-10-27 startup layout: the cached loading document used content-box
sizing (30px outer spinner), while dashboard.css changed the embedded
startup overlay to border-box (24px spinner) and applied -0.015em heading
letter-spacing. Chromium at 390x844 measured a 3px downward shift and a
135.70px to 131.39px title-width change during the shell/dashboard handoff.
Both startup copies and the login startup styles now explicitly use
border-box and normal heading letter-spacing. Browser measurements after
the fix match exactly for SVG, title, message and spinner rectangles and
computed fonts. Asset/auth/login/worker host checks pass; build 0x1603b0
leaves 6% slot space. OTA to confirmed monitor .137 returned OK, rebooting.
Public HTTPS /loading.html after reboot matches the corrected source byte
for byte. iPhone home-screen appearance remains for owner verification;
the changed loading source also changes the startup-worker cache version.
