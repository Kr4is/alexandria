#!/bin/sh
set -e

# Apply any pending database migrations before starting the server.
# This is safe with SQLite + 1 gunicorn worker because the migration
# runs before gunicorn forks, so there are no concurrent writers.
flask db upgrade

exec gunicorn -w 1 -b 0.0.0.0:5000 app:app
