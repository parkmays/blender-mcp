"""
Chat Manager for Cinema 4D MCP
Manages chat history and context for in-app conversations
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import json


class ChatMessage:
    """Represents a single chat message"""

    def __init__(self, role: str, content: str, timestamp: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        self.role = role  # 'user', 'assistant', or 'system'
        self.content = content
        self.timestamp = timestamp or datetime.now().isoformat()
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatMessage':
        """Create message from dictionary"""
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp"),
            metadata=data.get("metadata", {})
        )


class ChatManager:
    """Manages chat conversations and context"""

    def __init__(self, max_history: int = 100):
        self.history: List[ChatMessage] = []
        self.max_history = max_history
        self.context_data: Dict[str, Any] = {}
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    def add_message(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> ChatMessage:
        """Add a message to the chat history"""
        message = ChatMessage(role, content, metadata=metadata)
        self.history.append(message)

        # Trim history if it exceeds max
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        return message

    def get_messages(self, limit: Optional[int] = None, role_filter: Optional[str] = None) -> List[ChatMessage]:
        """Get chat messages with optional filtering"""
        messages = self.history

        if role_filter:
            messages = [m for m in messages if m.role == role_filter]

        if limit:
            messages = messages[-limit:]

        return messages

    def get_conversation_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get formatted conversation history"""
        messages = self.get_messages(limit=limit)
        return [m.to_dict() for m in messages]

    def update_context(self, key: str, value: Any) -> None:
        """Update context data"""
        self.context_data[key] = value

    def get_context(self, key: Optional[str] = None) -> Any:
        """Get context data"""
        if key:
            return self.context_data.get(key)
        return self.context_data.copy()

    def clear_history(self) -> None:
        """Clear all chat history"""
        self.history = []

    def clear_context(self) -> None:
        """Clear context data"""
        self.context_data = {}

    def reset(self) -> None:
        """Reset everything and start a new session"""
        self.clear_history()
        self.clear_context()
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    def export_history(self, filepath: str) -> None:
        """Export chat history to JSON file"""
        data = {
            "session_id": self.session_id,
            "messages": [m.to_dict() for m in self.history],
            "context": self.context_data
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    def import_history(self, filepath: str) -> None:
        """Import chat history from JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)

        self.session_id = data.get("session_id", self.session_id)
        self.history = [ChatMessage.from_dict(m) for m in data.get("messages", [])]
        self.context_data = data.get("context", {})

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the current chat state"""
        return {
            "session_id": self.session_id,
            "message_count": len(self.history),
            "user_messages": len([m for m in self.history if m.role == "user"]),
            "assistant_messages": len([m for m in self.history if m.role == "assistant"]),
            "context_keys": list(self.context_data.keys())
        }


# Global chat manager instance
_chat_manager: Optional[ChatManager] = None


def get_chat_manager() -> ChatManager:
    """Get or create the global chat manager instance"""
    global _chat_manager
    if _chat_manager is None:
        _chat_manager = ChatManager()
    return _chat_manager


def reset_chat_manager() -> None:
    """Reset the global chat manager"""
    global _chat_manager
    _chat_manager = None
