from importlib.metadata import PackageNotFoundError, version

import typer

from app.cli_site import site_app

cli = typer.Typer(no_args_is_help=True)
cli.add_typer(site_app, name="site")

try:
    _PKG_VERSION = version("claudesite-orchestrator")
except PackageNotFoundError:
    _PKG_VERSION = "0.0.0"


@cli.callback()
def _root(
    ctx: typer.Context,
    site: str | None = typer.Option(
        None,
        "--site",
        "-s",
        help="Default site slug for future task commands (stored in context).",
    ),
) -> None:
    """CLI оркестратора Claudesite."""
    ctx.ensure_object(dict)
    if site:
        ctx.obj["site"] = site


@cli.command("version")
def version_command() -> None:
    """Вывести версию пакета."""
    typer.echo(_PKG_VERSION)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
