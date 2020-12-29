#!/bin/bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
. $DIR/print-functions.sh

# if verbosity is on, output all ENV variables for debugging purposes.
if [[ "$VERBOSE" == "true" ]]; then
	print_msg "ENV variables at run time..."
	for VARIABLE in $(env); do
		echo $VARIABLE
	done
	print_line
fi

# This infinite loop is here in case we need to manually enter the container.
if [[ "$BASH_INFINITE_LOOP" == "true" ]]; then
  print_msg "Entering Bash infinite loop, so admin can login to container."
	for((i=0; ; ++i)); do
			sleep 1
	done
fi

# start the Flask server
echo "Starting up container with the following command: "
echo "${@}"
print_line ""
exec "$@"