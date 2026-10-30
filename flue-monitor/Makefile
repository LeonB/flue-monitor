.PHONY: gsheets-code

# Override with HOST=192.168.1.137 if mDNS is unavailable.
HOST ?= flue-monitor.local

# Prompt for dashboard password, fetch settings with an in-memory session,
# print Code.gs with the live secret and copy it to the macOS clipboard.
# No password/cookie/secret files are written; the session is logged out.
gsheets-code:
	@python3 tools/gsheets_code.py --host "$(HOST)"
