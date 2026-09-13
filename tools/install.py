from pathlib import Path

import shutil
import subprocess
import sys

try:
    import jsonc
except ModuleNotFoundError as e:
    raise ImportError(
        "Missing dependency 'json-with-comments' (imported as 'jsonc').\n"
        f"Install it with:\n  {sys.executable} -m pip install json-with-comments\n"
        "Or add it to your project's requirements."
    ) from e

from configure import configure_ocr_model


working_dir = Path(__file__).parent.parent.resolve()
install_path = working_dir / Path("install")
version = len(sys.argv) > 1 and sys.argv[1] or "v0.0.1"

# the first parameter is self name
if sys.argv.__len__() < 4:
    print("Usage: python install.py <version> <os> <arch>")
    print("Example: python install.py v1.0.0 win x86_64")
    sys.exit(1)

os_name = sys.argv[2]
arch = sys.argv[3]


def get_dotnet_platform_tag():
    """自动检测当前平台并返回对应的dotnet平台标签"""
    if os_name == "win" and arch == "x86_64":
        platform_tag = "win-x64"
    elif os_name == "win" and arch == "aarch64":
        platform_tag = "win-arm64"
    elif os_name == "macos" and arch == "x86_64":
        platform_tag = "osx-x64"
    elif os_name == "macos" and arch == "aarch64":
        platform_tag = "osx-arm64"
    elif os_name == "linux" and arch == "x86_64":
        platform_tag = "linux-x64"
    elif os_name == "linux" and arch == "aarch64":
        platform_tag = "linux-arm64"
    else:
        print("Unsupported OS or architecture.")
        print("available parameters:")
        print("version: e.g., v1.0.0")
        print("os: [win, macos, linux, android]")
        print("arch: [aarch64, x86_64]")
        sys.exit(1)

    return platform_tag


def install_deps():
    if not (working_dir / "deps" / "bin").exists():
        print('Please download the MaaFramework to "deps" first.')
        print('请先下载 MaaFramework 到 "deps"。')
        sys.exit(1)

    if os_name == "android":
        shutil.copytree(
            working_dir / "deps" / "bin",
            install_path,
            dirs_exist_ok=True,
        )
        shutil.copytree(
            working_dir / "deps" / "share" / "MaaAgentBinary",
            install_path / "MaaAgentBinary",
            dirs_exist_ok=True,
        )
    else:
        shutil.copytree(
            working_dir / "deps" / "bin",
            install_path / "runtimes" / get_dotnet_platform_tag() / "native",
            ignore=shutil.ignore_patterns(
                "*MaaDbgControlUnit*",
                "*MaaThriftControlUnit*",
                "*MaaRpc*",
                "*MaaHttp*",
                "plugins",
                "*.node",
                "*MaaPiCli*",
            ),
            dirs_exist_ok=True,
        )
        shutil.copytree(
            working_dir / "deps" / "share" / "MaaAgentBinary",
            install_path / "libs" / "MaaAgentBinary",
            dirs_exist_ok=True,
        )
        # plugins 目录某些 MaaFramework 发行包可能不存在，做兼容
        plugins_src = working_dir / "deps" / "bin" / "plugins"
        if plugins_src.exists():
            shutil.copytree(
                plugins_src,
                install_path / "plugins" / get_dotnet_platform_tag(),
                dirs_exist_ok=True,
            )
        else:
            print(f"Warning: plugins directory not found: {plugins_src}, skipping.")


def build_agent():
    """
    使用 PyInstaller 将 agent/main.py 打包成单文件 maa_agent.exe。

    - 只在 agent/main.py 存在时构建；
    - 已存在 agent/dist/maa_agent.exe 时跳过，避免重复构建；
    - 构建产物位于 agent/dist/maa_agent.exe。
    """
    agent_dir = working_dir / "agent"
    main_py = agent_dir / "main.py"

    if not main_py.exists():
        print("agent/main.py not found, skipping agent build.")
        return

    dist_exe = agent_dir / "dist" / "maa_agent.exe"
    if dist_exe.exists():
        print(f"Agent already built, skipping: {dist_exe}")
        return

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--name",
        "maa_agent",
        "--distpath",
        str(agent_dir / "dist"),
        "--workpath",
        str(agent_dir / "build"),
        "--specpath",
        str(agent_dir),
        str(main_py),
    ]
    print("Building agent with PyInstaller...")
    print("  " + " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(agent_dir))
    print(f"Agent built: {dist_exe}")


def install_resource():

    configure_ocr_model()

    shutil.copytree(
        working_dir / "assets" / "resource",
        install_path / "resource",
        dirs_exist_ok=True,
    )
    shutil.copy2(
        working_dir / "assets" / "interface.json",
        install_path,
    )

    with open(install_path / "interface.json", "r", encoding="utf-8") as f:
        interface = jsonc.load(f)

    interface["version"] = version

    with open(install_path / "interface.json", "w", encoding="utf-8") as f:
        jsonc.dump(interface, f, ensure_ascii=False, indent=4)


def install_chores():
    for name in ("README.md", "LICENSE"):
        src = working_dir / name
        if src.exists():
            shutil.copy2(src, install_path)
        else:
            print(f"Warning: {name} not found, skipping.")


def install_agent():
    shutil.copytree(
        working_dir / "agent",
        install_path / "agent",
        dirs_exist_ok=True,
    )


if __name__ == "__main__":
    install_deps()
    build_agent()
    install_resource()
    install_chores()
    install_agent()

    print(f"Install to {install_path} successfully.")