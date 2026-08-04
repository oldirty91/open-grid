from pathlib import Path


def test_entity_upsert_does_not_write_task_columns():
    source = (Path(__file__).parents[1] / "app" / "main.py").read_text()
    start = source.index("INSERT INTO entities_current")
    end = source.index("RETURNING entity_id", start)
    sql = source[start:end]
    assert "claimed_at" not in sql
    assert "attempt = attempt + 1" not in sql
