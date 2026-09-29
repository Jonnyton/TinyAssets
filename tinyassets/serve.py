"""Container entry point: ``python -m tinyassets.serve``.

Importing this module does nothing, on purpose.

Every credential-broker and workspace child is a ``multiprocessing`` *spawn*
child, and a spawn child re-imports the parent's ``__main__`` module by name
before it runs anything. With ``python -m tinyassets.universe_server`` that is
the whole server, about 5 s of imports on the production box. A served round
spawns about three broker children (catalogue, benchmarks, inference), so every
round waited about 18 s before its model was asked. Measured live 2026-09-29:
19-22 s between every round's reservations on the free account, against 0.25 s
to start the same child under a light ``__main__``.

Under this launcher a spawn child re-imports only this file, and the server is
imported under its own name, so it is loaded once rather than also as
``__main__``. The children stay spawn children: nothing is inherited that was
not before.
"""

if __name__ == "__main__":
    from tinyassets.universe_server import main

    main()
