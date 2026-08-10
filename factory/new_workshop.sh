#!/bin/sh
set -eu

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "Usage: factory/new_workshop.sh DESTINATION [live|tv|recipe-rebrand]" >&2
  exit 2
fi

destination=$1
scenario=${2:-live}
case "$scenario" in live|tv|recipe-rebrand) ;; *) echo "Unknown scenario: $scenario" >&2; exit 2 ;; esac

if [ -e "$destination" ]; then
  echo "Refusing to overwrite existing destination: $destination" >&2
  exit 1
fi

repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
remote=$(git -C "$repo" remote get-url origin)
git clone "$remote" "$destination"
if [ "$scenario" != live ]; then
  "$destination/setup_demo.sh" --scenario "$scenario"
fi

echo "Disposable workshop checkout ready: $destination ($scenario)"
