"""Shared exceptions."""


class AgentForgeError(Exception):
    """Base application error."""

    def __init__(self, message: str, code: str = "error"):
        self.message = message
        self.code = code
        super().__init__(message)


class NotFoundError(AgentForgeError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, code="not_found")


class ValidationError(AgentForgeError):
    def __init__(self, message: str):
        super().__init__(message, code="validation_error")


class GuardrailError(AgentForgeError):
    def __init__(self, message: str, guardrail: str = "unknown"):
        self.guardrail = guardrail
        super().__init__(message, code="guardrail_failure")


class ProviderError(AgentForgeError):
    def __init__(self, message: str, provider: str = "unknown"):
        self.provider = provider
        super().__init__(message, code="provider_error")


class ToolExecutionError(AgentForgeError):
    def __init__(self, message: str, tool: str = "unknown"):
        self.tool = tool
        super().__init__(message, code="tool_error")


class MCPError(AgentForgeError):
    def __init__(self, message: str, server: str = "unknown"):
        self.server = server
        super().__init__(message, code="mcp_error")
