#!/bin/bash

# Check if the config.conf file exists
if [ ! -f "config.conf" ]; then
    echo "Error: config.conf file not found!"
    exit 1
fi

# Read each line from the config.conf file
while IFS=' ' read -r id address
do
    # Start a new GNOME terminal for each node and run the python script with the node ID
    gnome-terminal -- bash -c "python3 node.py $id; exec bash" &
done < config.conf

echo "All nodes have been started in separate terminals."
