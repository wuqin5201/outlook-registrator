@echo off
chcp 65001 >nul
echo 正在安装依赖...
pip install -r requirements.txt
python -m playwright install chromium
echo.
echo 安装完成,按任意键开始注册...
pause >nul
python outlook_registrator.py
pause
