FROM python:3.11-slim

WORKDIR /app

# 使用清华源加速，并验证 Flask 安装
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    && python -c "import flask; print('Flask installed successfully')"

# 复制项目文件
COPY . .

# 创建必要目录
RUN mkdir -p /app/data /app/logs /app/static

EXPOSE 5001

CMD ["python", "app.py"]