"""Updates the board from GitHub, with rollback: python -m self_update (see __main__).

github.py asks GitHub what's newer, board.py does the git/installer/systemctl work, state.py keeps
the rollback point in /var/lib/peloton-update, update.py decides. It runs from the checkout (the
git clone peloton-install.sh installs from), not /opt/peloton-led: an update moves the checkout to
the new version and reruns its installer. Its own package, not part of the app or the settings
page, because an update restarts both. A version without it can't be updated to: the way back
would be gone. Ported from LightningLane-Live-LED's.
"""
