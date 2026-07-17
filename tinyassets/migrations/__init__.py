"""Runnable, deployable data migrations that ship INSIDE the ``tinyassets``
package (so they are importable wherever the package is installed — including the
production image, where ``scripts/`` is not copied).

Each migration is runnable as a module, e.g.::

    python -m tinyassets.migrations.retired_subscription_records --inventory
"""
