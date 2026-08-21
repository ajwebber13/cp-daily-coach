# push.ps1
# Run from inside C:\temp\cp-coach
# Usage: .\push.ps1

cd $PSScriptRoot

git add .
git commit -m "Replace scoring with TradingView 6-check swing system"
git push

Write-Host "Done. Check GitHub Actions to run a manual test."
