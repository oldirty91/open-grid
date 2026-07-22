from pathlib import Path
import ast

path = Path("backend/app/schema.py")
source = path.read_text(encoding="utf-8")
ast.parse(source)

for bad in ('"udp_listen_port":14550', '"default_altitude_m":30'):
    # These values are valid inside JSON passed as bind data, but must not occur
    # inside a SQLAlchemy text() SQL string where ":14550" becomes a bind name.
    for segment in source.split('text("""')[1:]:
        sql = segment.split('""")', 1)[0]
        if bad in sql:
            raise SystemExit(f"Unsafe JSON literal remains inside SQL text: {bad}")

print("schema SQL check passed")
