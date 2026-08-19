import tomllib
from importlib.resources import files
from pathlib import Path

from revenueops import __version__


def test_project_metadata_and_packaged_web_assets_are_consistent():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["version"] == __version__ == "0.1.0"
    assert project["scripts"]["revenueops"] == "revenueops.cli:main"
    web = files("revenueops").joinpath("web")
    assert all(web.joinpath(name).is_file() for name in ("index.html", "styles.css", "app.js"))
