@echo off
set "PYTHONPATH=%~dp0"
set "PYTHONIOENCODING=utf-8"
"D:\tools\conda310\envs\shop\python.exe" "%~dp0manager\shop_manager.py" %*
