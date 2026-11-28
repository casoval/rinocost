"""Ejecutar desde backend/:
    python -m app.importers b1  ruta/b1.pdf [--json]
    python -m app.importers esp ruta/especificaciones.pdf [--b1 ruta/b1.pdf] [--json]
    python -m app.importers presnet ruta/revista.pdf --excel biblioteca.xlsx [--json]
(Sin palabra inicial se asume b1, como antes.)"""
import sys

from . import b1_parser, presnet_parser, spec_parser

args = sys.argv[1:]
modo = args[0] if args and args[0] in ("b1", "esp", "presnet") else "b1"
if args and args[0] in ("b1", "esp", "presnet"):
    args = args[1:]
raise SystemExit({"esp": spec_parser, "presnet": presnet_parser}.get(modo, b1_parser)._main(args))
