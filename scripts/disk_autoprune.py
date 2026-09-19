"""Compatibility entrypoint for narrow daemon-image retention; dry-run by default."""

try:
    from scripts.daemon_image_retention import main
except ModuleNotFoundError:
    from daemon_image_retention import main


if __name__ == "__main__":
    raise SystemExit(main())
