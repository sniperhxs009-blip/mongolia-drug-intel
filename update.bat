@echo off
chcp 65001 >nul
echo Updating Mongolia Police News Database...
echo.
"C:\Users\sniper001\AppData\Local\Programs\Python\Python311\python.exe" "C:\Users\sniper001\police_search\crawler.py" update
echo.
echo Done.
pause
