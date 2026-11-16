#include "refill_rule.h"
#include <math.h>
#include <time.h>

void refill_rule_reset(refill_rule_t *rule) {
  *rule = (refill_rule_t){ .rising_since_ms = -1, .falling_since_ms = -1 };
}

bool refill_rule_sample(refill_rule_t *rule, int64_t now_ms, bool valid,
                        float temperature, float rate, float threshold) {
  if (!valid || !isfinite(temperature) || !isfinite(rate) || !isfinite(threshold)) {
    refill_rule_reset(rule);
    return false;
  }
  if (rule->sampled && (now_ms <= rule->last_ms || now_ms - rule->last_ms > 30000))
    refill_rule_reset(rule);
  rule->sampled = true;
  rule->last_ms = now_ms;
  if (rate >= 2.0f) {
    if (rule->rising_since_ms < 0) rule->rising_since_ms = now_ms;
  } else rule->rising_since_ms = -1;
  if (!rule->armed && rule->rising_since_ms >= 0 && now_ms - rule->rising_since_ms >= 240000) {
    rule->armed = true;
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
    refill_rule_reset(rule);
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
