#pragma once
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

// Parse a mutable Accept-Encoding value without depending on a transport.
static inline bool asset_encoding_accepts_gzip(char *encodings) {
  char *save = NULL;
  for (char *token = strtok_r(encodings, ",", &save); token; token = strtok_r(NULL, ",", &save)) {
    while (*token == ' ' || *token == '\t') token++;
    char *params = strchr(token, ';');
    if (params) *params++ = 0;
    char *end = token + strlen(token);
    while (end > token && (end[-1] == ' ' || end[-1] == '\t')) *--end = 0;
    if (strcasecmp(token, "gzip") != 0) continue;
    if (params) {
      while (*params == ' ' || *params == '\t') params++;
      if (strncasecmp(params, "q=", 2) == 0 && strtod(params + 2, NULL) <= 0) return false;
    }
    return true;
  }
  return false;
}
