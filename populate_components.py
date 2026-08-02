from digikey_client import search_by_keyword
from components_db import init_db, insert_components, save_categories, get_categories

# Fallback example categories (the original Janibe crib-monitor project) - used only
# if you run this file directly without going through run_pipeline.py first.
EXAMPLE_CATEGORIES = [
    {"category": "microcontroller_ble", "search_keyword": "nRF52 BLE microcontroller",
     "requirement": "32-bit, low-power MCU with integrated BLE 5.x and OTA DFU support, "
                    "target sleep current < 5 microamps."},
    {"category": "pir_motion_sensor", "search_keyword": "PIR motion sensor module",
     "requirement": "PIR motion sensor suitable for detecting a baby's movement in a crib, low quiescent current."},
    {"category": "ambient_light_sensor", "search_keyword": "photoresistor CdS cell",
     "requirement": "Analog ambient light sensor to distinguish day from night."},
    {"category": "sound_sensor", "search_keyword": "electret condenser microphone SMD",
     "requirement": "Analog microphone to detect a baby's sounds against background noise."},
    {"category": "led_main", "search_keyword": "warm white SMD LED",
     "requirement": "Warm white or orange LED, PWM dimmable, no blue-dominant light."},
    {"category": "led_status", "search_keyword": "SMD indicator LED low power",
     "requirement": "Single status indicator LED for low-battery warning."},
    {"category": "lipo_charger_ic", "search_keyword": "TP4057 lithium battery charger",
     "requirement": "Single-cell LiPo charger IC with USB-C input and overcharge protection."},
    {"category": "voltage_regulator", "search_keyword": "LDO voltage regulator 3.3V low quiescent current",
     "requirement": "Regulator to supply MCU/sensors from a single-cell LiPo battery."},
    {"category": "battery_connector", "search_keyword": "JST-PH 2-pin connector",
     "requirement": "JST-PH 2-pin connector for the LiPo battery."},
    {"category": "push_button", "search_keyword": "SMD tactile push button switch",
     "requirement": "SMD tactile push button for brightness controls, low profile."},
    {"category": "slide_switch", "search_keyword": "slide switch SMD 3 position",
     "requirement": "3-position SMD slide switch for mode/delay selection, low profile."},
]


def populate_from_categories(categories, record_count=5):
    """categories: list of dicts with keys category, search_keyword, requirement."""
    init_db()
    save_categories(categories)
    for c in categories:
        print(f"Searching DigiKey for '{c['search_keyword']}' -> category '{c['category']}'...")
        try:
            parts = search_by_keyword(c["search_keyword"], record_count=record_count)
        except Exception as e:
            print(f"  Failed: {e}")
            continue
        insert_components(c["category"], parts)
        print(f"  Stored {len(parts)} parts.")


if __name__ == "__main__":
    populate_from_categories(EXAMPLE_CATEGORIES)