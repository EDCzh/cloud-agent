##
文本嵌入模型为text-embedding-v2
OrchestratorAgent的模型名为： qwen-plus
product_agent的意图识别工具调用总是走的知识图谱 解决措施
few-shot 修改提示词
def get_db_connection():
    """获取远程 MySQL 连接。在生产环境中应使用连接池。"""
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "YOUR_MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", "YOUR_MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE", "cloud_platform"),
        cursorclass=pymysql.cursors.DictCursor # **让查询结果以字典形式返回，方便转 JSON**
    )
长期记忆中Top_k为5
环境搭建：