#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <math.h>

#define BOSCH_REDIRECT "com.bosch.tt.dashtt.pointt://app/login"
// Strict resource identifiers prevent path/query injection into cloud requests.
static inline bool bosch_id_valid(const char *s) {
    size_t n = s ? strlen(s) : 0;
    if (!n || n > 63) return false;
    for (; *s; s++) if (!((*s >= '0' && *s <= '9') || (*s >= 'a' && *s <= 'z') ||
                          (*s >= 'A' && *s <= 'Z') || *s == '-' || *s == '_')) return false;
    return true;
}
static inline bool bosch_zone_valid(const char *s) {
    if (!s || strncmp(s, "zn", 2) || strlen(s) < 3 || strlen(s) > 6) return false;
    for (s += 2; *s; s++) if (*s < '0' || *s > '9') return false;
    return true;
}
static inline bool bosch_temperature_valid(double value) {
    return isfinite(value) && value >= -40 && value <= 60;
}
static inline int bosch_hex(char c) {
    return c >= '0' && c <= '9' ? c-'0' : c >= 'a' && c <= 'f' ? c-'a'+10 :
           c >= 'A' && c <= 'F' ? c-'A'+10 : -1;
}
static inline bool bosch_decode(const char *s, size_t n, char *out, size_t cap) {
    size_t pos = 0;
    for (size_t i = 0; i < n; i++) {
        unsigned char c = s[i];
        if (c == '%') {
            if (i+2 >= n || bosch_hex(s[i+1]) < 0 || bosch_hex(s[i+2]) < 0) return false;
            c = bosch_hex(s[i+1])*16 + bosch_hex(s[i+2]); i += 2;
        } else if (c == '+') c = ' ';
        if (c < 0x21 || c > 0x7e || pos+1 >= cap) return false;
        out[pos++] = c;
    }
    out[pos] = 0;
    return true;
}
static inline bool bosch_callback(const char *url, const char *expected, char *code, size_t cap) {
    size_t prefix = strlen(BOSCH_REDIRECT);
    if (!url || !*expected || strncmp(url, BOSCH_REDIRECT, prefix) || url[prefix] != '?' || strchr(url, '#')) return false;
    bool got_code = false, got_state = false;
    for (const char *p = url+prefix+1; *p;) {
        const char *end = strchr(p, '&'); if (!end) end = p+strlen(p);
        const char *eq = memchr(p, '=', end-p);
        if (!eq) return false;
        if (eq-p == 4 && !memcmp(p, "code", 4)) {
            if (got_code || !bosch_decode(eq+1, end-eq-1, code, cap) || !*code) return false;
            got_code = true;
        } else if (eq-p == 5 && !memcmp(p, "state", 5)) {
            char state[65];
            if (got_state || !bosch_decode(eq+1, end-eq-1, state, sizeof state) || strcmp(state, expected)) return false;
            got_state = true;
        } else if (eq-p == 5 && !memcmp(p, "error", 5)) return false;
        p = *end ? end+1 : end;
    }
    return got_code && got_state;
}
