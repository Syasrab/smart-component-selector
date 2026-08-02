import sqlite3
import os

DB_FILE = "mcu_database.db"

# The final, PDF-verified dataset
MICROCONTROLLERS = [
    ("STM32F103C8T6", "STM32F1", "32-bit ARM Cortex-M3", 72, 64, 20, "2.0-3.6V", 37, 12, 0, 0, 1.8456, 52500, 1.4),
    ("ATMEGA328P-AU", "AVR", "8-bit AVR", 20, 32, 2, "1.8-5.5V", 23, 10, 0, 0, 2.4283, 1270, 40),
    ("RP2040", "Raspberry Pi", "Dual 32-bit ARM Cortex-M0+", 133, 2000, 264, "3.3V", 30, 12, 0, 0, 0.9930, 53971, None),
    ("STM32G030F6P6TR", "STM32G0", "32-bit ARM Cortex-M0+", 64, 64, 8, "2.0-3.6V", 17, 12, 0, 0, 1.2305, 1285, None),
    ("STM32F030C8T6", "STM32F0", "32-bit ARM Cortex-M0", 48, 64, 8, "2.4-3.6V", 39, 12, 0, 0, 1.3876, 28290, None),
    ("ATMEGA328PB-AU", "AVR", "8-bit AVR", 20, 32, 2, "1.8-5.5V", 27, 10, 0, 0, 1.8882, 14009, 0.2),
    ("STM8S003F3P6TR", "STM8", "8-bit STM8", 16, 8, 1, "2.95-5.5V", 16, 10, 0, 0, 0.5581, 9500, None),
    ("STM32F407VET6", "STM32F4", "32-bit ARM Cortex-M4", 168, 1000, 192, "1.8-3.6V", 82, 12, 0, 0, 7.2517, 2464, 2.5),
    ("STM32H743ZIT6", "STM32H7", "32-bit ARM Cortex-M7", 400, 2000, 1000, "1.62-3.6V", 114, 16, 0, 0, 11.0706, 27, 4),
    ("ATTINY13A-SSUR", "AVR", "8-bit AVR", 20, 1, 0.062, "1.8-5.5V", 6, 10, 0, 0, 1.2155, 7988, None),
]


def init_db():
    """Create the table and seed it, but only if the DB file doesn't already exist."""
    if os.path.exists(DB_FILE):
        return

    connection = sqlite3.connect(DB_FILE)
    cursor = connection.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS microcontrollers (
        name TEXT PRIMARY KEY,
        family TEXT,
        core TEXT,
        clock_mhz REAL,
        flash_kb REAL,
        ram_kb REAL,
        voltage TEXT,
        digital_io INTEGER,
        adc_bit INTEGER,
        has_wifi INTEGER,
        has_bluetooth INTEGER,
        price_usd REAL,
        in_stock INTEGER,
        stop_current_ua REAL
    )
    """)

    cursor.executemany("""
    INSERT OR REPLACE INTO microcontrollers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, MICROCONTROLLERS)

    connection.commit()
    connection.close()
    print(f"Database created and seeded with {len(MICROCONTROLLERS)} microcontrollers.")


def get_connection():
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def get_candidates(min_flash_kb=0, min_ram_kb=0, min_io=0, needs_wifi=False, needs_bluetooth=False, max_price_usd=None):
    connection = get_connection()
    cursor = connection.cursor()

    query = """
        SELECT * FROM microcontrollers
        WHERE flash_kb >= ?
          AND ram_kb >= ?
          AND digital_io >= ?
    """
    params = [min_flash_kb, min_ram_kb, min_io]

    if needs_wifi:
        query += " AND has_wifi = 1"
    if needs_bluetooth:
        query += " AND has_bluetooth = 1"
    if max_price_usd is not None:
        query += " AND price_usd <= ?"
        params.append(max_price_usd)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    connection.close()
    return rows


DEFAULT_WEIGHTS = {
    "price_usd": -2.0,
    "digital_io": 0.1,
    "flash_kb": 0.01,
}

# Applied when a weight targets stop_current_ua but the chip's value is
# unknown (None) - keeps unknown-power chips from unfairly beating chips
# with a known, real value.
UNKNOWN_STOP_CURRENT_PENALTY = 50


def score_row(row, weights=None):
    """Generic weighted-sum scorer. weights maps column name -> multiplier.
    Positive weight = maximize that column, negative = minimize it."""
    weights = weights or DEFAULT_WEIGHTS
    score = 0
    for column, weight in weights.items():
        value = row[column] if column in row.keys() else None
        if value is None:
            if column == "stop_current_ua" and weight < 0:
                score -= UNKNOWN_STOP_CURRENT_PENALTY
            continue
        score += weight * value
    return score


def rank_rows(rows, weights=None):
    scored = [(row, score_row(row, weights)) for row in rows]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


if __name__ == "__main__":
    init_db()

    results = get_candidates(min_flash_kb=16, min_io=20)
    print(f"\n{len(results)} chips meet the requirements:")
    for row in results:
        print(f"  {row['name']}")

    ranked = rank_rows(results, weights={"price_usd": -5.0, "digital_io": 0.1, "flash_kb": 0.01})
    print("\nRanked by cheapest-first priority:")
    for row, score in ranked:
        print(f"  {row['name']}: score={score:.2f}, price=${row['price_usd']}")
