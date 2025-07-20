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
};
EOL

# Verify env.js
if [ -f public/env.js ]; then
  echo "Generated public/env.js successfully"
else
  echo "Failed to generate public/env.js"
  exit 1
fi

# Copy logo
if [ -f empowertours_logo.svg ]; then
  cp empowertours_logo.svg public/empowertours_logo.svg
  echo "Copied empowertours_logo.svg to public/"
else
  echo "empowertours_logo.svg not found"
  exit 1
fi

# Copy Farcaster images
if [ -d images ]; then
  cp images/*.png public/images/
  echo "Copied Farcaster images to public/images/"
else
  echo "Images directory not found, skipping"
fi

# Build Farcaster app
if [ -d farcaster ]; then
  cd farcaster
  npm install
  npm run build
  cd ..
  echo "Farcaster Mini App built successfully"
else
  echo "Farcaster directory not found, skipping"
fi

echo "Build completed successfully"
