import logging
from logging import StreamHandler
import sys
import botpy
import asyncio
import os
import time
import threading
import random
import re
import copy
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from config.main import account_config
from botpy.types.message import Ark, ArkKv
from botpy.types.message import MarkdownPayload, MessageMarkdownParams
from botpy.message import GroupMessage, Message, DirectMessage
from botpy.types.message import Message, Embed
from botpy.message import C2CMessage

# ====================== 动态随机颜色日志 ======================
class DynamicColorFormatter(logging.Formatter):
    # 可选的 ANSI 颜色（加粗 + 不同颜色）
    COLORS = [
        "\033[1;32m",  # 亮绿
        "\033[1;33m",  # 亮黄
        "\033[1;34m",  # 亮蓝
        "\033[1;35m",  # 亮紫
        "\033[1;36m",  # 亮青
        "\033[1;92m",  # 亮浅绿
        "\033[1;93m",  # 亮浅黄
        "\033[1;94m",  # 亮浅蓝
        "\033[1;95m",  # 亮浅紫
        "\033[1;96m",  # 亮浅青
    ]
    RESET = "\033[0m"

    def format(self, record):
        # 随机选择一个颜色
        color = random.choice(self.COLORS)
        message = super().format(record)
        return f"{color}{message}{self.RESET}"

def setup_dynamic_logging():
    # 获取根日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 清除所有现有处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 添加动态颜色处理器
    console = StreamHandler(sys.stdout)
    console.setFormatter(DynamicColorFormatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(console)

# 初始化日志系统
setup_dynamic_logging()

# ====================== ANSI 颜色代码 ======================
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    MAGENTA = '\033[35m'
    BG_RED = '\033[41m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'

# ====================== 词库引擎核心 ======================
class ParallelWordLibrary:
    def __init__(self, dir_path="words", check_interval=5):
        self.dir_path = os.path.abspath(dir_path)
        self.check_interval = max(check_interval, 1)
        self._libraries = {}
        self._running = True
        self._lib_lock = threading.Lock()
        
        os.makedirs(self.dir_path, exist_ok=True)
        self._start_parallel_load()
        
        threading.Thread(
            target=self._global_monitor,
            daemon=True,
            name="GlobalMonitor"
        ).start()

    def _start_parallel_load(self):
        """并行加载所有词库文件，统计加载时长"""
        def load_file(file_path):
            start_time = time.time()
            lib = QALibrary(file_path)
            load_time = time.time() - start_time
            with self._lib_lock:
                self._libraries[file_path] = lib
            return lib, load_time

        try:
            with ThreadPoolExecutor() as executor:
                files = [
                    os.path.join(self.dir_path, f)
                    for f in os.listdir(self.dir_path)
                    if f.endswith(".liq")
                ]
                futures = {executor.submit(load_file, f): f for f in files}
                for future in futures:
                    file_path = futures[future]
                    try:
                        lib, load_time = future.result()
                        print(f"{Colors.YELLOW}[{os.path.basename(file_path)}]"
                              f"{Colors.END} {Colors.GREEN}装载完成{Colors.END} | "
                              f"指令数: {len(lib.qa_pairs)} | "
                              f"耗时: {load_time:.3f}s")
                    except Exception as e:
                        print(f"{Colors.RED}装载失败 [{os.path.basename(file_path)}]: {e}{Colors.END}")

        except FileNotFoundError:
            print(f"{Colors.RED}目录不存在: {self.dir_path}{Colors.END}")

    def _global_monitor(self):
        """监控新增和删除的文件"""
        while self._running:
            try:
                # 获取当前目录下的所有词库文件
                current_files = set()
                try:
                    current_files = {
                        os.path.join(self.dir_path, f)
                        for f in os.listdir(self.dir_path)
                        if f.endswith(".liq")
                    }
                except FileNotFoundError:
                    print(f"{Colors.RED}监控目录被删除: {self.dir_path}{Colors.END}")
                    time.sleep(self.check_interval)
                    continue

                # 检查新增文件
                new_files = current_files - set(self._libraries.keys())
                if new_files:
                    print(f"{Colors.CYAN}发现新词库: {', '.join(os.path.basename(f) for f in new_files)}{Colors.END}")
                    self._start_parallel_load()

                # 检查被删除的文件
                with self._lib_lock:
                    deleted_files = set(self._libraries.keys()) - current_files
                    if deleted_files:
                        for file_path in deleted_files:
                            print(f"{Colors.MAGENTA}词库被删除: {os.path.basename(file_path)}{Colors.END}")
                            self._libraries[file_path].close()
                            del self._libraries[file_path]

                time.sleep(self.check_interval)
            except Exception as e:
                print(f"{Colors.RED}监控异常: {e}{Colors.END}")
                time.sleep(5)

    def find_command(self, command):
        """并行查询所有词库，每个文件只返回第一个匹配结果"""
        start_time = time.time()
        results = []
        
        def query(lib):
            start = time.time()
            reply_info = lib.find_command(command)
            if reply_info:
                cost = (time.time() - start) * 1000
                return {
                    'file': os.path.basename(lib.file_path),
                    'reply': reply_info['reply'],
                    'cost': cost,
                    'line': reply_info['line']
                }
            return None

        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(query, lib): lib 
                for lib in self._libraries.values()
            }
            
            for future in futures:
                try:
                    if result := future.result():
                        results.append(result)
                except Exception as e:
                    print(f"{Colors.RED}查询异常: {e}{Colors.END}")
        
        total_cost = (time.time() - start_time) * 1000
        return results, total_cost

    def close(self):
        self._running = False
        for lib in self._libraries.values():
            lib.close()

class QALibrary:
    """问答词库管理"""
    def __init__(self, file_path):
        self.file_path = file_path
        self.qa_pairs = []
        self._lock = threading.Lock()
        self._last_modified = 0
        self._running = True
        self._load_data()
        self._start_monitor()

    def _parse_content(self, content):
        """解析问答数据，保持原始顺序"""
        qa_pairs = []
        current_command = None
        current_reply = []
        line_num = 1
        
        for line in content.splitlines():
            line = line.strip()
            if not line:
                if current_command and current_reply:
                    reply = ''.join(current_reply)
                    qa_pairs.append({
                        'commands': current_command['aliases'],
                        'reply': reply,
                        'line': current_command['line']
                    })
                current_command = None
                current_reply = []
                line_num += 1
                continue
            
            if not current_command:
                commands = [cmd.strip() for cmd in line.split('|') if cmd.strip()]
                if commands:
                    current_command = {
                        'aliases': commands,
                        'line': line_num
                    }
            else:
                processed_line = line.replace('\\n', '\n')
                current_reply.append(processed_line)
            
            line_num += 1
        
        if current_command and current_reply:
            reply = ''.join(current_reply)
            qa_pairs.append({
                'commands': current_command['aliases'],
                'reply': reply,
                'line': current_command['line']
            })
        
        return qa_pairs

    def _load_data(self):
        """加载/重载数据"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            with self._lock:
                self.qa_pairs = self._parse_content(content)
                self._last_modified = os.path.getmtime(self.file_path)
                
        except FileNotFoundError:
            print(f"{Colors.RED}词库被删除: {os.path.basename(self.file_path)}{Colors.END}")
            self.close()
        except Exception as e:
            print(f"{Colors.RED}加载失败 [{os.path.basename(self.file_path)}]: {e}{Colors.END}")

    def _start_monitor(self):
        """启动文件监控"""
        def monitor():
            while self._running:
                try:
                    current_mtime = os.path.getmtime(self.file_path)
                    if current_mtime > self._last_modified:
                        print(f"{Colors.YELLOW}[{os.path.basename(self.file_path)}]"
                              f"{Colors.END} {Colors.CYAN}热更新中...{Colors.END}")
                        self._load_data()
                    time.sleep(1)
                except FileNotFoundError:
                    print(f"{Colors.RED}词库被删除: {os.path.basename(self.file_path)}{Colors.END}")
                    self.close()
                    break
                except Exception as e:
                    print(f"{Colors.RED}监控异常 [{os.path.basename(self.file_path)}]: {e}{Colors.END}")
                    time.sleep(5)

        threading.Thread(
            target=monitor,
            daemon=True,
            name=f"Monitor-{os.path.basename(self.file_path)}"
        ).start()

    def find_command(self, command):
        """查询指令，返回第一个匹配的结果"""
        with self._lock:
            for qa in self.qa_pairs:
                if command in qa['commands']:
                    return {
                        'reply': qa['reply'],
                        'line': qa['line']
                    }
            return None

    def close(self):
        self._running = False

async def process_reply(reply, cost, line, message, member_openid, group_openid, self, message_type):
    """处理回复中的函数"""
    if re.findall("\$复制 (.*?) (.*?)\$", reply):
        # 使用正则表达式匹配
        pattern = r'\$复制 (.*?) (.*?)\$'
        matches = re.findall(pattern, reply)
        for match in matches:
            if not match[1].isdigit():
                pass
            else:
                blank = ""
                for i in range(0,int(match[1])):
                    blank = f"{blank}{match[0]}"
                reply = reply.replace(f"$复制 {match[0]} {match[1]}$", blank)
                
    if re.findall("\$回调 (.*?)\$", reply):
        # 使用正则表达式匹配
        pattern = r'\$回调 (.*?)\$'
        matches = re.findall(pattern, reply)
        for match in matches:
            message.content = '[内部]' + str(match)
            call_back = True
            call_back_answer = await message_dealwith(self, message, message_type, call_back)
            if call_back_answer == None:
                call_back_answer = ''
            reply = reply.replace(f"$回调 {match}$", call_back_answer)
            
    if re.findall(r"\$调用", reply):
        # 处理所有调用格式（延迟和即时）
        matches = re.findall(r'\$调用 (?:(\d+) )?(.*?)\$', reply)
        
        for match in matches:
            delay_str, content = match
            reply = reply.replace(f"$调用 {delay_str+' ' if delay_str else ''}{content}$", "")
            
            async def execute_call(msg_content=content, delay=delay_str):
                try:
                    if delay:
                        await asyncio.sleep(int(delay))
                    # 创建安全的上下文环境
                    original_content = message.content
                    try:
                        message.content = msg_content
                        await message_dealwith(self, message, message_type, False)
                    finally:
                        message.content = original_content
                except Exception as e:
                    print(f"{Colors.RED}调用执行失败: {e}{Colors.END}")
            
            asyncio.create_task(execute_call())
    
    """处理回复中的变量"""
    variables = {
        '%匹配耗时%': f"{cost:.2f}",
        '%当前行%': str(line),
        '%QQ%': member_openid,
        '%id%': member_openid,
        '%群号%': group_openid,
        '%groupid%': group_openid,
        '%空格%': ' '
    }
    
    for var, val in variables.items():
        reply = reply.replace(var, val)
    
    return reply

# ====================== 回复处理 ======================
async def answer_dealwith(self, answer_msg, answer_type, message_type, message, member_openid):
    number_seq = random.randint(1, 100)
    if message_type == "group":
        if answer_type == "string":
            await message._api.post_group_message(
                group_openid=message.group_openid,
                msg_type=0,
                msg_id=message.id,
                msg_seq=number_seq,
                content=answer_msg
            )
        elif answer_type == "music":
            uploadMedia = await message._api.post_group_file(group_openid=message.group_openid, file_type=3, url=answer_msg)
            await message._api.post_group_message(group_openid=message.group_openid,msg_type=7, msg_id=message.id, msg_seq=number_seq,media=uploadMedia)

    elif message_type == "friend":
        if answer_type == "string":
            await message._api.post_c2c_message(
                openid=message.author.user_openid, 
                msg_type=0, 
                msg_seq=number_seq,
                msg_id=message.id, 
                content=answer_msg
           )
        elif answer_type == "picture":
            uploadMedia = await message._api.post_c2c_file(
                openid=message.author.user_openid, 
                file_type=1,
                url=answer_msg
            )
            await message._api.post_c2c_message(
                openid=message.author.user_openid,
                msg_type=7,
                msg_id=message.id,
                msg_seq=number_seq,
                media=uploadMedia
            )

    elif message_type == "channel":
        if answer_type == "string":
            await message.reply(
                content=answer_msg
            )

    elif message_type == "channel_friend":
        if answer_type == "string":
            await message.reply(
                content=answer_msg
            )

# ====================== 消息处理 ======================
async def message_dealwith(self, message, message_type, call_back):
    message_type_list = {
        'group': '群组',
        'channel': '频道',
        'friend': '好友',
        'channel_friend': '频道私信'
    }
    print(f"{Colors.GREEN}接收到{message_type_list[message_type]}消息: {message.content}{Colors.END}")
    
    if message.content == None:
        message.content = ""

    answer_type = "string"
    
    if message_type == "group":
        member_openid = message.author.member_openid
        group_openid = message.group_openid
    elif message_type == "friend":
        member_openid = message.author.user_openid
        group_openid = message.author.user_openid
    elif message_type == "channel":
        member_openid = message.author.id
        group_openid = message.author.id
        pattern = r"<@!(\d+)>"
        match = re.search(pattern, message.content)
        if match:
            bot_id = match.group(1)
        message.content = message.content.replace(f"<@!{bot_id}>", "")
    elif message_type == "channel_friend":
        member_openid = message.author.id
        group_openid = message.author.id
        
    cmd = message.content.strip()
    
    results, total_cost = library.find_command(cmd)
    
    if not results:
        return
    
    for result in results:
        processed_reply = await process_reply(
            result['reply'],
            result['cost'],
            result['line'],
            message,
            member_openid,
            group_openid,
            self, 
            message_type
        )
        if call_back == False:
            answer_msg = processed_reply
            await answer_dealwith(self, answer_msg, answer_type, message_type, message, member_openid)
            print(f"{Colors.GREEN}回复消息: {answer_msg}{Colors.END}")
        else:
            return processed_reply
        
    print(f"{Colors.MAGENTA}总匹配耗时: {total_cost:.2f}ms{Colors.END}")

# ====================== 主程序 ======================
class MyClient(botpy.Client):
    async def on_group_at_message_create(self, message: GroupMessage):
        if '[内部]' in message.content:
            pass
        else:
            message_type = "group"
            call_back = False
            await message_dealwith(self, message, message_type, call_back)

    async def on_c2c_message_create(self, message: C2CMessage):
        if '[内部]' in message.content:
            pass
        else:
            message_type = "friend"
            call_back = False
            await message_dealwith(self, message, message_type, call_back)

    async def on_at_message_create(self, message: Message):
        if '[内部]' in message.content:
            pass
        else:
            message_type = "channel"
            call_back = False
            await message_dealwith(self, message, message_type, call_back)

    async def on_direct_message_create(self, message: DirectMessage):
        if '[内部]' in message.content:
            pass
        else:
            message_type = "channel_friend"
            call_back = False
            await message_dealwith(self, message, message_type, call_back)
        
if __name__ == "__main__":
    import Main
else:
    print(f"{Colors.MAGENTA}正在装载词库...{Colors.END}")
    library = ParallelWordLibrary()
    intents = botpy.Intents.default()
    sandbox_type = False
    # 如果沙箱模式已开启
    if account_config()[2] == 1:
        sandbox_type = True
        print(f"{Colors.YELLOW}沙箱模式已开启{Colors.END}")
    client = MyClient(intents=intents, is_sandbox=sandbox_type)
    client.run(appid=account_config()[0], secret=account_config()[1])