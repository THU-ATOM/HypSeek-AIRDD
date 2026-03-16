# 使用官方 CUDA 11.8 开发版镜像，确保包含 nvcc 等编译工具
FROM nvidia/cuda:11.8.0-devel-ubuntu22.04

# 声明构建时的代理参数 (仅在 build 时生效，不会固化到镜像里)
ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV http_proxy=$HTTP_PROXY
ENV https_proxy=$HTTPS_PROXY

# 设置非交互模式以防 apt-get 卡住
ENV DEBIAN_FRONTEND=noninteractive

# 安装系统基础工具
RUN apt-get update && apt-get install -y \
    wget \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装 Miniconda (设置 Python 3.11 为默认)
# ENV CONDA_DIR=/opt/conda
# RUN wget --quiet https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh && \
#     /bin/bash ~/miniconda.sh -b -p /opt/conda && \
#     rm ~/miniconda.sh
# ENV PATH=$CONDA_DIR/bin:$PATH



# RUN conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main && \
#     conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r && \
#     conda install -y python=3.11 -c defaults && \
#     conda install -y -c conda-forge openbabel && \
#     conda clean -ya
# # RUN conda install -y python=3.11 && conda clean -ya

# # # 安装 OpenBabel
# # RUN conda install -y -c conda-forge openbabel && conda clean -ya

# # 设置工作目录
# WORKDIR /app

# # 复制 pip 依赖文件并安装
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# # 复制本地自定义模块源代码
# # 注意：这要求在执行 docker build 时，Uni-Core 和 ProDy 必须在当前上下文中
# COPY Uni-Core/ ./Uni-Core/
# COPY ProDy/ ./ProDy/

# # 编译安装本地模块
# RUN cd Uni-Core && python setup.py.bak install && cd ..
# # 注意：在 Docker 中通常不需要 -e (editable) 模式，这里去掉了 -e 减小镜像体积并避免源码依赖
# RUN cd ProDy && pip install . && cd ..

# # 复制当前目录下的所有剩余代码 (例如 test.sh, checkpoints, 业务代码等)
# COPY . /app/

# # 清理构建过程中的代理环境变量
# ENV http_proxy=""
# ENV https_proxy=""

# # 默认启动命令 (可选，这里设置为启动 bash)
# CMD ["/bin/bash"]

# ... 前面安装系统工具部分保持不变 ...

# 安装 Miniconda
ENV CONDA_DIR=/opt/conda
RUN wget --quiet https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh && \
    /bin/bash ~/miniconda.sh -b -p $CONDA_DIR && \
    rm ~/miniconda.sh

ENV PATH=$CONDA_DIR/bin:$PATH

# 接受 TOS、配置渠道并安装 Python + OpenBabel
# 将它们放在同一个 RUN 指令中可以显著减少镜像层数
RUN conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main && \
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r && \
    conda config --add channels conda-forge && \
    conda config --set channel_priority strict && \
    conda install -y python=3.11 openbabel && \
    conda clean -ya

WORKDIR /app

# 复制依赖文件并安装 (利用缓存机制)
# 注意：requirements.txt 在 docker/ 子目录中，需要指定相对于 build context 的路径
COPY docker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制并编译本地模块
COPY Uni-Core/ ./Uni-Core/
COPY ProDy/ ./ProDy/
RUN cd Uni-Core && python setup.py.bak install && \
    cd ../ProDy && pip install . && \
    cd ..

# 最后再复制其余业务代码（这样如果业务代码变动，前面的编译层不需要重跑）
COPY . /app/

# 清理环境变量（使用 unset 更彻底）
ENV http_proxy=
ENV https_proxy=

CMD ["/bin/bash"]