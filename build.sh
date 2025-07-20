#!/bin/bash
set -e

echo "Starting build process..."

# Create public directory if it doesn't exist
mkdir -p public

# Generate env.js with environment variables
cat > public/env.js << EOL
window.env = {
  TOURS_TOKEN_ADDRESS: "${TOURS_TOKEN_ADDRESS}",
  BANALL_CONTRACT_ADDRESS: "${BANALL_CONTRACT_ADDRESS}",
  API_BASE_URL: "${API_BASE_URL}",
};
EOL

# Verify env.js was created
if [ -f public/env.js ]; then
  echo "Generated public/env.js successfully"
else
  echo "Failed to generate public/env.js"
  exit 1
fi

# Copy logo to public directory
if [ -f empowertours_logo.svg ]; then
  cp empowertours_logo.svg public/empowertours_logo.svg
  echo "Copied empowertours_logo.svg to public/"
else
  echo "empowertours_logo.svg not found in root directory"
  exit 1
fi

# Build Farcaster Mini App
if [ -d farcaster ]; then
  cd farcaster
  npm install
  npm run build
  cd ..
  echo "Farcaster Mini App built successfully"
else
  echo "Farcaster directory not found, skipping Farcaster build"
fi

echo "Build completed successfully"
