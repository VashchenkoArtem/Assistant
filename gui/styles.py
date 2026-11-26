from pathlib import Path


STYLESHEET = (Path(__file__).parent / "assets" / "styles.qss").read_text(
    encoding="utf-8"
)
