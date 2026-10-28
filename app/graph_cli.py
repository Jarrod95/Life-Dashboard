"""Read-only Graph diagnostics and explicit import CLI commands."""
import json
import click
from flask import current_app
from app.integrations.graph_auth import status, begin_connect
from app.integrations.onedrive import OneDriveClient
from app.services.data_sources import SOURCES, resolve
from app.services.sync import sync_all, sync_one


def register_cli(app):
    @app.cli.command("graph-test")
    def graph_test():
        """Validate delegated credentials, drive access and configured paths."""
        client = OneDriveClient()
        try:
            me = client.whoami()
            drive = client.drive()
            click.echo("Microsoft account: authenticated; personal drive: accessible")
            for key in SOURCES:
                if key == "mfp_exports":
                    from app.services.mfp_exports import discover
                    _, files, _ = discover(client)
                    click.echo(f"{key}: accessible ({len(files)} CSV exports)")
                    continue
                item, _ = resolve(client, key)
                click.echo(f"{key}: accessible ({'folder' if 'folder' in item else 'file'})")
        except Exception as exc:
            click.echo("Graph connectivity failed: " + getattr(exc, "code", type(exc).__name__))
            raise SystemExit(1)

    @app.cli.command("graph-connect")
    def graph_connect():
        """Start local device-code sign-in; complete in this process."""
        from app.integrations import graph_auth
        from time import sleep
        result = begin_connect(current_app._get_current_object())
        click.echo("Open " + result["verification_uri"] + " and enter " + result["user_code"])
        for _ in range(180):
            state = status()
            if state.get("flow") == "connected":
                click.echo("Connected; token cache protected with Windows DPAPI when available")
                return
            if state.get("flow") == "reconnect_required":
                raise click.ClickException("Microsoft sign-in failed; retry")
            sleep(5)
        raise click.ClickException("Device sign-in expired")

    @app.cli.command("sync-sources")
    @click.option("--all", "all_sources", is_flag=True)
    @click.option("--source", type=click.Choice(tuple(SOURCES)))
    @click.option("--force", is_flag=True)
    def sync_sources(all_sources, source, force):
        """Synchronise one or all configured OneDrive data sources."""
        if all_sources == bool(source):
            raise click.UsageError("Choose exactly one of --all or --source")
        result = sync_all(force, trigger="scheduled") if all_sources else {
            source: sync_one(source, force, trigger="manual")}
        click.echo(json.dumps(result))
        if any(v["status"] == "failed" for v in result.values()):
            raise SystemExit(1)
