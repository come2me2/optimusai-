"""Production entrypoint for ONREZA / cloud deploy."""
import os
from pathlib import Path


def main() -> None:
    data_dir = Path(os.environ.get("OPTIMUS_DATA_DIR", "/tmp/optimus-data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("OPTIMUS_DB_PATH", str(data_dir / "optimus.db"))

    import uvicorn
    from optimus.main import create_app

    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    db_path = Path(os.environ["OPTIMUS_DB_PATH"])

    app = create_app(db_path=db_path)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
