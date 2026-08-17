import sqlite3

from tools.backtest_staking_tiers import load_db
from tools.coverage_gate_report import gate_rows, main


def _db(path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY, final_action TEXT, result_hit INTEGER,
            pnl_units REAL, gale_bet_value REAL, sda_numbers TEXT,
            dealer TEXT, spin_direction TEXT
        );
        CREATE TABLE decision_dna (
            decision_id INTEGER, feature_name TEXT, hit INTEGER
        );
        """
    )
    rows = [
        (1, "APOSTAR", 1, 1.0, 1.0, "[1]", "Maria", "cw"),
        (2, "APOSTAR", 0, -1.0, 1.0, "[1]", "Maria", "cw"),
        (3, "APOSTAR", 1, 1.0, 1.0, "[1]", "Maria", "cw"),
    ]
    connection.executemany("INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    dna = [
        (1, "v5_would_hit_17", 1), (1, "v5_would_hit_21", 1),
        (2, "v5_would_hit_17", 0), (2, "v5_would_hit_21", 0),
        (3, "v5_would_hit_17", 1), (3, "v5_would_hit_21", 1),
    ]
    connection.executemany("INSERT INTO decision_dna VALUES (?, ?, ?)", dna)
    connection.commit()
    connection.close()


def test_gate_report_fixture_and_verdict(tmp_path, capsys):
    path = tmp_path / "decisions.db"
    _db(path)
    result = gate_rows(load_db(path))
    assert result[0]["n"] == 3
    assert result[0]["extras"] == 0
    assert result[0]["verdict"] == "NAO_PAGA"
    assert main(["--db", str(path)]) == 0
    output = capsys.readouterr().out
    assert "TOTAL 3" in output
    assert "VEREDITO=NAO_PAGA" in output
