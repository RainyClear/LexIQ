#!/data/data/com.termux/files/usr/bin/bash
# Termux一键安装脚本
set -e

echo -e "\033[34m[*] 正在准备环境...\033[0m"

# 安装基础工具
pkg update -y
pkg install -y python wget

# 下载主程序
echo -e "\033[34m[*] 下载主程序...\033[0m"
REPO_URL="https://raw.githubusercontent.com/你的用户名/你的仓库名/main"
wget -O main.py "$REPO_URL/main.py"
wget -O requirements.txt "$REPO_URL/requirements.txt" 2>/dev/null || true

# 安装依赖
echo -e "\033[34m[*] 安装Python依赖...\033[0m"
pip install --upgrade pip
pip install -r requirements.txt --quiet --disable-pip-version-check

# 启动程序
echo -e "\033[32m[✓] 环境准备完成\033[0m"
python main.py