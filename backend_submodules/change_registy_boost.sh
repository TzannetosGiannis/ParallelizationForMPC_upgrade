#!/bin/bash

# Define URLs
OLD_URL="https://boostorg.jfrog.io/artifactory/main/release/1.76.0/source/boost_1_76_0.tar.bz2"
NEW_URL="https://archives.boost.io/release/1.76.0/source/boost_1_76_0.tar.bz2"

# Recursively find files under src/ and replace the URL
find MOTION/cmake/ -type f -exec grep -lF "$OLD_URL" {} \; | while read -r file; do
    echo "Updating: $file"
    sed -i.bak "s|$OLD_URL|$NEW_URL|g" "$file" && rm "${file}.bak"
done

find MOTION/docker/ -type f -exec grep -lF "$OLD_URL" {} \; | while read -r file; do
    echo "Updating: $file"
    sed -i.bak "s|$OLD_URL|$NEW_URL|g" "$file" && rm "${file}.bak"
done

