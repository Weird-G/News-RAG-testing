"""
run_allure.py - Allure 测试报告生成脚本

本脚本用于运行 pytest 测试并生成 Allure 可视化测试报告。
支持一键执行所有测试、生成报告、启动报告服务等功能。

使用方法:
    python scripts/run_allure.py run            # 运行所有测试
    python scripts/run_allure.py generate        # 生成报告
    python scripts/run_allure.py serve           # 启动报告服务
    python scripts/run_allure.py all             # 一键运行+生成+服务

依赖:
    - allure-pytest: pytest 插件，用于生成 Allure 结果
    - allure 命令行工具: 用于生成可视化报告

注意: 需要先安装 allure 命令行工具（参考 Allure 官方文档）
"""

import os
import sys
import subprocess
import argparse

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 测试报告目录
REPORT_DIR = os.path.join(PROJECT_ROOT, "test_reports")
# Allure 结果目录
ALLURE_RESULTS_DIR = os.path.join(REPORT_DIR, "allure-results")
# Allure 报告输出目录
ALLURE_REPORT_DIR = os.path.join(REPORT_DIR, "allure-report")


def run_tests(test_path=None):
    """
    运行 pytest 测试并生成 Allure 结果
    
    Args:
        test_path: 测试路径，为 None 时运行所有测试
    
    Returns:
        int: 测试退出码（0 表示成功）
    """
    # 确保目录存在
    os.makedirs(ALLURE_RESULTS_DIR, exist_ok=True)
    
    # 构建命令
    cmd = [
        sys.executable, "-m", "pytest",
        test_path or "tests/",
        "-v",                                    # 详细输出
        "--tb=short",                            # 简短回溯
        "--alluredir", ALLURE_RESULTS_DIR,       # Allure 结果目录
        "-p", "no:warnings"                      # 禁用警告
    ]
    
    print(f"执行命令: {' '.join(cmd)}")
    print("=" * 60)
    
    # 运行测试
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=False
    )
    
    return result.returncode


def generate_report():
    """
    从 Allure 结果生成可视化报告
    
    需要 allure 命令行工具已安装
    
    Returns:
        bool: 是否成功生成报告
    """
    # 检查 allure 是否已安装
    try:
        # 清理旧报告
        if os.path.exists(ALLURE_REPORT_DIR):
            import shutil
            shutil.rmtree(ALLURE_REPORT_DIR)
        
        # 生成新报告
        cmd = [
            "allure", "generate",
            ALLURE_RESULTS_DIR,
            "-o", ALLURE_REPORT_DIR,
            "--clean"
        ]
        
        print(f"生成报告命令: {' '.join(cmd)}")
        print("=" * 60)
        
        subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)
        print(f"\n✓ 报告已生成: {ALLURE_REPORT_DIR}")
        return True
        
    except FileNotFoundError:
        print("\n✗ 错误: 未找到 allure 命令行工具")
        print("请先安装 allure:")
        print("  1. 访问 https://allurereport.org/docs/install/")
        print("  2. Windows 用户可使用: scoop install allure")
        print("  3. 或下载 zip 包并配置环境变量")
        return False
    except subprocess.CalledProcessError as e:
        print(f"\n✗ 报告生成失败: {e}")
        return False


def serve_report(host="localhost", port=8088):
    """
    启动 Allure 报告服务
    
    Args:
        host: 服务主机地址
        port: 服务端口
    """
    # 检查报告是否存在
    if not os.path.exists(ALLURE_REPORT_DIR):
        print("报告不存在，正在生成...")
        if not generate_report():
            return
    
    print(f"启动报告服务: http://{host}:{port}")
    print("按 Ctrl+C 停止服务\n")
    
    try:
        cmd = [
            "allure", "open",
            "-h", host,
            "-p", str(port),
            ALLURE_REPORT_DIR
        ]
        subprocess.run(cmd, cwd=PROJECT_ROOT)
    except FileNotFoundError:
        print("错误: 未找到 allure 命令行工具")
        print("请先安装 allure: scoop install allure")
        # 尝试用 Python 启动简单 HTTP 服务
        print(f"\n备选方案: 直接打开 {ALLURE_REPORT_DIR}/index.html")
        import webbrowser
        index_file = os.path.join(ALLURE_REPORT_DIR, "index.html")
        if os.path.exists(index_file):
            webbrowser.open(f"file://{index_file}")


def main():
    """主函数：解析命令行参数并执行相应操作"""
    parser = argparse.ArgumentParser(
        description="Allure 测试报告生成工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python scripts/run_allure.py run              # 运行所有测试
    python scripts/run_allure.py run -t tests/test_api/  # 运行指定目录测试
    python scripts/run_allure.py generate          # 生成报告
    python scripts/run_allure.py serve             # 启动报告服务
    python scripts/run_allure.py all               # 一键执行全部流程
        """
    )
    
    parser.add_argument(
        "action",
        choices=["run", "generate", "serve", "all"],
        help="执行的操作: run(运行测试), generate(生成报告), serve(启动服务), all(全部)"
    )
    
    parser.add_argument(
        "-t", "--test-path",
        default=None,
        help="测试路径，默认运行所有测试"
    )
    
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=8088,
        help="报告服务端口（默认 8088）"
    )
    
    args = parser.parse_args()
    
    if args.action == "run":
        print("▶ 运行测试...")
        exit_code = run_tests(args.test_path)
        if exit_code == 0:
            print("\n✓ 所有测试通过！")
        else:
            print(f"\n⚠ 部分测试失败（退出码: {exit_code}）")
    
    elif args.action == "generate":
        print("▶ 生成 Allure 报告...")
        generate_report()
    
    elif args.action == "serve":
        print("▶ 启动报告服务...")
        serve_report(port=args.port)
    
    elif args.action == "all":
        print("▶ 一键执行所有流程...")
        print("\n" + "=" * 60)
        print("步骤 1/3: 运行测试")
        print("=" * 60)
        exit_code = run_tests(args.test_path)
        
        print("\n" + "=" * 60)
        print("步骤 2/3: 生成报告")
        print("=" * 60)
        generate_report()
        
        print("\n" + "=" * 60)
        print("步骤 3/3: 启动报告服务")
        print("=" * 60)
        print(f"\n报告已生成在: {ALLURE_REPORT_DIR}")
        print(f"直接打开: {os.path.join(ALLURE_REPORT_DIR, 'index.html')}")
        print("\n要启动报告服务，请运行:")
        print(f"  python scripts/run_allure.py serve -p {args.port}")


if __name__ == "__main__":
    main()
