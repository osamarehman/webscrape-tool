#!/bin/bash

# Change to the directory containing the 'seointense' folder
#cd /path/to/directory-containing-seointense  # Replace with the actual path

# Navigate into the 'seointense' folder
cd seointense

# Check if .git directory exists
if [ ! -d ".git" ]; then
    git init
    git remote add origin git@github.com:osamarehman/seointense.git
fi

# Remove all history and start fresh
git checkout --orphan latest_branch

# Add all changes to the staging area
git add .

# Commit the changes
git commit -m "Update website content"

# Delete the main branch
git branch -D main

# Rename the current branch to main
git branch -m main

# Finally, force update your repository
git push -f origin main
