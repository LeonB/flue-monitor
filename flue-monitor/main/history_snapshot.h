#pragma once
#include <math.h>
#include <stdint.h>
#include <string.h>
#include "sensors.h"

#define HISTORY_SNAPSHOT_VERSION 2
#define HISTORY_EVENT_CAPACITY 64

typedef struct {
  uint32_t age_s, event_id;
} history_saved_event_t;

typedef struct {
  int64_t saved_at;
  uint32_t version, sample_count, event_count, elapsed_s;
  // uptime_s stores an age in this transfer representation, not a boot time.
  history_sample_t samples[SENSORS_HISTORY_CAPACITY];
  history_saved_event_t events[HISTORY_EVENT_CAPACITY];
} history_snapshot_t;

_Static_assert(sizeof(history_sample_t) == 16 && offsetof(history_snapshot_t, samples) == 24 &&
               sizeof(history_snapshot_t) == 6296, "Versioned history snapshot wire layout changed");

static bool history_snapshot_valid(const history_snapshot_t *saved, size_t event_types) {
  if (saved->version != HISTORY_SNAPSHOT_VERSION ||
      saved->sample_count > SENSORS_HISTORY_CAPACITY || saved->event_count > HISTORY_EVENT_CAPACITY) return false;
  for (size_t i = 0; i < saved->sample_count; i++) {
    const history_sample_t *s = &saved->samples[i];
    if (!isfinite(s->thermocouple_c) || s->thermocouple_c < -40 || s->thermocouple_c > 600 ||
        !isfinite(s->thermocouple_rate_c_per_min) ||
        s->thermocouple_zone < THERMOCOUPLE_ZONE_COLD || s->thermocouple_zone > THERMOCOUPLE_ZONE_HOT ||
        (i && s->uptime_s > saved->samples[i-1].uptime_s)) return false;
  }
  for (size_t i = 0; i < saved->event_count; i++)
    if (saved->events[i].event_id >= event_types ||
        (i && saved->events[i].age_s > saved->events[i-1].age_s)) return false;
  return true;
}

// Unsigned subtraction represents pre-boot samples. The Mac supplies elapsed
// time, so this also works before NTP sync and with later clock corrections.
static bool history_snapshot_rebase(history_snapshot_t *saved, uint32_t uptime) {
  uint32_t elapsed = saved->elapsed_s;
  for (size_t i = 0; i < saved->sample_count; i++)
    if (saved->samples[i].uptime_s > UINT32_MAX - elapsed) return false;
  for (size_t i = 0; i < saved->event_count; i++)
    if (saved->events[i].age_s > UINT32_MAX - elapsed) return false;
  for (size_t i = 0; i < saved->sample_count; i++)
    saved->samples[i].uptime_s = uptime - saved->samples[i].uptime_s - elapsed;
  for (size_t i = 0; i < saved->event_count; i++) saved->events[i].age_s += elapsed;
  return true;
}
