"""Export the reviewed candidate as a native ESP-IDF v6.0.3 patch (no SDK edits)."""
import difflib
import importlib.util
from pathlib import Path
import re
import tempfile

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parents[1]
spec = importlib.util.spec_from_file_location('patch_iwdt', TOOLS / 'patch_iwdt_transition.py')
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)
sdk = Path.home() / 'Library/Caches/esphome/idf/frameworks/6.0.3'


def tokens(source):
    source = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
    return re.findall(r'\w+|[^\s]', source)


with tempfile.TemporaryDirectory() as tmp:
    patch.generate(sdk, Path(tmp))
    outputs = {}
    for name in patch.EXPECTED:
        source = (Path(tmp) / Path(name).name).read_text()
        source = source.replace('s_flue_livelock_enabled', 's_livelock_enabled')
        source = source.replace('flue_iwdt_', 'iwdt_').replace('FLUE_IWDT_', 'IWDT_')
        if name.endswith('/int_wdt.c'):
            # Comments explain the protocol, not project history or one timeout configuration.
            comments = iter([
                '/* Serialize the livelock handler mode with the hardware timeout.\n * Handler completion relies on MEMW ordering its peripheral writes before\n * publishing idle bookkeeping in internal memory.\n */',
                '/* Bound retries without feeding a stalled handler. The hardware watchdog\n * continues running and may reset the system before this bound expires.\n */',
                '/* Observe both handler halves with local high interrupts masked. These\n * separate loads are rechecked after installing a fresh full timeout.\n */',
                '/* Read-back detects rejected writes; handler exclusion provides ownership. */',
                '/* Let an active handler finish with high interrupts restored. */',
                '/* Extend and feed before changing the handler mode. An expiry during\n         * this operation is detected by the following handler-state check. */',
                '/* A handler entering during the preceding writes must publish its\n         * bookkeeping before proceeding to its delayed register writes. */',
                '/* Disable only after installing the full timeout. On enable, publish\n         * the recovery budget before installing the short timeout. */',
                '/* Do not continue with an unverified watchdog configuration. */',
                '/* Preserve the selected mode when the tick feeds the watchdog. */',
            ])
            start = source.index('/* IWDT transition candidate')
            end = source.index('\n#endif', source.index('static void ESP_SYSTEM_IRAM_ATTR iwdt_tick', start))
            block = source[start:end]
            changed = re.sub(r'/\*.*?\*/', lambda _: next(comments), block, flags=re.S)
            assert tokens(block) == tokens(changed), 'Unexpected executable change'
            source = source[:start] + changed + source[end:]
            source = source.replace('#include "soc/timer_group_reg.h"\n#include <stdlib.h>\n', '')
            source = source.replace('#include <stdint.h>', '#include <stdlib.h>\n#include <stdint.h>')
            source = source.replace('#include "esp_private/eco3_livelock_workaround.h"', '#include "esp_private/eco3_livelock_workaround.h"\n#include "soc/timer_group_reg.h"')
            source = source.replace('extern volatile uint32_t _lx_intr_livelock_sync[2], _lx_intr_livelock_app, _lx_intr_livelock_pro;', 'extern volatile uint32_t _lx_intr_livelock_sync[2];\nextern volatile uint32_t _lx_intr_livelock_app;\nextern volatile uint32_t _lx_intr_livelock_pro;')
            source = source.replace('}\nstatic inline', '}\n\nstatic inline')
        if name.endswith('/eco3_livelock_workaround.c'):
            source = source.replace('void esp_int_wdt_set_livelock_mode(bool enable);\n\n', '')
        outputs[name] = source
    header = 'components/esp_system/include/esp_private/esp_int_wdt.h'
    source = (sdk / header).read_text().replace('#include "sdkconfig.h"', '#include <stdbool.h>\n#include <stdint.h>\n#include "sdkconfig.h"')
    anchor = 'void esp_int_wdt_reconfigure_ticks(uint32_t stage0_ticks, uint32_t stage1_ticks);'
    source = source.replace(anchor, anchor + '''

/**
 * @brief Change the ESP32 cache livelock recovery mode and watchdog timeout.
 *
 * Serializes the transition with tick feeds and waits for active recovery
 * handlers before publishing the new mode. Does not feed while waiting for
 * an active handler. Call before stalling the other CPU.
 *
 * @param enable Whether cache livelock recovery should be enabled.
 */
void esp_int_wdt_set_livelock_mode(bool enable);''')
    outputs[header] = source
    test_root = 'components/esp_system/test_apps/esp_system_unity_tests/'
    outputs[test_root + 'main/test_int_wdt.c'] = (HERE / 'tests/test_int_wdt.c').read_text()
    cmake = test_root + 'main/CMakeLists.txt'
    outputs[cmake] = (sdk / cmake).read_text().replace('         "test_ipc.c"', '         "test_ipc.c"\n         "test_int_wdt.c"')
    diff = []
    for name, source in outputs.items():
        target = HERE / 'src' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)
        diff.extend(difflib.unified_diff(((sdk / name).read_text() if (sdk / name).exists() else '').splitlines(True), source.splitlines(True), fromfile=('a/' + name if (sdk / name).exists() else '/dev/null'), tofile='b/' + name))
    (HERE / 'iwdt-transition.patch').write_text(''.join(diff))
print('Exported v6.0.3 review patch including Unity tests; installed SDK unchanged.')
