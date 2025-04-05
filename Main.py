import sys
import subprocess
import threading
from time import sleep

# 颜色代码（标准ANSI颜色，大多数现代终端都支持）
class Colors:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BOLD = "\033[1m"

# 根据Python版本选择导入方式
try:
    from importlib.metadata import version as get_version  # Python 3.8+
    from importlib.metadata import PackageNotFoundError
except ImportError:
    from pkg_resources import get_distribution as get_version  # 旧版回退
    from pkg_resources import DistributionNotFound as PackageNotFoundError

REQUIRED_PACKAGES = [
    ('qq-botpy', '1.2.1'),
    ('requests', '2.26.0')
]

def install_package(package, min_version):
    # 进度条动画
    def show_spinner():
        chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        message = f"{Colors.YELLOW}正在安装 {Colors.CYAN}{package}>={min_version}{Colors.RESET}"
        while not installed.is_set():
            for char in chars:
                print(f"\r{message} {Colors.MAGENTA}{char}{Colors.RESET}", end='', flush=True)
                sleep(0.1)
    
    installed = threading.Event()
    spinner_thread = threading.Thread(target=show_spinner)
    spinner_thread.daemon = True
    spinner_thread.start()
    
    success = False
    try:
        # 第一次尝试安装
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", 
            f"{package}>={min_version}",
            "--quiet", "--disable-pip-version-check"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        success = True
    except subprocess.CalledProcessError:
        try:
            # 第二次尝试安装
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                f"{package}>={min_version}", 
                "--quiet", "--disable-pip-version-check",
                "--break-system-packages", 
                "--ignore-installed"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            success = True
        except subprocess.CalledProcessError:
            pass
    
    installed.set()
    spinner_thread.join()
    
    # 清除进度条
    print("\r" + " " * (len(f"正在安装 {package}>={min_version}") + 15) + "\r", end='')
    
    if success:
        print(f"{Colors.GREEN}✓ 成功安装: {Colors.CYAN}{package}>={min_version}{Colors.RESET}")
    else:
        print(f"{Colors.RED}✗ 安装失败: {Colors.CYAN}{package}>={min_version}{Colors.RESET}")

def parse_version(version_str):
    """将版本字符串转换为可比较的元组"""
    return tuple(map(int, version_str.split('.')[:3]))  # 只比较前三位

def ensure_dependencies():
    print(f"{Colors.BLUE}🔍 正在检查依赖项...{Colors.RESET}")
    for package, min_version in REQUIRED_PACKAGES:
        try:
            installed = get_version(package)
            if isinstance(installed, str):
                installed_version = installed
            else:
                installed_version = installed.version
            
            if parse_version(installed_version) < parse_version(min_version):
                raise ValueError(f"{Colors.RED}需要 {min_version}+，当前 {installed_version}{Colors.RESET}")
            
            print(f"{Colors.GREEN}✔ 已满足: {Colors.CYAN}{package}>={min_version} {Colors.WHITE}({installed_version}){Colors.RESET}")
        except (PackageNotFoundError, ValueError) as e:
            print(f"{Colors.YELLOW}⚠ 需要安装/更新: {Colors.CYAN}{package}>={min_version} {Colors.WHITE}({str(e)}){Colors.RESET}")
            install_package(package, min_version)

try:
    ensure_dependencies()
    print(f"\n{Colors.GREEN}{Colors.BOLD}✨ 所有依赖已就绪，程序开始运行！{Colors.RESET}\n")
    # 开始运行
    import index
    index.main()
except KeyboardInterrupt:
    print(f"\n{Colors.RED}⏹ 用户中断，程序退出。{Colors.RESET}")
    sys.exit(1)
except Exception as e:
    print(f"\n{Colors.RED}❌ 发生错误: {e}{Colors.RESET}")
    sys.exit(1)