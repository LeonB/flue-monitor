"""Cycle-stepped two-core model of the ESP32 ECO3 IWDT livelock handler (v3).

Runs the REAL C of (a) the original SDK transition + tick, (b) the deployed
project patch + its tick, (c) the proposal + its tick, as coroutines on the
modelled cores, while both halves of .handle_livelock_int (highint_hdl.S,
6.0.3) run op by op from the assembly on whichever core takes the interrupt.
Modelled: _lx_intr_livelock_sync/app/pro, CPU1's interrupt (un)mapping, every
separate register write, TIMG_WDTWPROTECT as a value register (open iff it
holds the key), stage0/stage1, feed, INT_RAW, timer progress every cycle,
FreeRTOS tick ISR on CPU0 (deferred behind the spinlock / critical level),
both transition directions, an extra stall at any handler step of CPU1, a
hung other core, and an invariant evaluated after every cycle.

Interrupt delivery: INT_RAW set, core's TG1 interrupt mapped, PS.INTLEVEL<4,
not already in the handler.  counter >= max takes the PANIC path exactly like
the compiled `bltu a0,a5`.

Still a model: cycle costs are parameters, not measurements; TICK is scaled;
APB arbitration is a fixed cost; abort() is an outcome, not a panic handler.

CLI of a built binary (all key=value, defaults shown):
  apb=4 delay=2160 efuse=60 stall_pc=-1 stall_len=0 tick=500 core=0 hung=0 dir=0
  exp_from=.. exp_to=.. exp_step=1 tick_from=NONE tick_to=NONE tick_step=1
  trace_exp=.. trace_tick=..   (trace one run to stderr)
dir=0: sleep entry (livelock mode -> plain IWDT).  dir=1: wake (plain -> livelock).
"""
import itertools, json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = Path(os.environ.get('FLUE_PROJECT', '')) if os.environ.get('FLUE_PROJECT') else None
for cand in [HERE.parent.parent, HERE.parent, Path('/Users/leon/Workspaces/go/src/github.com/LeonB/flue-monitor/flue-monitor')]:
    if (cand / 'tools/patch_iwdt_transition.py').exists():
        PROJECT = PROJECT or cand
        break
sys.path.insert(0, str(PROJECT / 'tools'))
from patch_iwdt_transition import generate  # noqa: E402

SDK = Path(os.environ.get('IDF_PATH') or (Path.home() / 'Library/Caches/esphome/idf/frameworks/6.0.3'))
NOEXP = 1000000000
NOTICK = 1000000000


def function(source, name):   # same extractor as tools/test_iwdt_transition.py
    match = re.search(r'^.*\b' + name + r'\([^;]*?\)\s*\{', source, re.M)
    assert match, name
    end = match.end()
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end]


HARNESS = r'''
#define _XOPEN_SOURCE 600
#include <ucontext.h>
#include <setjmp.h>
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ESP_SYSTEM_IRAM_ATTR
#define CONFIG_ESP_INT_WDT 1
#define CONFIG_ESP32_ECO3_CACHE_LOCK_FIX 1
#define CONFIG_ESP_INT_WDT_CHECK_CPU1 1
#define CONFIG_ESP_INT_WDT_TIMEOUT_MS 800
#define IWDT_LIVELOCK_TIMEOUT_MS 20
#define IWDT_STAGE0_TIMEOUT_US 1600
#define IWDT_STAGE1_TIMEOUT_US 3200
#define WDT_STAGE0 0
#define WDT_STAGE1 1
#define WDT_STAGE_ACTION_INT 0
#define WDT_STAGE_ACTION_RESET_SYSTEM 1
typedef int wdt_hal_context_t;
static wdt_hal_context_t iwdt_context;
static int s_iwdt_configure_lock;
uint32_t _lx_intr_livelock_counter, _lx_intr_livelock_max;
volatile bool int_wdt_cpu1_ticked = false;

/* ---------------- parameters (cycles) ---------------- */
static unsigned P_ORDER = 0, P_TICK_PERIOD = 0, P_TICK_COUNT = 1, P_TICKS = 0, P_COUNTER = 0;
static bool initial_plain_expired;
static unsigned P_APB = 4;      /* one APB/DPORT register access incl. memw      */
static unsigned P_DELAY = 2160; /* handler's explicit CCOUNT delay loop          */
static unsigned P_EFUSE = 60;   /* soc_has_cache_lock_bug(): efuse reads         */
static int      P_STALL_PC = -1;/* handler step of CPU1 after which it stalls    */
static unsigned P_STALL_LEN = 0;/* ... for this many extra cycles                */
static unsigned TICK = 500;     /* cycles per WDT tick (physical: 120000 @240MHz)*/
static bool     OTHER_HUNG = false; /* other core never takes interrupts/ticks   */
static int      DIR = 0;        /* 0: enable=false (sleep entry) 1: enable=true  */

/* ---------------- world ---------------- */
#define WKEY 0x50D83AA1u
static uint64_t cyc, t0;
static unsigned active_stage;
static uint32_t wdt_cnt;                   /* cycles since last accepted feed */
static uint32_t hw_stage0, hw_stage1;      /* ticks */
static uint32_t wp_key;                    /* TIMG_WDTWPROTECT value; open iff == WKEY */
#define WP_OPEN (wp_key == WKEY)
static bool int_raw, stage0_fired, app_mapped, tick_req[2];
volatile uint32_t _lx_intr_livelock_sync[2], _lx_intr_livelock_app, _lx_intr_livelock_pro;   /* handler bookkeeping (highint_hdl.S .data) */
typedef struct { int level, saved_level; bool in_h; int pc; unsigned busy; uint32_t tmp_max, sync0, sync1; } cpu_t;
static cpu_t cpu[2];
static int our_core;
enum { R_RUNNING = -1, R_OK, R_PANIC, R_RESET, R_DEADLOCK, R_ABORT, R_BADFINAL, R_N };
static const char *RNAME[] = {"ok","PANIC","STAGE1_RESET","DEADLOCK","ABORT","BAD_FINAL"};
static int outcome;
static uint64_t deadline;
static unsigned entries[2], blocked_c_writes, panic_core;
static uint32_t panic_stage0, panic_max, panic_counter;
static uint64_t last_feed, max_feed_gap, first_feed; static unsigned c_feeds;
static uint64_t viol_cycles, viol_pending, latent_cycles, stage1_bad; static long viol_min_margin;
static char bad_reason[128];

static bool TRACE;
#define TR(...) do { if (TRACE) { fprintf(stderr, "%8llu ", (unsigned long long)cyc); fprintf(stderr, __VA_ARGS__); fprintf(stderr, "\n"); } } while (0)

/* ---------------- activities (C code as coroutines) ---------------- */
/* Switching: the first entry goes through makecontext/swapcontext, every later
   switch through _setjmp/_longjmp (no signal-mask syscall; ~20 ns on macOS). */
typedef struct { ucontext_t ctx; jmp_buf jb; char *stack; unsigned busy; bool done, started; void (*fn)(void); int core, saved_level, crit_saved; const char *name; } act_t;
#define STACK_SZ (256*1024)
static act_t acts[4]; static int nacts;
static act_t *astack[2][3]; static int nast[2];
static act_t *cur; static jmp_buf *sched_jb;

static void yield_(void) { act_t *a = cur; if (_setjmp(a->jb) == 0) _longjmp(*sched_jb, 1); }
static void act_entry(void) { cur->fn(); cur->done = true; yield_(); }
static void resume(act_t *a)
{
    jmp_buf here; jmp_buf *prev = sched_jb; sched_jb = &here; cur = a;
    if (_setjmp(here) == 0) {
        if (!a->started) { a->started = true; ucontext_t dummy; swapcontext(&dummy, &a->ctx); }
        else _longjmp(a->jb, 1);
    }
    cur = NULL; sched_jb = prev;
}
static act_t *act_push(int core, void (*fn)(void), int level, const char *name)
{
    act_t *a = &acts[nacts++];
    if (!a->stack) a->stack = malloc(STACK_SZ);
    a->busy = 0; a->done = false; a->started = false; a->fn = fn; a->core = core; a->name = name;
    /* If the core is inside the handler right now, the C code starts after rfi: adjust the level the handler will restore. */
    int *base = cpu[core].in_h ? &cpu[core].saved_level : &cpu[core].level;
    a->saved_level = *base; if (*base < level) *base = level;
    getcontext(&a->ctx); a->ctx.uc_stack.ss_sp = a->stack; a->ctx.uc_stack.ss_size = STACK_SZ; a->ctx.uc_link = NULL;
    makecontext(&a->ctx, act_entry, 0);
    astack[core][nast[core]++] = a;
    TR("  CPU%d: %s starts (level %d)", core, name, cpu[core].level);
    return a;
}
static void advance(unsigned n) { assert(cur); cur->busy = n; yield_(); }
static void finish(int r)
{
    outcome = r;
    TR("== %s %s stage0=%u stage1=%u max=%u counter=%u int_raw=%d wp=%s cpu0{lvl%d,h%d,pc%d} cpu1{lvl%d,h%d,pc%d} sync=%u,%u app=%u pro=%u",
       RNAME[r], bad_reason, hw_stage0, hw_stage1, _lx_intr_livelock_max, _lx_intr_livelock_counter, int_raw, WP_OPEN ? "open" : "closed",
       cpu[0].level, cpu[0].in_h, cpu[0].pc, cpu[1].level, cpu[1].in_h, cpu[1].pc, _lx_intr_livelock_sync[0], _lx_intr_livelock_sync[1], _lx_intr_livelock_app, _lx_intr_livelock_pro);
    if (cur) yield_();   /* never resumed */
}
static int me(void) { return cur ? cur->core : our_core; }

/* ---------- handler op machine, straight from highint_hdl.S ---------- */
/* pc: 0 entry,1 app++,2 sync[me]=1,3 wait both,4 counter++,5 delay,6 after-delay branch,
   7 core0 remap app int,10 core0 wait re-entry,11..14 core0 wdt_clr_intr_status,
   8,15..19 core1 wdt_feed (8 open,15 read max,16 stage0,17 stage1,18 feed,19 close),
   9 core1 unmap, 20 exit bookkeeping (sync=0), 21 rfi */
static void h_op(int c)
{
    cpu_t *u = &cpu[c];
    int before = u->pc;
    switch (u->pc) {
    case 0:  u->busy = 12; u->pc = 1; break;                       /* save a2-a4, getcoreid, rsil */
    case 1:  if (c == 1) { _lx_intr_livelock_app++; u->busy = 3; } else u->busy = 1; u->pc = 2; break;
    case 2:  _lx_intr_livelock_sync[c] = 1; u->busy = 3; u->pc = 3; break;
    case 3: u->sync0 = _lx_intr_livelock_sync[0]; u->busy = 1; u->pc = 23; break;
    case 23: u->sync1 = _lx_intr_livelock_sync[1]; u->busy = 1; u->pc = 24; break;
    case 24: u->busy = 3; u->pc = (u->sync0 && u->sync1) ? 4 : 3; break;   /* 1: ... beqz a2,1b */
    case 4:  if (c == 1 && _lx_intr_livelock_app == 2) { _lx_intr_livelock_counter++; u->busy = 4; } else u->busy = 1; u->pc = 5; break;
    case 5:  u->busy = P_DELAY + 4; u->pc = 6; break;              /* 1: rsr.ccount ... 2: bltu 2b */
    case 6:
        if (c == 1) { u->busy = 3; u->pc = (_lx_intr_livelock_app == 2) ? 8 : 9; }
        else {
            _lx_intr_livelock_pro++; u->busy = 10;                                /* 2: pro++ ; read syncs */
            if (_lx_intr_livelock_sync[0] && _lx_intr_livelock_sync[1]) u->pc = 5;                    /* both set -> j 1b (delay) */
            else if (_lx_intr_livelock_pro >= 2) u->pc = 7;                       /* 5: bgei a4,2,4f */
            else u->pc = 5;
        }
        break;
    case 7:  app_mapped = true; u->busy = P_APB + 3; u->pc = 10; break;   /* 4: intr_matrix_map */
    case 10: u->sync0 = _lx_intr_livelock_sync[0]; u->busy = 1; u->pc = 25; break;
    case 25: u->sync1 = _lx_intr_livelock_sync[1]; u->busy = 1; u->pc = 26; break;
    case 26: u->busy = 3; u->pc = (u->sync0 && u->sync1) ? 11 : 10; break;    /* wait App cpu re-entry */
    case 11: wp_key = WKEY; TR("  CPU%d handler: WPROTECT open (clr)", c); u->busy = P_APB + 2; u->pc = 12; break;
    case 12: u->busy = P_APB + 1; u->pc = 13; break;                      /* l32i INT_CLR */
    case 13: int_raw = false; TR("  CPU%d handler: INT_CLR", c); u->busy = P_APB + 2; u->pc = 14; break;
    case 14: wp_key = 0; TR("  CPU%d handler: WPROTECT close (clr)", c); u->busy = P_APB + 2; u->pc = 20; break;
    case 8:  wp_key = WKEY; TR("  CPU%d handler: WPROTECT open (feed)", c); u->busy = P_APB + 2; u->pc = 15; break;
    case 15: u->tmp_max = _lx_intr_livelock_max; TR("  CPU%d handler: read max=%u", c, u->tmp_max); u->busy = 3; u->pc = 16; break;
    case 16: TR("  CPU%d handler: stage0=%u%s", c, 1600/(u->tmp_max+1), WP_OPEN?"":" BLOCKED"); if (WP_OPEN) hw_stage0 = 1600 / (u->tmp_max + 1); u->busy = P_APB + 8; u->pc = 17; break;
    case 17: TR("  CPU%d handler: stage1=3200%s", c, WP_OPEN?"":" BLOCKED"); if (WP_OPEN) hw_stage1 = 3200; u->busy = P_APB + 2; u->pc = 18; break;
    case 18: TR("  CPU%d handler: FEED%s", c, WP_OPEN?"":" BLOCKED"); if (WP_OPEN) { wdt_cnt = 0; active_stage = 0; stage0_fired = false; if (cyc - last_feed > max_feed_gap) max_feed_gap = cyc - last_feed; last_feed = cyc; } u->busy = P_APB + 2; u->pc = 19; break;
    case 19: wp_key = 0; TR("  CPU%d handler: WPROTECT close (feed)", c); u->busy = P_APB + 2; u->pc = 20; break;
    case 9:  app_mapped = false; u->busy = P_APB + 3; u->pc = 20; break;  /* 3: unmap self */
    case 20:                                                              /* 9: */
        if (c == 1 && _lx_intr_livelock_app == 2) _lx_intr_livelock_app = 0;
        if (c == 0) _lx_intr_livelock_pro = 0;
        u->busy = 3; u->pc = 22; break;
    case 22: _lx_intr_livelock_sync[c] = 0; u->busy = 3; u->pc = 21; break;
    case 21: u->in_h = false; u->level = u->saved_level; u->busy = 10; u->pc = 0; TR("  CPU%d handler: rfi", c); break;
    }
    if (c == 1 && before == P_STALL_PC && before != u->pc) { u->busy += P_STALL_LEN; TR("  CPU1 handler: STALL %u after pc%d", P_STALL_LEN, before); }
    if (TRACE && before != u->pc) TR("  CPU%d handler pc%d->pc%d  (stage0=%u int_raw=%d wp=%s sync=%u,%u app=%u pro=%u max=%u)", c, before, u->pc, hw_stage0, int_raw, WP_OPEN?"open":"closed", _lx_intr_livelock_sync[0], _lx_intr_livelock_sync[1], _lx_intr_livelock_app, _lx_intr_livelock_pro, _lx_intr_livelock_max);
}

static bool mapped(int c) { return c == 0 ? true : app_mapped; }

static void try_deliver(int c)
{
    cpu_t *u = &cpu[c];
    if (u->in_h || !int_raw || !mapped(c) || u->level >= 4) return;
    if (c != our_core && OTHER_HUNG) return;
    if (!(_lx_intr_livelock_counter < _lx_intr_livelock_max)) {       /* bltu a0,a5 fails -> panic */
        panic_core = c; panic_stage0 = hw_stage0; panic_max = _lx_intr_livelock_max;
        panic_counter = _lx_intr_livelock_counter;
        snprintf(bad_reason, sizeof bad_reason, "CPU%d counter=%u max=%u", c, panic_counter, panic_max);
        finish(R_PANIC); return;
    }
    entries[c]++; TR("  CPU%d ENTER handler (level was %d, counter=%u max=%u)", c, u->level, _lx_intr_livelock_counter, _lx_intr_livelock_max);
    u->in_h = true; u->saved_level = u->level; u->level = 5; u->pc = 0; u->busy = 0;
}

static void tick_fn(void);

static void core_cycle(int c)
{
    cpu_t *u = &cpu[c];
    if (!u->in_h) try_deliver(c);
    if (outcome != R_RUNNING) return;
    if (u->in_h) { if (u->busy) { u->busy--; return; } h_op(c); return; }
    if (tick_req[c] && u->level == 0 && !(c != our_core && OTHER_HUNG)) { tick_req[c] = false; act_push(c, tick_fn, 1, "tick ISR"); }
    if (!nast[c]) return;
    act_t *a = astack[c][nast[c] - 1];
    if (a->busy) { a->busy--; if (a->busy) return; }
    resume(a);
    if (a->done) { nast[c]--; u->level = a->saved_level; TR("  CPU%d: %s done (level %d)", c, a->name, u->level); }
}

static void timer_step(void)
{
    wdt_cnt++;
    if (active_stage == 0 && wdt_cnt >= hw_stage0 * TICK) {
        if (DIR == 1 && first_feed == 0 && hw_stage0 == 1600 && _lx_intr_livelock_max == 0) initial_plain_expired = true;
        active_stage = 1; wdt_cnt = 0; stage0_fired = true; int_raw = true;
        TR("  WDT stage0 EXPIRED (stage0=%u ticks)", hw_stage0);
    } else if (active_stage == 1 && wdt_cnt >= hw_stage1 * TICK) {
        snprintf(bad_reason, sizeof bad_reason, "stage1"); finish(R_RESET);
    }
}

/* Invariant, evaluated after every cycle:
 *  I1 "short stage implies handler budget": !(stage0 != 1600 && max == 0).
 *     Count violating cycles and the smallest distance to expiry while violated.
 *  I2 "a pending expiry must be survivable": !(INT_RAW && counter >= max).
 *  I3 stage1 == 3200 always. */
static void invariant_check(void)
{
    if (hw_stage0 != 1600 && _lx_intr_livelock_max == 0) {
        viol_cycles++;
        long margin = (long)hw_stage0 * (long)TICK - (long)wdt_cnt;
        if (margin < viol_min_margin) viol_min_margin = margin;
        if (int_raw) viol_pending++;
    }
    if (int_raw && !(_lx_intr_livelock_counter < _lx_intr_livelock_max)) latent_cycles++;
    if (hw_stage1 != 3200) stage1_bad++;
}

static long tick_at = NOTICK_SENTINEL; static bool tick_fired;
static void world_cycle(void)
{
    cyc++; if (cyc > deadline) { snprintf(bad_reason, sizeof bad_reason, "model deadline"); finish(R_DEADLOCK); return; }
    if (!tick_fired && tick_at != NOTICK_SENTINEL && (long)(cyc - t0) >= tick_at) { P_TICKS++; tick_fired = P_TICKS >= P_TICK_COUNT; if (!tick_fired) tick_at += P_TICK_PERIOD; tick_req[0] = true; if (P_TICK_COUNT > 1 && !OTHER_HUNG) tick_req[1] = true; TR("  tick ISR requested"); }
    timer_step(); if (outcome != R_RUNNING) return;
    core_cycle(P_ORDER ? our_core : 1 - our_core); if (outcome != R_RUNNING) return;
    core_cycle(P_ORDER ? 1 - our_core : our_core);     if (outcome != R_RUNNING) return;
    invariant_check();
}
static void idle(unsigned n) { while (n-- && outcome == R_RUNNING) world_cycle(); }

/* ---------------- stubs seen by the real C ---------------- */
static void flue_iwdt_observe_barrier(void) { advance(1); }
static uint32_t shared_load(volatile uint32_t *p) { uint32_t v = *p; advance(2); return v; }
static void shared_store(volatile uint32_t *p, uint32_t v) { *p = v; advance(2); }
static bool soc_has_cache_lock_bug(void) { advance(P_EFUSE); return true; }
static unsigned esp_cpu_get_core_id(void) { return me(); }
static uint32_t esp_cpu_get_cycle_count(void) { advance(1); return (uint32_t)cyc; }
static void portENTER_CRITICAL_SAFE(int *l)
{
    cur->crit_saved = cpu[me()].level; if (cpu[me()].level < 3) cpu[me()].level = 3;
    while (*l) advance(4);                       /* spin on the other context's lock */
    *l = 1; advance(16); TR("C[%s]: lock taken", cur->name);   /* S32C1I: test-and-set is atomic */
}
static void portEXIT_CRITICAL_SAFE(int *l)  { assert(*l); advance(15); *l = 0; cpu[me()].level = cur->crit_saved; TR("C[%s]: lock released", cur->name); }
static void wdt_hal_write_protect_disable(wdt_hal_context_t *x) { (void)x; advance(6); wp_key = WKEY; TR("C[%s]: WPROTECT open", cur->name); advance(P_APB); }
static void wdt_hal_write_protect_enable(wdt_hal_context_t *x)  { (void)x; advance(4); wp_key = 0; TR("C[%s]: WPROTECT close", cur->name); advance(P_APB); }
static void wdt_hal_config_stage(wdt_hal_context_t *x, int st, uint32_t ticks, int act)
{
    (void)x; (void)act; advance(10);
    if (WP_OPEN) { if (st == 0) hw_stage0 = ticks; else hw_stage1 = ticks; TR("C[%s]: stage%d=%u", cur->name, st, ticks); } else { blocked_c_writes++; TR("C[%s]: stage%d=%u BLOCKED (WPROTECT closed)", cur->name, st, ticks); }
    advance(P_APB); advance(P_APB);                                    /* timeout reg + action bits */
}
static void wdt_hal_feed(wdt_hal_context_t *x)
{
    (void)x; advance(4);
    if (WP_OPEN) { wdt_cnt = 0; active_stage = 0; stage0_fired = false; c_feeds++; if (!first_feed) first_feed = cyc; if (cyc - last_feed > max_feed_gap) max_feed_gap = cyc - last_feed; last_feed = cyc; TR("C[%s]: FEED", cur->name); }
    else { blocked_c_writes++; TR("C[%s]: FEED BLOCKED", cur->name); }
    advance(P_APB);
}
static unsigned flue_iwdt_mask_high_interrupts(void) { advance(2); unsigned o = cpu[me()].level; cpu[me()].level = 5; TR("C[%s]: rsil 5", cur->name); return o; }
static void flue_iwdt_restore_high_interrupts(unsigned o) { cpu[me()].level = o; TR("C[%s]: PS restored", cur->name); advance(3); }
static bool flue_iwdt_interrupt_pending(void) { assert(cpu[me()].level == 5); advance(P_APB + 1); TR("C[%s]: read INT_RAW=%d", cur->name, int_raw); return int_raw; }
static uint32_t flue_iwdt_stage0_ticks(void)  { assert(cpu[me()].level == 5); advance(P_APB + 1); TR("C[%s]: read stage0=%u", cur->name, hw_stage0); return hw_stage0; }
static uint32_t flue_iwdt_stage1_ticks(void)  { assert(cpu[me()].level == 5); advance(P_APB + 1); TR("C[%s]: read stage1=%u", cur->name, hw_stage1); return hw_stage1; }
static bool flue_iwdt_write_protect_is_open(void) { assert(cpu[me()].level == 5); advance(P_APB + 1); TR("C[%s]: read WPROTECT=%s", cur->name, WP_OPEN?"open":"closed"); return WP_OPEN; }
#define abort() do { snprintf(bad_reason, sizeof bad_reason, "abort() in C"); finish(R_ABORT); } while (0)
void esp_int_wdt_reconfigure_ticks(uint32_t, uint32_t);
void esp_int_wdt_set_livelock_mode(bool);
'''

DRIVER = r'''
#undef abort
static void transition_fn(void) { TRANSITION_CALL; }
static void tick_fn(void) { TICK_CALL; }

static void reset_world(int core, int dir)
{
    P_TICKS = 0; initial_plain_expired = false; cyc = 0; t0 = 0; active_stage = 0; wdt_cnt = 0; hw_stage1 = 3200; wp_key = 0; int_raw = false; stage0_fired = false;
    app_mapped = true; _lx_intr_livelock_sync[0] = _lx_intr_livelock_sync[1] = 0; _lx_intr_livelock_app = _lx_intr_livelock_pro = 0; tick_req[0] = tick_req[1] = false; tick_fired = false;
    memset(cpu, 0, sizeof cpu); our_core = core; cpu[core].level = 3; cpu[1 - core].level = 0;
    nacts = 0; nast[0] = nast[1] = 0; cur = NULL;
    DIR = dir;
    if (dir == 0) { hw_stage0 = 40;   _lx_intr_livelock_counter = P_COUNTER; _lx_intr_livelock_max = 39; }
    else          { hw_stage0 = 1600; _lx_intr_livelock_counter = 0; _lx_intr_livelock_max = 0; }
    s_iwdt_configure_lock = 0; int_wdt_cpu1_ticked = true;
    entries[0] = entries[1] = 0; blocked_c_writes = 0; outcome = R_RUNNING; bad_reason[0] = 0;
    last_feed = 0; max_feed_gap = 0; first_feed = 0; c_feeds = 0;
    viol_cycles = viol_pending = latent_cycles = stage1_bad = 0; viol_min_margin = 0x7fffffffL;
    deadline = 4000000;
    RESET_VARIANT_STATE
}

/* expiry_offset > 0: stage0 expires that many cycles AFTER the transition starts.
   expiry_offset < 0: it expired that many cycles BEFORE (handler may be mid-flight).
   tick_offset: FreeRTOS tick ISR requested on CPU0 at that offset (NOTICK_SENTINEL: never). */
static int run_one(int core, int dir, long expiry_offset, long tick_offset, unsigned *len_out)
{
    reset_world(core, dir);
    uint32_t init_stage = hw_stage0;
    tick_at = tick_offset;
    if (expiry_offset == NOEXP_SENTINEL) { wdt_cnt = 0; }
    else if (expiry_offset >= 0) wdt_cnt = init_stage * TICK - (uint32_t)expiry_offset;
    else { wdt_cnt = init_stage * TICK - 1; t0 = (uint64_t)(-expiry_offset); idle((unsigned)(-expiry_offset)); }
    if (outcome != R_RUNNING) return outcome;
    uint64_t start = cyc;
    act_t *tr = act_push(core, transition_fn, 3, "transition");
    while (!tr->done && outcome == R_RUNNING) world_cycle();
    if (outcome != R_RUNNING) return outcome;
    if (len_out) *len_out = (unsigned)(cyc - start);
    idle(POST_IDLE + P_STALL_LEN);
    /* let a late tick ISR / handler round / stalled handler finish before judging the final state */
    while (outcome == R_RUNNING && (nast[0] || nast[1] || cpu[0].in_h || cpu[1].in_h
           || (tick_at != NOTICK_SENTINEL && !tick_fired && core == 1))) world_cycle();
    if (outcome == R_RUNNING) idle(2000);
    if (outcome == R_RUNNING && core == 0 && (tick_req[0] || nast[0] || !tick_fired)) {
        /* sleep code releases its critical section (both directions) -> the deferred tick runs now */
        if (!tick_fired && tick_at != NOTICK_SENTINEL) { tick_fired = true; tick_req[0] = true; }
        cpu[0].level = 0;
        while (outcome == R_RUNNING && (tick_req[0] || nast[0])) world_cycle();
        idle(2000);
    }
    if (outcome != R_RUNNING) return outcome;
    if (expiry_offset == NOEXP_SENTINEL && tick_offset == NOTICK_SENTINEL) return R_OK;
    uint32_t want_stage0 = dir ? 40 : 1600, want_max = dir ? 39 : 0;
    const char *why = NULL;
    if (hw_stage0 != want_stage0) why = "stage0";
    else if (_lx_intr_livelock_max != want_max) why = "max";
    else if (hw_stage1 != 3200) why = "stage1";
    else if (int_raw) why = "INT_RAW pending";
    else if (cpu[0].in_h || cpu[1].in_h) why = "core still in handler";
    else if (WP_OPEN) why = "WPROTECT left open";
    else if (s_iwdt_configure_lock) why = "lock held";
    else if (nast[0] || nast[1]) why = "C activity unfinished";
    if (why) { snprintf(bad_reason, sizeof bad_reason, "%s", why); finish(R_BADFINAL); return outcome; }
    if (dir == 1) {
        /* provoke the next expiry: the committed livelock mode must survive one full handler round */
        wdt_cnt = hw_stage0 * TICK - 1; stage0_fired = false;
        idle(3 * P_DELAY + 8000);
        if (outcome != R_RUNNING) return outcome;
        if (cpu[0].in_h || cpu[1].in_h || int_raw) { snprintf(bad_reason, sizeof bad_reason, "post-commit handler round incomplete"); finish(R_BADFINAL); return outcome; }
    }
    return R_OK;
}

static long arg(int argc, char **argv, const char *k, long dflt)
{
    size_t n = strlen(k);
    for (int i = 1; i < argc; i++) if (!strncmp(argv[i], k, n) && argv[i][n] == '=') return atol(argv[i] + n + 1);
    return dflt;
}

int main(int argc, char **argv)
{
    P_ORDER = arg(argc, argv, "order", 0); P_COUNTER = arg(argc, argv, "counter", 0);
    P_TICK_PERIOD = arg(argc, argv, "tick_period", 5000); P_TICK_COUNT = arg(argc, argv, "tick_count", 1);
    P_APB = arg(argc, argv, "apb", 4); P_DELAY = arg(argc, argv, "delay", 2160); P_EFUSE = arg(argc, argv, "efuse", 60);
    P_STALL_PC = arg(argc, argv, "stall_pc", -1); P_STALL_LEN = arg(argc, argv, "stall_len", 0);
    TICK = arg(argc, argv, "tick", 500); int core = arg(argc, argv, "core", 0); OTHER_HUNG = arg(argc, argv, "hung", 0);
    int dir = arg(argc, argv, "dir", 0);
    long trace_exp = arg(argc, argv, "trace_exp", NOEXP_SENTINEL + 1), trace_tick = arg(argc, argv, "trace_tick", NOTICK_SENTINEL);
    if (trace_exp != NOEXP_SENTINEL + 1) { TRACE = true; int r = run_one(core, dir, trace_exp, trace_tick, NULL); if (r == R_OK) fprintf(stderr, "== ok\n"); printf("{\"outcome\":\"%s\"}\n", RNAME[r]); return 0; }
    reset_world(core, dir);
    hw_stage0 = 40; hw_stage1 = 3200; wdt_cnt = 40 * TICK - 1;
    timer_step(); assert(active_stage == 1 && wdt_cnt == 0);
    hw_stage0 = 1600; wdt_cnt = 3200 * TICK - 1;
    timer_step(); assert(outcome == R_RESET); /* changing stage0 must not extend stage1 */
    unsigned len = 0;
    run_one(core, dir, NOEXP_SENTINEL, NOTICK_SENTINEL, &len);
    uint64_t ff = first_feed;
    long exp_from = arg(argc, argv, "exp_from", -(3 * (long)P_DELAY + 4000)), exp_to = arg(argc, argv, "exp_to", (long)len + 2000), exp_step = arg(argc, argv, "exp_step", 1);
    long tick_from = arg(argc, argv, "tick_from", NOTICK_SENTINEL), tick_to = arg(argc, argv, "tick_to", NOTICK_SENTINEL), tick_step = arg(argc, argv, "tick_step", 1);
    if (arg(argc, argv, "exp_none", 0)) exp_from = exp_to = NOEXP_SENTINEL;
    unsigned counts[R_N] = {0}; long first_bad[R_N][2]; for (int i = 0; i < R_N; i++) first_bad[i][0] = first_bad[i][1] = 0x7fffffffL;
    unsigned max_entries = 0, any_c_blocked = 0, pre_feed_panic = 0, runs = 0;
    uint64_t v_max = 0, vp_max = 0, lat_max = 0, s1_max = 0, gap_max = 0; long v_margin = 0x7fffffffL;
    char reasons[1024] = ""; unsigned nreasons = 0;
    for (long off = exp_from; off <= exp_to; off += (exp_from == NOEXP_SENTINEL ? 1 : exp_step)) {
        for (long tk = tick_from; tk <= tick_to; tk += (tick_from == NOTICK_SENTINEL ? 1 : tick_step)) {
            int r = run_one(core, dir, off, tk, NULL); runs++;
            counts[r]++; if (first_bad[r][0] == 0x7fffffffL) { first_bad[r][0] = off; first_bad[r][1] = tk; }
            if (entries[0] + entries[1] > max_entries) max_entries = entries[0] + entries[1];
            if (blocked_c_writes) any_c_blocked++;
            if (viol_cycles > v_max) v_max = viol_cycles; if (viol_pending > vp_max) vp_max = viol_pending;
            if (viol_cycles && viol_min_margin < v_margin) v_margin = viol_min_margin;
            if (latent_cycles > lat_max) lat_max = latent_cycles; if (stage1_bad > s1_max) s1_max = stage1_bad;
            if (max_feed_gap > gap_max) gap_max = max_feed_gap;
            if (r == R_PANIC && initial_plain_expired) pre_feed_panic++;   /* expiry before/at our first feed: real IWDT timeout, inherent */
            if (r != R_OK && nreasons < 6 && !strstr(reasons, bad_reason)) { nreasons++; strncat(reasons, bad_reason, sizeof reasons - strlen(reasons) - 3); strcat(reasons, "; "); }
            if (r == R_PANIC && counts[r] == 1)
                fprintf(stderr, "  first PANIC at exp=%ld tick=%ld on CPU%u: stage0=%u max=%u counter=%u\n", off, tk, panic_core, panic_stage0, panic_max, panic_counter);
        }
    }
    printf("{\"len\":%u,\"first_feed\":%llu,\"runs\":%u,\"ok\":%u,\"panic\":%u,\"reset\":%u,\"deadlock\":%u,\"abort\":%u,\"bad_final\":%u,"
           "\"pre_feed_panic\":%u,\"first_panic\":[%ld,%ld],\"first_bad_final\":[%ld,%ld],\"first_abort\":[%ld,%ld],\"first_deadlock\":[%ld,%ld],"
           "\"max_handler_entries\":%u,\"runs_with_blocked_c_writes\":%u,"
           "\"viol_cycles_max\":%llu,\"viol_pending_max\":%llu,\"viol_min_margin\":%ld,\"latent_max\":%llu,\"stage1_bad_max\":%llu,\"max_feed_gap\":%llu,\"reasons\":\"%s\"}\n",
           len, (unsigned long long)ff, runs, counts[0], counts[1], counts[2], counts[3], counts[4], counts[5], pre_feed_panic,
           first_bad[1][0], first_bad[1][1], first_bad[5][0], first_bad[5][1], first_bad[4][0], first_bad[4][1], first_bad[3][0], first_bad[3][1],
           max_entries, any_c_blocked, (unsigned long long)v_max, (unsigned long long)vp_max, v_max ? v_margin : 0,
           (unsigned long long)lat_max, (unsigned long long)s1_max, (unsigned long long)gap_max, reasons);
    return 0;
}
'''


def build(variant, settle, outdir, proposal_inc=None):
    """variant: 'sdk' | 'deployed' | 'proposal'.  Returns the executable path."""
    gen = outdir / 'generated'
    generate(SDK, gen)
    original_helper = (SDK / 'components/esp_system/port/soc/esp32/eco3_livelock_workaround.c').read_text()
    original_wdt = (SDK / 'components/esp_system/int_wdt.c').read_text()
    generated = (gen / 'int_wdt.c').read_text()
    harness = HARNESS.replace('NOTICK_SENTINEL', str(NOTICK)).replace('NOEXP_SENTINEL', str(NOEXP))
    parts = [harness]
    parts += [function(original_helper, n) for n in ['esp_int_wdt_reset_livelock_params', 'esp_int_wdt_set_livelock_params',
                                                      'esp_int_wdt_livelock_get_feed_stage0_ticks']]
    parts += [function(generated, n) for n in ['reconfigure_ticks', 'esp_int_wdt_reconfigure_ticks']]
    if variant == 'sdk':
        parts.append(function(original_helper, 'esp_int_wdt_livelock_workaround'))
        parts.append(function(original_wdt, 'tick_hook'))
        call, state = 'esp_int_wdt_livelock_workaround(DIR)', ''
    elif variant == 'deployed':
        parts.append((HERE / 'deployed_iwdt_transition.c.inc').read_text())
        parts.append(function(generated, 'tick_hook').replace('flue_iwdt_tick();', 'flue_iwdt_update(false, true);'))
        call, state = 'esp_int_wdt_set_livelock_mode(DIR)', 's_flue_livelock_enabled = (dir == 0);'
    else:
        name = {'proposal': 'proposal_iwdt_transition.c.inc', 'v2settle': 'proposal_v2_settle.c.inc'}[variant]
        inc = Path(proposal_inc or (PROJECT / 'cmake/iwdt_transition.c.inc' if variant == 'proposal' else HERE / name)).read_text()
        parts.append(f'#define FLUE_IWDT_SETTLE_CYCLES {settle}u\n' + inc)
        parts.append(function(generated, 'tick_hook').replace('flue_iwdt_update(false, true);', 'flue_iwdt_tick();'))
        call, state = 'esp_int_wdt_set_livelock_mode(DIR)', 's_flue_livelock_enabled = (dir == 0);'
    drv = (DRIVER.replace('TRANSITION_CALL', call).replace('TICK_CALL', 'tick_hook()')
           .replace('RESET_VARIANT_STATE', state).replace('POST_IDLE', '12000')
           .replace('NOTICK_SENTINEL', str(NOTICK)).replace('NOEXP_SENTINEL', str(NOEXP)))
    for i in range(1, len(parts)):
        part = parts[i]
        for symbol in ['_lx_intr_livelock_counter', '_lx_intr_livelock_max',
                       '_lx_intr_livelock_app', '_lx_intr_livelock_pro',
                       '_lx_intr_livelock_sync[0]', '_lx_intr_livelock_sync[1]']:
            # declarations remain untouched; convert expressions/statements.
            pattern = re.escape(symbol)
            part = re.sub(pattern + r' = ([^;]+);', lambda m: 'shared_store(&' + symbol + ', ' + m[1] + ');', part)
            part = re.sub(pattern + r'(?= ==| \+| <| /)', 'shared_load(&' + symbol + ')', part)
        parts[i] = part
    src = outdir / f'{variant}_{settle}.c'
    src.write_text('\n'.join(parts) + drv)
    exe = outdir / f'{variant}_{settle}'
    subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Wno-unused-function', '-Wno-unused-parameter',
                    '-Wno-deprecated-declarations', str(src), '-o', str(exe)], check=True)
    return exe


def run(exe, **kw):
    p = subprocess.run([str(exe)] + [f'{k}={v}' for k, v in kw.items()], capture_output=True, text=True, check=True)
    d = json.loads(p.stdout)
    d['stderr'] = p.stderr.strip()
    return d


def healthy(r, hung=False, dir=0):
    # Timeout scenarios need their own explicit oracle; never silently accept resets.
    if hung:
        return r['reset'] == r['runs'] and r['viol_cycles_max'] == 0
    return (r['ok'] == r['runs'] and r['viol_cycles_max'] == 0
            and r['stage1_bad_max'] == 0)


def main():
    outdir = HERE / 'model-build'
    outdir.mkdir(exist_ok=True)
    variants = [('sdk', 0), ('deployed', 0), ('v2settle', 0), ('v2settle', 8000), ('proposal', 0)]
    exes = {v: build(*v, outdir) for v in variants}
    results = []
    log = open(HERE / 'model-run.log', 'w')
    lock = __import__('threading').Lock()
    t_start = time.time()

    def go(label, name, settle, **kw):
        exe = exes[(name, settle)]
        params = dict(apb=4, delay=2160, efuse=60, stall_pc=-1, stall_len=0, tick=500, core=0, hung=0, dir=0)
        params.update(kw)
        r = run(exe, **params)
        r.update(variant=name, settle=settle, label=label, **params)
        ok = healthy(r, hung=bool(params['hung']), dir=params['dir'])
        r['healthy'] = ok
        line = (f"[{label}] {name:8s} settle={settle:5d} dir={params['dir']} core={params['core']} apb={params['apb']:2d} delay={params['delay']:4d} "
                f"stall={params['stall_pc']:>2}/{params['stall_len']:<5d} hung={params['hung']} len={r['len']:6d} runs={r['runs']:7d} ok={r['ok']:7d} "
                f"panic={r['panic']:5d}(pre={r['pre_feed_panic']}) reset={r['reset']:4d} badfinal={r['bad_final']:5d} dead={r['deadlock']} abort={r['abort']:5d} "
                f"viol={r['viol_cycles_max']}/{r['viol_min_margin']} latent={r['latent_max']} gap={r['max_feed_gap']} cblk={r['runs_with_blocked_c_writes']}"
                f"{'' if ok else '  <-- FAIL'} {r['reasons']}")
        with lock:
            results.append(r)
            print(f'{time.time() - t_start:7.0f}s {line}', flush=True)
            log.write(line + '\n')
            if r['stderr']:
                log.write('    ' + r['stderr'].replace('\n', '\n    ') + '\n')
            log.flush()

    jobs = []
    # A. expiry sweep, both directions, both cores, no tick
    for (name, settle) in variants:
        for apb, delay, dir, core in itertools.product([4, 10], [480, 2160], [0, 1], [0, 1]):
            jobs.append(('grid', name, settle, dict(apb=apb, delay=delay, dir=dir, core=core)))
    # B. stall at each step of CPU1's handler (transition on CPU0, dir=0), lengths up to beyond settle+commit
    for (name, settle) in [('sdk', 0), ('deployed', 0), ('v2settle', 8000), ('proposal', 0)]:
        for pc in [2, 3, 5, 8, 15, 16, 17, 18, 19, 20]:
            for ln in [40, 500, 2500, 6000, 8500, 9500, 12000, 20000]:
                jobs.append(('stall', name, settle, dict(stall_pc=pc, stall_len=ln, core=0, dir=0, **({'exp_step': 40} if pc in (2, 3) else {}))))
    # B'. same with the transition on CPU1 (stalls then also delay our own C)
    for (name, settle) in [('deployed', 0), ('v2settle', 8000), ('proposal', 0)]:
        for pc in [15, 16, 18, 19]:
            for ln in [500, 8500, 12000]:
                jobs.append(('stall1', name, settle, dict(stall_pc=pc, stall_len=ln, core=1, dir=0)))
    # C. tick ISR on CPU0 at every offset, no expiry
    for (name, settle) in variants:
        for dir, core in itertools.product([0, 1], [0, 1]):
            jobs.append(('tick', name, settle, dict(dir=dir, core=core, exp_none=1, tick_from=-3000, tick_to=40000)))
    # D. tick x expiry (transition on CPU1 so the tick really runs concurrently on CPU0)
    for (name, settle) in [('sdk', 0), ('deployed', 0), ('v2settle', 8000), ('proposal', 0)]:
        for dir in (0, 1):
            jobs.append(('tick+exp', name, settle, dict(dir=dir, core=1, exp_step=5, tick_from=-2500, tick_to=24000, tick_step=151)))
    # E. other core genuinely hung
    for (name, settle) in [('deployed', 0), ('v2settle', 8000), ('proposal', 0)]:
        for core in (0, 1):
            jobs.append(('hung', name, settle, dict(core=core, hung=1)))
    # F. sync-miss probe (stall at pc2), both directions of the old finding
    for ln in [36, 40, 60]:
        for (name, settle) in [('sdk', 0), ('deployed', 0), ('v2settle', 8000), ('proposal', 0)]:
            for apb in (4, 10):
                jobs.append(('syncmiss', name, settle, dict(stall_pc=2, stall_len=ln, apb=apb, exp_step=40)))

    print(f'{len(jobs)} jobs', flush=True)
    with ThreadPoolExecutor(max_workers=int(os.environ.get('JOBS', '8'))) as ex:
        list(ex.map(lambda j: go(j[0], j[1], j[2], **j[3]), jobs))
    (HERE / 'model-results.json').write_text(json.dumps(results, indent=1))
    print('wrote', HERE / 'model-results.json', f'in {time.time() - t_start:.0f}s')


if __name__ == '__main__':
    main()
