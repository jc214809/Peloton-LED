"""The updater's command line: peloton-install.sh's peloton-update runs it from the checkout with
/opt/peloton-led's venv (cd <checkout> && /opt/peloton-led/venv/bin/python -m self_update ...):

    sudo peloton-update status                   # what's installed, the last update
    peloton-update check [--channel beta]        # what an update would do; changes nothing
    sudo peloton-update update [--channel beta]  # update, rolling back if it fails
    sudo peloton-update rollback                 # undo the last update (also sudo peloton-rollback)
    sudo peloton-update recover                  # at boot: undo an update a power cut stopped

The channel is "releases" (the default) or "beta" (develop-beta's tip, once its CI passed). A
rollback also puts back the live config.json as it was before the update, undoing settings saved
since. Exits 0 when it did (or would do) what was asked, or there was nothing to do; 1 otherwise.
"""
import argparse
import logging
import os
import sys

from self_update.board import Board
from self_update.update import CHANNELS, NOTHING_TO_UNDO, RELEASES, Updater, name_of
from utils import heartbeat

logger = logging.getLogger('peloton-led.update')

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def status(updater):
    """What status prints, and whether it could read it all."""
    board = updater.board
    lines = [f"Installed: {updater.installed_version} at {board.head()[:7]}"
             f" ({'on ' + board.branch() if board.branch() else 'detached'})"]
    readable = not updater.state.unreadable()
    if readable:
        record = updater.state.load()
        lines.append(f"Last update: {record['phase']}")
    else:
        record = {}
        lines.append(f"Last update: unknown: {updater.state.folder} is root's, so run it with sudo:"
                     " sudo peloton-update status")
    if record.get("to"):
        lines.append(f"  to {record['to'].get('ref')} ({str(record['to'].get('sha'))[:7]}),"
                     f" from {name_of(record['from'])}")
    if record.get("reason"):
        lines.append(f"  rolled back because: {record['reason']}")
    if record.get("good"):
        lines.append(f"Good commits: {', '.join(sha[:7] for sha in record['good'])}")
    beat = heartbeat.read(updater.heartbeat_path)
    lines.append(f"Heartbeat: {updater.clock() - beat['at']:.0f}s ago" if beat else "Heartbeat: none")
    return "\n".join(lines), readable


def main(argv=None, updater=None, euid=os.geteuid):
    parser = argparse.ArgumentParser(prog="python3 -m self_update", description="Update the board from GitHub, with rollback.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="what's installed and how the last update went")
    for name, text in (("check", "say what an update would do, changing nothing"),
                       ("update", "update, rolling back if the new version isn't healthy (as root)")):
        command = commands.add_parser(name, help=text)
        command.add_argument("--channel", choices=CHANNELS, default=RELEASES)
    commands.add_parser("rollback", help="undo the last update, config.json included (as root)")
    commands.add_parser("recover", help="roll back an update that stopped midway, else nothing (as root; "
                                        "peloton-update-recover.service runs it at boot)")
    args = parser.parse_args(argv)

    # To the journal only (the recover unit's, or the terminal): the display's app.log rotates in
    # the display's process, and two writers rotating one file lose lines.
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')

    updater = updater or Updater(Board(APP_DIR))
    if args.command == "status":
        text, readable = status(updater)
        print(text)
        return 0 if readable else 1
    if args.command in ("update", "rollback", "recover") and euid() != 0:
        print(f"{args.command} needs root: sudo peloton-update {args.command}", file=sys.stderr)
        return 1
    if args.command == "rollback":
        outcome = updater.rollback()
    elif args.command == "recover":
        outcome = updater.recover()
    else:
        outcome = updater.update(args.channel, dry_run=args.command == "check")
    print(f"{outcome.result}: {outcome.message}")
    usual_boot = args.command == "recover" and outcome.result == NOTHING_TO_UNDO
    if args.command != "check" and not usual_boot:  # outcome.json: for a settings-page Updates card
        try:
            updater.state.save_outcome({"command": args.command, "channel": getattr(args, "channel", None),
                                        "result": outcome.result, "message": outcome.message,
                                        "ok": outcome.ok, "at": updater.clock()})
        except OSError as e:
            logger.warning("Couldn't keep the outcome for the settings page: %s", e)
    return 0 if outcome.ok or usual_boot else 1


if __name__ == "__main__":
    sys.exit(main())
