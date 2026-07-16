@echo off
chcp 65001 >nul
echo =========================================
echo Mongolia Multi-Source News Search
echo 12 sites configured
echo =========================================
echo.
start "" "C:\Users\sniper001\AppData\Local\Programs\Python\Python311\python.exe" "C:\Users\sniper001\police_search\search_server.py"
echo Search server at http://127.0.0.1:8765
echo.
echo Commands:
echo   Empty search + Enter = Live Fetch latest news from all sources
echo   Keywords + Enter     = Search local database
echo.
pause
