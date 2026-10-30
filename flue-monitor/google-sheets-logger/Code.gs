// Google Apps Script webhook that appends flue-monitor sensor readings to
// a Google Sheet. Bind this to a Sheet via Extensions -> Apps Script, paste
// it in place of the placeholder code, replace SHARED_SECRET below with your
// own random string, then Deploy -> New deployment -> Web app
// (Execute as: Me, Who has access: Anyone). Put the resulting /exec URL and
// the secret you chose into the sidecar's settings via
// POST /api/settings (see README.md) -- not a secrets file, since this
// project's settings are runtime/NVS-backed rather than compiled in.
//
// The placeholder secret below is intentionally not a real one -- this file
// is a template checked into git, not the live deployed script. Set the
// real secret only inside the Apps Script editor for your own deployment,
// never here.
//
// This uses GET (query parameters), not POST with a JSON body. Apps Script
// Web Apps always respond with a redirect to a script.googleusercontent.com
// URL that only accepts GET; ESP-IDF's own HTTP client (esp_http_client, see
// sheets_logger.c) preserves the original method across that redirect
// instead of downgrading to GET the way browsers and curl's default
// behavior do, so a POST here fails with HTTP 405 on the ESP32 even though
// it can look fine when tested with a browser or a naive curl call. Using
// GET end-to-end sidesteps the whole issue since GET always redirects to
// GET regardless of the client's redirect-method policy.
const SHARED_SECRET = "REPLACE_ME_WITH_A_RANDOM_STRING";
// Existing headers determine column positions; new fields are appended.
const SHEET_NAME = "Sensor Log";
// Legacy labels remain stable. New fields use their exact query key as header.
const FIELDS = [
  ["thermocouple", "Thermocouple (C)", "0.0"],
  ["cold_junction", "Cold Junction (C)", "0.0"],
  ["event", "Event", ""],
  ["rate", "Rate (C/min)", "0.00"],
  ["zone", "Zone", ""],
  ["room_temperature", "Room Temperature (C)", "0.0"],
];
const RESERVED = new Set(["secret", "event_ts", "age_ms"]);
const HEADER_ROW = ["Timestamp", ...FIELDS.map(f => f[1])];

function cellValue(key, value) {
  const text = typeof value === "string" ? value.trim() : "";
  if (text === "") return "";
  // Decimal numbers only: retain zero, reject NaN/Infinity and formula input.
  const number = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(text) ? Number(text) : NaN;
  if (["thermocouple", "cold_junction", "rate", "room_temperature"].includes(key)) {
    if (!Number.isFinite(number)) return "";
    return key === "room_temperature" && (number < -40 || number > 60) ? "" : number;
  }
  if (key !== "event" && key !== "zone" && Number.isFinite(number)) return number;
  // appendRow interprets leading '=' as a formula. Store arbitrary text literally.
  return /^[=+@-]/.test(text) ? "'" + text : text;
}

function doGet(e) {
  const p = (e && e.parameter) || {};
  const reply = text => ContentService.createTextOutput(text).setMimeType(ContentService.MimeType.TEXT);
  if (p.secret !== SHARED_SECRET) return reply("forbidden");
  // Serialize header discovery + row append across concurrent webhook requests.
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) return reply("busy");
  try {
    const book = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = book.getSheetByName(SHEET_NAME) || book.insertSheet(SHEET_NAME);
    const headers = sheet.getLastRow() === 0 ? [] :
      sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const previousWidth = headers.length;
    for (const label of HEADER_ROW) if (!headers.includes(label)) headers.push(label);
    const values = new Map();
    for (const key of Object.keys(p).sort()) {
      if (RESERVED.has(key) || !/^[a-z][a-z0-9_]{0,63}$/.test(key)) continue;
      const known = FIELDS.find(f => f[0] === key);
      const label = known ? known[1] : key;
      if (!headers.includes(label)) headers.push(label);
      values.set(label, cellValue(key, p[key]));
    }
    if (headers.length > sheet.getMaxColumns())
      sheet.insertColumnsAfter(sheet.getMaxColumns(), headers.length - sheet.getMaxColumns());
    if (headers.length > previousWidth)
      sheet.getRange(1, previousWidth + 1, 1, headers.length - previousWidth)
        .setValues([headers.slice(previousWidth)]);
    for (const [, label, format] of FIELDS) {
      const col = headers.indexOf(label) + 1;
      if (format && sheet.getRange(2, col).getNumberFormat() !== format)
        sheet.getRange(2, col, sheet.getMaxRows() - 1, 1).setNumberFormat(format);
    }
  // Two ways the device tells us when this actually happened -- prefer the
  // more accurate one (see REVIEW.md finding D4):
  //   - event_ts: an absolute Unix timestamp (seconds) from the device's own
  //     SNTP-synced wall clock, captured at the moment of the tap/reading.
  //     Immune to this request's own latency, however long it took to get
  //     here -- unlike age_ms below, which is necessarily computed before
  //     the request is even sent. 0 (or absent, on an older device build)
  //     means the device's clock hadn't synced yet.
  //   - age_ms: how long ago (in ms, relative to right now) the device says
  //     this reading/event actually happened -- only corrects for the
  //     device's own queue backlog, not this request's transit/processing
  //     time, so it's the fallback for when event_ts isn't available, not a
  //     full fix on its own. REVIEW.md finding #3 originally flagged this
  //     drift; missing/non-numeric age_ms (an older device build) falls back
  //     to 0, i.e. the original behavior of just using new Date().
  const eventTsS = Number(p.event_ts) || 0;
  const ageMs = Number(p.age_ms) || 0;
  const timestamp = eventTsS > 0 ? new Date(eventTsS * 1000) : new Date(Date.now() - ageMs);

    values.set("Timestamp", timestamp);
    sheet.appendRow(headers.map(label => values.has(label) ? values.get(label) : ""));
    SpreadsheetApp.flush();
    return reply("ok");
  } finally {
    lock.releaseLock();
  }
}
