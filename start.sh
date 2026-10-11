#!/bin/bash

# Function to kill both processes when Ctrl+C is pressed
cleanup() {
    echo -e "\nStopping both servers..."
    kill $PYTHON_PID $NPM_PID 2>/dev/null
    wait $PYTHON_PID $NPM_PID 2>/dev/null
    echo "Servers stopped."
    exit 0
}

# Trap SIGINT (Ctrl+C) and SIGTERM, routing them to the cleanup function
trap cleanup SIGINT SIGTERM

# Start the Python server in the background and save its Process ID
echo "Starting Python server..."
python -m server.server &
PYTHON_PID=$!

# Start the npm dev server in the background and save its Process ID
echo "Starting npm server..."
(cd frontend && npm run dev) &
NPM_PID=$!

# Keep the script running and wait for both background processes
wait