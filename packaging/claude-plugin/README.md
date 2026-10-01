# Claude Plugin Packaging

This directory contains the TinyAssets plugin marketplace surface plus the
packaged `tinyassets-universe-server` plugin.

## Core

- [Plugin README](plugins/tinyassets-universe-server/README.md)

## Structure

- `.claude-plugin/marketplace.json` - marketplace manifest
- `plugins/tinyassets-universe-server/` - packaged plugin contents. Its
  `runtime/tinyassets/` is built by `build_plugin.py`, never committed; releases
  publish the built plugin to the `plugin-dist` branch.

## Notes

- The packaged plugin carries its own end-user slash-command skills. Those are
  plugin assets, not main project workflow skills.
