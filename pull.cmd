cd /d %~dp0
git checkout .
git fetch --all
git reset --hard origin/main
git pull