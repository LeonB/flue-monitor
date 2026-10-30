#!/bin/sh
# Activates the ESP-IDF v5.5.6 toolchain for this project. This selects the
# official 5.5.6 release installed alongside the prior SDK in the existing
# ESPHome tool cache (see CLAUDE.md).
#
# Usage: source this file, don't execute it, so the environment changes
# apply to your current shell:
#
#   . ./activate-idf.sh
#
# Every Claude Code Bash tool call runs in a fresh, non-persistent shell, so
# from that context this needs to be sourced within the *same* command as
# whatever idf.py invocation follows it, e.g.:
#
#   cd flue-monitor && . ./activate-idf.sh && idf.py build

export IDF_TOOLS_PATH="$HOME/Library/Caches/esphome/idf"
export IDF_PATH="$IDF_TOOLS_PATH/frameworks/5.5.6"
. "$IDF_PATH/export.sh" > /dev/null
