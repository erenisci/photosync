"""PhotoSync entry point.

When ``settings.json`` exists the app enters sync mode (password prompt → sync).
When it doesn't, the setup wizard runs (Phase 2+). A lightweight CLI fallback is
provided so Phase 1 can be tested end-to-end without the GUI::

    python -m app.main                         # GUI (Phase 2+)
    python -m app.main --cli --password secret  # CLI mode
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from app import paths
from app.config import Settings, load_settings, save_settings, settings_exist
from app.db import Database
from app.rclone_client import RcloneClient
from app.sync_engine import SyncStats, sync

logger = logging.getLogger("photosync")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _print_event(event: str, path: Path) -> None:
    icons = {
        "hashing": "🔑",
        "uploading": "⬆️ ",
        "uploaded": "✅",
        "skipped": "⏭️ ",
        "failed": "❌",
    }
    print(f"  {icons.get(event, '  ')} {event:<10} {path.name}")


def _print_summary(stats: SyncStats) -> None:
    print("\n" + "=" * 50)
    print(f"  Total:    {stats.total}")
    print(f"  Uploaded: {stats.uploaded}")
    print(f"  Skipped:  {stats.skipped}  ({stats.match_percent:.0f}% match)")
    print(f"  Failed:   {stats.failed}")
    if stats.failures:
        print("\n  Failed files:")
        for path, reason in stats.failures:
            print(f"    {path.name}: {reason}")
    print("=" * 50)


def _cli_setup(args: argparse.Namespace) -> Settings:
    """Create settings from CLI flags (for Phase 1 testing without the wizard)."""
    settings = Settings(
        remote_name=args.remote_name or "photosync-remote",
        remote_type=args.remote_type or "s3",
        target_path=args.target_path or "PhotoSync/Backup",
    )
    save_settings(settings)

    # Create rclone remote config if S3 flags were given.
    if args.endpoint:
        rclone = RcloneClient(
            binary=paths.get_rclone_binary(),
            config_path=paths.get_rclone_config_path(),
            password=args.password,
        )
        params: dict[str, str] = {
            "provider": args.s3_provider or "Other",
            "endpoint": args.endpoint,
            "env_auth": "false",
        }
        if args.access_key_id:
            params["access_key_id"] = args.access_key_id
        if args.secret_access_key:
            params["secret_access_key"] = args.secret_access_key
        if args.region:
            params["region"] = args.region
        rclone.config_create(settings.remote_name, settings.remote_type, params)
    return settings


def _run_sync(settings: Settings, password: str | None, scan_root: Path | None) -> int:
    root = scan_root or paths.get_app_root()
    rclone = RcloneClient(
        binary=paths.get_rclone_binary(),
        config_path=paths.get_rclone_config_path(),
        password=password,
    )
    with Database() as db:
        stats = sync(
            root=root,
            db=db,
            rclone=rclone,
            remote=settings.remote_name,
            target_path=settings.target_path,
            on_event=_print_event,
        )
    _print_summary(stats)
    return 1 if stats.failed else 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="PhotoSync — USB-to-cloud backup")
    p.add_argument("--cli", action="store_true", help="run in CLI mode (no GUI)")
    p.add_argument("--password", help="master password for rclone config")
    p.add_argument("--scan-root", type=Path, help="override scan root (for testing)")
    # Quick setup flags for Phase 1 testing.
    setup = p.add_argument_group("quick setup (creates settings + rclone config)")
    setup.add_argument("--remote-name", help="rclone remote name")
    setup.add_argument("--remote-type", default="s3", help="rclone remote type")
    setup.add_argument("--target-path", default="PhotoSync/Backup", help="cloud folder")
    setup.add_argument("--endpoint", help="S3 endpoint URL")
    setup.add_argument("--access-key-id", help="S3 access key")
    setup.add_argument("--secret-access-key", help="S3 secret key")
    setup.add_argument("--region", help="S3 region")
    setup.add_argument("--s3-provider", help="S3 provider (Backblaze, Cloudflare, etc.)")
    return p


def main(argv: list[str] | None = None) -> int:
    """Application entry point. Returns an exit code."""
    _configure_logging()
    args = _build_parser().parse_args(argv)

    if args.cli:
        if args.endpoint and not settings_exist():
            _cli_setup(args)
        if not settings_exist():
            print("No settings found. Run the setup wizard or pass --endpoint.")
            return 1
        settings = load_settings()
        return _run_sync(settings, args.password, args.scan_root)

    # GUI path — Phase 2+. For now fall back to CLI instructions.
    if not settings_exist():
        print("GUI wizard not yet implemented. Use --cli mode with setup flags.")
        print("Example:")
        print(
            "  python -m app.main --cli --endpoint https://s3.us-west-004.backblazeb2.com "
            "--access-key-id KEY --secret-access-key SECRET --password pw"
        )
        return 1
    print("GUI not yet implemented. Use --cli --password <pw> to sync.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
