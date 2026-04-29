"""核心 Agent 框架组件。"""

# 延迟导入以避免循环依赖
# from .mcp.mcp_manager import MCPManager
from .workflow.state import AgentOutput, AgentState
# from .workflow.graph_manager import AgentGraphManager
# from .memory.memory_manager import MemoryManager

__all__ = ["AgentOutput", "AgentState"]
