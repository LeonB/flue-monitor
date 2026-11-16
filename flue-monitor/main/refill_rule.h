#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef struct {
  bool armed, sampled;
  float peak;
  int64_t last_ms, rising_since_ms, falling_since_ms;
} refill_rule_t;

void refill_rule_reset(refill_rule_t *rule);
// Called on real, fresh ten-second samples. Returns once per heat/cool cycle.
bool refill_rule_sample(refill_rule_t *rule, int64_t now_ms, bool valid,
                        float temperature, float rate, float threshold);
bool refill_quiet_minute(int minute, int start, int end);

// Netherlands civil time (EU summer-time rule); input and expiry remain UTC.
int refill_local_minute(int64_t utc);
int64_t refill_next_quiet_end(int64_t utc, int end_minute);
