#!/bin/sh
# P6: on first start, create the two demo sessions so the dashboard has something to show.
# A clean finished run and one waiting for staff (E6). Skipped when the database already exists.
set -e
if [ ! -f "$SILVERFILE_DB" ]; then
  echo "Seeding demo sessions into $SILVERFILE_DB"
  python run.py start --demo --thread-id demo-clean
  python run.py start --demo --hitl --thread-id demo-hitl
fi
exec "$@"
