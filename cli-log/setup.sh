#!/bin/bash

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install as editable package
echo "Installing cli-log..."
pip install -e .

echo "Setup complete! You can now use 'cli-log' command."
echo "To activate the environment manually, run: source venv/bin/activate"