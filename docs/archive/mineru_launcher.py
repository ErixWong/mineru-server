#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MinerU 启动脚本 - 支持 OpenAI 兼容 API

本脚本用于启动 MinerU，并配置使用第三方 OpenAI 兼容接口，
让您可以使用远程 LLM/VLM 服务，而无需在本地加载推理模型。

使用方法:
    python mineru_launcher.py --input /path/to/pdf --output /path/to/output
    python mineru_launcher.py --input /path/to/pdf --output /path/to/output --server-url http://localhost:8000/v1

环境变量:
    MINERU_VLM_API_KEY: VLM 服务的 API 密钥 (默认: your_api_key)
    MINERU_VLM_BASE_URL: VLM 服务的基础 URL (默认: http://localhost:8000/v1)
    MINERU_VLM_MODEL: 使用的模型名称 (默认: qwen2.5-vl-7b-instruct)
    MINERU_VLM_BACKEND: 后端类型 - http-client, vlm-http-client, hybrid-http-client (默认: vlm-http-client)

使用示例:
    # 使用本地 vLLM 服务器
    export MINERU_VLM_BASE_URL=http://localhost:8000/v1
    export MINERU_VLM_MODEL=Qwen/Qwen2.5-VL-7B-Instruct
    python mineru_launcher.py -p document.pdf -o output/

    # 使用 OpenAI 兼容的云服务
    export MINERU_VLM_API_KEY=sk-xxxxxxxx
    export MINERU_VLM_BASE_URL=https://api.openai.com/v1
    export MINERU_VLM_MODEL=gpt-4o
    python mineru_launcher.py -p document.pdf -o output/ --backend vlm-http-client

    # 使用混合后端 (本地 OCR + 远程 VLM)
    export MINERU_VLM_BASE_URL=http://localhost:8000/v1
    python mineru_launcher.py -p document.pdf -o output/ --backend hybrid-http-client
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from typing import Optional, List


def get_env_or_default(env_var: str, default: str) -> str:
    """获取环境变量，如果不存在则返回默认值"""
    return os.getenv(env_var, default)


def setup_vlm_environment(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """
    设置 VLM 配置的环境变量
    
    参数:
        api_key: VLM 服务的 API 密钥
        base_url: VLM 服务的基础 URL (OpenAI 兼容端点)
        model: 使用的模型名称
        
    返回:
        需要设置的环境变量字典
    """
    env_vars = {}
    
    # VLM API 配置
    env_vars['MINERU_VLM_API_KEY'] = api_key or get_env_or_default('MINERU_VLM_API_KEY', 'your_api_key')
    env_vars['MINERU_VLM_BASE_URL'] = base_url or get_env_or_default('MINERU_VLM_BASE_URL', 'http://localhost:8000/v1')
    env_vars['MINERU_VLM_MODEL'] = model or get_env_or_default('MINERU_VLM_MODEL', 'qwen2.5-vl-7b-instruct')
    
    # 可选: 设置额外的 VLM 参数
    env_vars['MINERU_VLM_MAX_CONCURRENCY'] = get_env_or_default('MINERU_VLM_MAX_CONCURRENCY', '100')
    env_vars['MINERU_VLM_HTTP_TIMEOUT'] = get_env_or_default('MINERU_VLM_HTTP_TIMEOUT', '600')
    env_vars['MINERU_VLM_MAX_RETRIES'] = get_env_or_default('MINERU_VLM_MAX_RETRIES', '3')
    
    return env_vars


def build_mineru_command(
    input_path: str,
    output_path: str,
    backend: str = "vlm-http-client",
    server_url: Optional[str] = None,
    method: str = "auto",
    lang: str = "ch",
    formula_enable: bool = True,
    table_enable: bool = True,
    start_page: int = 0,
    end_page: Optional[int] = None,
    extra_args: Optional[List[str]] = None,
) -> List[str]:
    """
    构建 MinerU CLI 命令
    
    参数:
        input_path: 输入 PDF 或图片文件路径
        output_path: 输出目录路径
        backend: 使用的后端
        server_url: VLM 服务器 URL (用于 http-client 后端)
        method: 解析方法 (auto, txt, ocr)
        lang: 语言代码
        formula_enable: 启用公式解析
        table_enable: 启用表格解析
        start_page: 起始页码 (从 0 开始)
        end_page: 结束页码 (从 0 开始，None 表示所有页面)
        extra_args: 传递给 MinerU 的额外参数
        
    返回:
        命令参数列表
    """
    cmd = [
        sys.executable, "-m", "mineru.cli.client",
        "-p", input_path,
        "-o", output_path,
        "-b", backend,
        "-m", method,
        "-l", lang,
    ]
    
    # 为 http-client 后端添加服务器 URL
    if server_url and "http-client" in backend:
        cmd.extend(["-u", server_url])
    
    # 添加公式和表格选项
    if formula_enable:
        cmd.append("-f")
    if table_enable:
        cmd.append("-t")
    
    # 添加页码范围
    if start_page > 0:
        cmd.extend(["-s", str(start_page)])
    if end_page is not None:
        cmd.extend(["-e", str(end_page)])
    
    # 添加额外参数
    if extra_args:
        cmd.extend(extra_args)
    
    return cmd


def launch_mineru(
    input_path: str,
    output_path: str,
    backend: str = "vlm-http-client",
    server_url: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    method: str = "auto",
    lang: str = "ch",
    formula_enable: bool = True,
    table_enable: bool = True,
    start_page: int = 0,
    end_page: Optional[int] = None,
    extra_args: Optional[List[str]] = None,
    dry_run: bool = False,
) -> int:
    """
    启动 MinerU
    
    参数:
        input_path: 输入文件路径
        output_path: 输出目录路径
        backend: 使用的后端
        server_url: VLM 服务器 URL
        api_key: VLM 服务的 API 密钥
        base_url: VLM 服务的基础 URL
        model: 模型名称
        method: 解析方法
        lang: 语言代码
        formula_enable: 启用公式解析
        table_enable: 启用表格解析
        start_page: 起始页码
        end_page: 结束页码
        extra_args: 额外参数
        dry_run: 如果为 True，只打印命令而不执行
        
    返回:
        MinerU 进程的退出代码
    """
    # 设置环境变量
    env_vars = setup_vlm_environment(api_key, base_url, model)
    
    # 确定服务器 URL
    effective_server_url = server_url or env_vars['MINERU_VLM_BASE_URL']
    
    # 构建命令
    cmd = build_mineru_command(
        input_path=input_path,
        output_path=output_path,
        backend=backend,
        server_url=effective_server_url,
        method=method,
        lang=lang,
        formula_enable=formula_enable,
        table_enable=table_enable,
        start_page=start_page,
        end_page=end_page,
        extra_args=extra_args,
    )
    
    # 打印配置
    print("=" * 60)
    print("MinerU 启动配置")
    print("=" * 60)
    print(f"输入文件: {input_path}")
    print(f"输出目录: {output_path}")
    print(f"后端类型: {backend}")
    print(f"服务器 URL: {effective_server_url}")
    print(f"模型名称: {env_vars['MINERU_VLM_MODEL']}")
    print(f"解析方法: {method}")
    print(f"文档语言: {lang}")
    print("-" * 60)
    print("环境变量:")
    for key, value in env_vars.items():
        # 隐藏 API 密钥
        display_value = value if key != 'MINERU_VLM_API_KEY' else '*' * len(value)
        print(f"  {key}={display_value}")
    print("-" * 60)
    print(f"命令: {' '.join(cmd)}")
    print("=" * 60)
    
    if dry_run:
        print("\n[试运行] 命令未执行")
        return 0
    
    # 准备环境
    env = os.environ.copy()
    env.update(env_vars)
    
    # 执行 MinerU
    print("\n正在启动 MinerU...\n")
    try:
        result = subprocess.run(cmd, env=env, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\n\n用户中断")
        return 130
    except Exception as e:
        print(f"\n执行 MinerU 时出错: {e}")
        return 1


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="启动 MinerU 并配置 OpenAI 兼容 API 支持",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 基本用法 - 使用本地 vLLM 服务器
  python mineru_launcher.py -p document.pdf -o output/

  # 使用自定义服务器 URL
  python mineru_launcher.py -p document.pdf -o output/ -u http://localhost:8000/v1

  # 使用混合后端 (本地 OCR + 远程 VLM)
  python mineru_launcher.py -p document.pdf -o output/ --backend hybrid-http-client

  # 指定语言并禁用表格解析
  python mineru_launcher.py -p document.pdf -o output/ -l en --no-table

  # 处理指定页码范围
  python mineru_launcher.py -p document.pdf -o output/ -s 5 -e 10

  # 试运行 - 查看命令但不执行
  python mineru_launcher.py -p document.pdf -o output/ --dry-run
        """
    )
    
    # 必需参数
    parser.add_argument(
        "-p", "--path",
        required=True,
        help="输入 PDF 或图片文件/目录的路径"
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="输出目录路径"
    )
    
    # VLM/服务器配置
    parser.add_argument(
        "-u", "--server-url",
        default=None,
        help="VLM 服务器 URL (OpenAI 兼容 API 端点，例如: http://localhost:8000/v1)"
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="VLM 服务的 API 密钥 (或设置 MINERU_VLM_API_KEY 环境变量)"
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="VLM 服务的基础 URL (或设置 MINERU_VLM_BASE_URL 环境变量)"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="使用的模型名称 (或设置 MINERU_VLM_MODEL 环境变量)"
    )
    
    # 后端选择
    parser.add_argument(
        "-b", "--backend",
        choices=["vlm-http-client", "hybrid-http-client", "vlm-auto-engine", "hybrid-auto-engine", "pipeline"],
        default="vlm-http-client",
        help="""
使用的后端类型:
  - vlm-http-client: 通过 OpenAI 兼容 API 使用远程 VLM (高精度，需要 server_url)
  - hybrid-http-client: 本地 OCR + 远程 VLM (平衡速度和精度，需要 server_url)
  - vlm-auto-engine: 本地 VLM 自动引擎 (需要本地 GPU)
  - hybrid-auto-engine: 本地混合管道 (需要本地 GPU)
  - pipeline: 传统管道模式 (无 VLM)
默认: vlm-http-client
        """
    )
    
    # 解析选项
    parser.add_argument(
        "-m", "--method",
        choices=["auto", "txt", "ocr"],
        default="auto",
        help="解析方法: auto (自动检测), txt (文本), ocr (图像). 默认: auto"
    )
    parser.add_argument(
        "-l", "--lang",
        choices=["ch", "ch_server", "ch_lite", "en", "korean", "japan", "chinese_cht", 
                 "ta", "te", "ka", "th", "el", "latin", "arabic", "east_slavic", 
                 "cyrillic", "devanagari"],
        default="ch",
        help="文档语言. 默认: ch (中文)"
    )
    
    # 功能开关
    parser.add_argument(
        "-f", "--formula",
        action="store_true",
        default=True,
        help="启用公式解析 (默认: 启用)"
    )
    parser.add_argument(
        "--no-formula",
        action="store_false",
        dest="formula",
        help="禁用公式解析"
    )
    parser.add_argument(
        "-t", "--table",
        action="store_true",
        default=True,
        help="启用表格解析 (默认: 启用)"
    )
    parser.add_argument(
        "--no-table",
        action="store_false",
        dest="table",
        help="禁用表格解析"
    )
    
    # 页码范围
    parser.add_argument(
        "-s", "--start",
        type=int,
        default=0,
        help="起始页码 (从 0 开始，默认: 0)"
    )
    parser.add_argument(
        "-e", "--end",
        type=int,
        default=None,
        help="结束页码 (从 0 开始，包含，默认: 最后一页)"
    )
    
    # 其他选项
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印命令而不执行"
    )
    parser.add_argument(
        "--extra-args",
        nargs=argparse.REMAINDER,
        help="传递给 MinerU CLI 的额外参数"
    )
    
    args = parser.parse_args()
    
    # 验证输入路径
    input_path = Path(args.path)
    if not input_path.exists():
        print(f"错误: 输入路径不存在: {args.path}")
        return 1
    
    # 创建输出目录
    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 验证后端要求
    if "http-client" in args.backend and not (args.server_url or os.getenv('MINERU_VLM_BASE_URL')):
        print(f"警告: 后端 '{args.backend}' 需要服务器 URL")
        print("请提供 --server-url 或设置 MINERU_VLM_BASE_URL 环境变量")
        print("示例: --server-url http://localhost:8000/v1")
        if not args.dry_run:
            return 1
    
    # 启动 MinerU
    exit_code = launch_mineru(
        input_path=str(input_path.absolute()),
        output_path=str(output_path.absolute()),
        backend=args.backend,
        server_url=args.server_url,
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        method=args.method,
        lang=args.lang,
        formula_enable=args.formula,
        table_enable=args.table,
        start_page=args.start,
        end_page=args.end,
        extra_args=args.extra_args,
        dry_run=args.dry_run,
    )
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
