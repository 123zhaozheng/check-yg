# -*- coding: utf-8 -*-
"""
MinerU API Server on Modal

直接使用 MinerU 官方的 mineru-api 服务

部署步骤:
1. 安装 modal: pip install modal
2. 登录 modal: modal token new
3. 部署服务: modal deploy modal_mineru_server.py
4. 获取 URL 后配置到项目设置中

服务会自动获得一个公网 URL，类似:
https://your-workspace--mineru-api-server.modal.run
"""

import modal

app = modal.App("mineru-api-server")

# 定义镜像：安装 MinerU
mineru_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1-mesa-glx", "libglib2.0-0")
    .pip_install("uv")
    .run_commands("uv pip install --system 'mineru[all]'")
)


@app.function(
    image=mineru_image,
    gpu="L4",
    timeout=600,
    memory=32768,
)
@modal.concurrent(max_inputs=5)
@modal.web_server(port=8000, startup_timeout=120)
def mineru_server():
    """直接启动 MinerU 官方 API 服务"""
    import subprocess
    # 使用 mineru-api 官方命令启动服务
    subprocess.Popen([
        "mineru-api",
        "--host", "0.0.0.0",
        "--port", "8000"
    ])
