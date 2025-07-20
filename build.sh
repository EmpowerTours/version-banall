#!/bin/bash
echo "window.env = { TOURS_TOKEN_ADDRESS: '$TOURS_TOKEN_ADDRESS' };" > public/env.js
pip install -r requirements.txt
