#!/bin/bash
set -e

echo "Starting build process..."

# Create public and images directories
mkdir -p public/images

# Generate env.js
cat > public/env.js << EOL
window.env = {
  TOURS_TOKEN_ADDRESS: "${TOURS_TOKEN_ADDRESS}",
  BANALL_CONTRACT_ADDRESS: "${BANALL_CONTRACT_ADDRESS}",
  API_BASE_URL: "${API_BASE_URL}",
  MONAD_RPC_URL: "${MONAD_RPC_URL:-https://rpc.ankr.com/monad_testnet}",
  MONAD_CHAIN_ID: 10143
};
EOL

# Verify env.js
if [ -f public/env.js ]; then
  echo "Generated public/env.js successfully"
else
  echo "Failed to generate public/env.js"
  exit 1
fi

# Copy logo (it might already be in public directory)
if [ -f empowertours_logo.svg ]; then
  cp empowertours_logo.svg public/empowertours_logo.svg
  echo "Copied empowertours_logo.svg to public/"
elif [ -f public/empowertours_logo.svg ]; then
  echo "empowertours_logo.svg already exists in public/"
else
  echo "empowertours_logo.svg not found, but continuing build..."
fi

# Copy Farcaster images
if [ -d images ]; then
  cp images/*.png public/images/
  echo "Copied Farcaster images to public/images/"
else
  echo "Images directory not found, skipping"
fi

# Build Farcaster app (completely optional)
if [ -d farcaster ] && [ "${BUILD_FARCASTER:-false}" = "true" ] && command -v npm >/dev/null 2>&1; then
  echo "Building Farcaster app..."
  cd farcaster
  timeout 120s npm install || echo "npm install timed out, continuing..."
  timeout 60s npm run build || echo "npm build failed, continuing..."
  cd ..
  echo "Farcaster build attempt completed"
else
  echo "Skipping Farcaster build (BUILD_FARCASTER=${BUILD_FARCASTER:-false})"
fi

echo "Build completed successfully"
