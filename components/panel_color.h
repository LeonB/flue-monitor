#pragma once
#include <math.h>
#include <stdbool.h>
#include <stdint.h>

// CSS sRGB to linear PWM, or the previous experimental gamma curve.
// Gains operate in linear light; global brightness is applied only once.
static inline uint8_t panel_color_channel(float encoded, float brightness, bool srgb, float gain, float gamma) {
  float c = fminf(1.0f, fmaxf(0.0f, encoded / 255.0f));
  float linear = srgb ? (c <= 0.04045f ? c / 12.92f : powf((c + 0.055f) / 1.055f, 2.4f)) : powf(c, gamma);
  return (uint8_t)lroundf(fminf(255.0f, fmaxf(0.0f, linear * gain * brightness)));
}
