#!/data/data/com.termux/files/usr/bin/bash
# 零依赖一键安装脚本
set -e

# 自动检测并安装缺失工具
install_if_needed() {
    if ! command -v $1 &>/dev/null; then
        echo "正在安装 $1..."
        pkg update -y
        pkg install -y $2
    fi
}

# 1. 确保基础工具存在
install_if_needed curl curl
install_if_needed wget wget
install_if_needed python python

# 2. 下载主程序（兼容多种方式）
download() {
    if command -v curl &>/dev/null; then
        curl -sL "$1"
    elif command -v wget &>/dev/null; then
        wget -qO- "$1"
    else
        echo "错误：无法下载文件" >&2
        exit 1
    fi
}

echo "正在下载主程序..."
download "https://raw.githubusercontent.com/你的用户名/仓库名/main/main.py" > main.py
download "https://raw.githubusercontent.com/你的用户名/仓库名/main/requirements.txt" > requirements.txt 2>/dev/null || true

# 3. 安装Python依赖
echo "正在安装依赖..."
pip install --upgrade pip
pip install -r requirements.txt --quiet --disable-pip-version-check

# 4. 启动程序
python main.py