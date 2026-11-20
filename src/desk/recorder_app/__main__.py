import argparse
import sys

from desk.recorder_app.main import run

parser = argparse.ArgumentParser(prog="desk.recorder_app")
parser.add_argument("--socket", required=True, help="Unix socket Desk is listening on")
sys.exit(run(parser.parse_args().socket))
