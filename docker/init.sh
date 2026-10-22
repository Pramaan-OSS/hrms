#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' 'The upstream bootstrap was removed: it fetched mutable upstream source at startup.' 'Use ./start for the key-only local stack; see README.md.' >&2
exit 1
