#include "refill_rule.h"
#include <math.h>
#include <time.h>
#include <string.h>

void refill_rule_reset(refill_rule_t *rule) {
  *rule = (refill_rule_t){ .rising_since_ms = -1, .falling_since_ms = -1,
                          .cold_since_ms = -1, .action_min = NAN };
}

void refill_rule_event(refill_rule_t *rule, const char *event, int64_t now_ms) {
  if (!strcmp(event, "stove_off")) { refill_rule_reset(rule); return; }
  if (strcmp(event, "added_wood") && strcmp(event, "cold_start")) return;
  float baseline = rule->sampled && now_ms >= rule->last_ms && now_ms - rule->last_ms <= 30000
    ? rule->last_temperature : NAN;
  int64_t last_sample = rule->last_ms;
  refill_rule_reset(rule);
  rule->session_active = rule->action_pending = true;
  rule->action_min = baseline;
  rule->action_ms = now_ms;
  rule->sampled = isfinite(baseline);
  rule->last_ms = last_sample;
  rule->last_temperature = baseline;
}

bool refill_rule_sample(refill_rule_t *rule, int64_t now_ms, bool valid,
                        float temperature, float rate, float threshold, float session_end) {
  if (!valid || !isfinite(temperature) || !isfinite(rate) || !isfinite(threshold) || !isfinite(session_end)) {
    refill_rule_reset(rule);
    return false;
  }
  if (rule->sampled && (now_ms <= rule->last_ms || now_ms - rule->last_ms > 30000))
    refill_rule_reset(rule);
  if (!rule->sampled && rule->action_pending &&
      (now_ms < rule->action_ms || now_ms - rule->action_ms > 30000))
    refill_rule_reset(rule);
  rule->sampled = true;
  rule->last_ms = now_ms;
  rule->last_temperature = temperature;
  if (rate >= 2.0f) {
    if (rule->rising_since_ms < 0) rule->rising_since_ms = now_ms;
  } else rule->rising_since_ms = -1;
  bool sustained = rule->rising_since_ms >= 0 && now_ms - rule->rising_since_ms >= 240000;
  if (temperature < session_end && !sustained) {
    if (rule->cold_since_ms < 0) rule->cold_since_ms = now_ms;
    if (now_ms - rule->cold_since_ms >= 1800000) {
      refill_rule_reset(rule);
      return false;
    }
  } else rule->cold_since_ms = -1;
  if (rule->action_pending && (!isfinite(rule->action_min) || temperature < rule->action_min))
    rule->action_min = temperature;
  // A logged start/refill supplies intent; an actual 20 C rise supplies evidence.
  if (!rule->armed && (sustained || (rule->action_pending && temperature - rule->action_min >= 20.0f))) {
    rule->armed = true;
    rule->session_active = true;
    rule->action_pending = false;
    rule->peak = temperature;
    rule->falling_since_ms = -1;
  }
  if (!rule->armed) return false;
  if (temperature > rule->peak) rule->peak = temperature;
  if (rate < 0.0f) {
    if (rule->falling_since_ms < 0) rule->falling_since_ms = now_ms;
  } else rule->falling_since_ms = -1;
  if (rule->falling_since_ms >= 0 && now_ms - rule->falling_since_ms >= 300000 &&
      rule->peak - temperature >= 20.0f && temperature <= threshold) {
    int64_t cold_since = rule->cold_since_ms;
    refill_rule_reset(rule);
    rule->cold_since_ms = cold_since;
    rule->session_active = true;
    rule->sampled = true;
    rule->last_ms = now_ms;
    rule->last_temperature = temperature;
    return true;
  }
  return false;
}

bool refill_quiet_minute(int minute, int start, int end) {
  return start < end ? minute >= start && minute < end : minute >= start || minute < end;
}

// Directive2000/84/EC: last Sunday of March/October, at01:00UTC. Avoid
// pulling the general TZ parser into the monitor's bounded OTA image.
int refill_local_minute(int64_t utc) {
  time_t epoch = utc;
  struct tm t;
  gmtime_r(&epoch, &t);
  bool summer = t.tm_mon > 2 && t.tm_mon < 9;
  int last_sunday = 31 - (t.tm_wday + 31 - t.tm_mday) % 7;
  if (t.tm_mon == 2) summer = t.tm_mday > last_sunday || (t.tm_mday == last_sunday && t.tm_hour >= 1);
  if (t.tm_mon == 9) summer = t.tm_mday < last_sunday || (t.tm_mday == last_sunday && t.tm_hour < 1);
  return (t.tm_hour * 60 + t.tm_min + (summer ? 120 : 60)) % 1440;
}

int64_t refill_next_quiet_end(int64_t utc, int end_minute) {
  int previous = refill_local_minute(utc);
  int64_t next = utc - utc % 60;
  // An action runs rarely. A bounded minute scan handles skipped/repeated
  // civil times without guessing a UTC offset for the next morning.
  for (int i = 0; i < 26 * 60; ++i) {
    next += 60;
    int minute = refill_local_minute(next);
    int advance = (minute - previous + 1440) % 1440;
    int distance = (end_minute - previous + 1440) % 1440;
    if (advance <= 61 && distance > 0 && distance <= advance) return next;
    previous = minute;
  }
  return utc; // Fail closed: never leave an unbounded quiet-hours override.
}
