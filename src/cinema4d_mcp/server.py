"""
Cinema 4D MCP Server
Enhanced MCP server for Cinema 4D 2025-2026 with chat functionality
"""

from mcp.server.fastmcp import FastMCP, Context, Image
import socket
import json
import asyncio
import logging
import tempfile
from dataclasses import dataclass
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, List, Optional
import os
from pathlib import Path
import base64
from cinema4d_mcp.chat_manager import get_chat_manager

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Cinema4DMCP")


@dataclass
class Cinema4DConnection:
    """Connection to Cinema 4D socket server"""
    host: str
    port: int
    sock: socket.socket = None
    timeout: float = 30.0  # Increased timeout for rendering operations

    def connect(self) -> bool:
        """Connect to the Cinema 4D plugin socket server"""
        if self.sock:
            return True

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            logger.info(f"Connected to Cinema 4D at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Cinema 4D: {str(e)}")
            self.sock = None
            return False

    def disconnect(self):
        """Disconnect from Cinema 4D"""
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logger.error(f"Error disconnecting from Cinema 4D: {str(e)}")
            finally:
                self.sock = None

    def receive_full_response(self, sock, buffer_size=8192):
        """Receive the complete response, potentially in multiple chunks"""
        chunks = []
        sock.settimeout(self.timeout)

        try:
            while True:
                try:
                    chunk = sock.recv(buffer_size)
                    if not chunk:
                        if not chunks:
                            raise Exception("Connection closed before receiving any data")
                        break

                    chunks.append(chunk)

                    # Check if we've received a complete JSON object
                    try:
                        data = b''.join(chunks)
                        json.loads(data.decode('utf-8'))
                        logger.info(f"Received complete response ({len(data)} bytes)")
                        return data
                    except json.JSONDecodeError:
                        continue
                except socket.timeout:
                    logger.warning("Socket timeout during chunked receive")
                    break
                except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
                    logger.error(f"Socket connection error during receive: {str(e)}")
                    raise
        except socket.timeout:
            logger.warning("Socket timeout during chunked receive")
        except Exception as e:
            logger.error(f"Error during receive: {str(e)}")
            raise

        if chunks:
            data = b''.join(chunks)
            logger.info(f"Returning data after receive completion ({len(data)} bytes)")
            try:
                json.loads(data.decode('utf-8'))
                return data
            except json.JSONDecodeError:
                raise Exception("Incomplete JSON response received")
        else:
            raise Exception("No data received")

    def send_command(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send a command to Cinema 4D and return the response"""
        if not self.sock and not self.connect():
            raise ConnectionError("Not connected to Cinema 4D")

        command = {
            "type": command_type,
            "params": params or {}
        }

        try:
            logger.info(f"Sending command: {command_type} with params: {params}")

            self.sock.sendall(json.dumps(command).encode('utf-8'))
            logger.info(f"Command sent, waiting for response...")

            self.sock.settimeout(self.timeout)

            response_data = self.receive_full_response(self.sock)
            logger.info(f"Received {len(response_data)} bytes of data")

            response = json.loads(response_data.decode('utf-8'))
            logger.info(f"Response parsed, status: {response.get('status', 'unknown')}")

            if response.get("status") == "error":
                logger.error(f"Cinema 4D error: {response.get('message')}")
                raise Exception(response.get("message", "Unknown error from Cinema 4D"))

            return response.get("result", {})
        except socket.timeout:
            logger.error("Socket timeout while waiting for response from Cinema 4D")
            self.sock = None
            raise Exception("Timeout waiting for Cinema 4D response - operation may be too complex")
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            logger.error(f"Socket connection error: {str(e)}")
            self.sock = None
            raise Exception(f"Connection to Cinema 4D lost: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from Cinema 4D: {str(e)}")
            if 'response_data' in locals() and response_data:
                logger.error(f"Raw response (first 200 bytes): {response_data[:200]}")
            raise Exception(f"Invalid response from Cinema 4D: {str(e)}")
        except Exception as e:
            logger.error(f"Error communicating with Cinema 4D: {str(e)}")
            self.sock = None
            raise Exception(f"Communication error with Cinema 4D: {str(e)}")


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """Manage server startup and shutdown lifecycle"""
    try:
        logger.info("Cinema 4D MCP server starting up")

        # Try to connect to Cinema 4D on startup
        try:
            c4d = get_cinema4d_connection()
            logger.info("Successfully connected to Cinema 4D on startup")
        except Exception as e:
            logger.warning(f"Could not connect to Cinema 4D on startup: {str(e)}")
            logger.warning("Make sure the Cinema 4D plugin is running before using Cinema 4D tools")

        yield {}
    finally:
        global _c4d_connection
        if _c4d_connection:
            logger.info("Disconnecting from Cinema 4D on shutdown")
            _c4d_connection.disconnect()
            _c4d_connection = None
        logger.info("Cinema 4D MCP server shut down")


# Create the MCP server with lifespan support
mcp = FastMCP(
    "Cinema4DMCP",
    description="Cinema 4D 2025-2026 integration through the Model Context Protocol with enhanced features",
    lifespan=server_lifespan
)

# Global connection
_c4d_connection = None


def get_cinema4d_connection():
    """Get or create a persistent Cinema 4D connection"""
    global _c4d_connection

    if _c4d_connection is not None:
        try:
            # Ping to check if connection is still valid
            result = _c4d_connection.send_command("ping")
            return _c4d_connection
        except Exception as e:
            logger.warning(f"Existing connection is no longer valid: {str(e)}")
            try:
                _c4d_connection.disconnect()
            except:
                pass
            _c4d_connection = None

    if _c4d_connection is None:
        _c4d_connection = Cinema4DConnection(host="localhost", port=9877)  # Different port than Blender
        if not _c4d_connection.connect():
            logger.error("Failed to connect to Cinema 4D")
            _c4d_connection = None
            raise Exception("Could not connect to Cinema 4D. Make sure the Cinema 4D plugin is running.")
        logger.info("Created new persistent connection to Cinema 4D")

    return _c4d_connection


# ========== Scene Management Tools ==========

@mcp.tool()
def get_scene_info(ctx: Context, include_hierarchy: bool = False) -> str:
    """
    Get detailed information about the current Cinema 4D scene.

    Parameters:
    - include_hierarchy: Include full object hierarchy (default: False)

    Returns comprehensive scene information including objects, materials, cameras, lights.
    """
    try:
        c4d = get_cinema4d_connection()
        result = c4d.send_command("get_scene_info", {"include_hierarchy": include_hierarchy})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting scene info from Cinema 4D: {str(e)}")
        return f"Error getting scene info: {str(e)}"


@mcp.tool()
def get_object_info(ctx: Context, object_name: str) -> str:
    """
    Get detailed information about a specific object in the Cinema 4D scene.

    Parameters:
    - object_name: The name of the object to get information about

    Returns object properties, transform data, tags, and more.
    """
    try:
        c4d = get_cinema4d_connection()
        result = c4d.send_command("get_object_info", {"name": object_name})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting object info from Cinema 4D: {str(e)}")
        return f"Error getting object info: {str(e)}"


@mcp.tool()
def create_object(ctx: Context, object_type: str, name: str, position: List[float] = None,
                  rotation: List[float] = None, scale: List[float] = None) -> str:
    """
    Create a new object in Cinema 4D.

    Parameters:
    - object_type: Type of object (cube, sphere, cylinder, cone, plane, null, camera, light, etc.)
    - name: Name for the new object
    - position: Position [x, y, z] (optional)
    - rotation: Rotation [h, p, b] in degrees (optional)
    - scale: Scale [x, y, z] (optional)

    Returns confirmation with object details.
    """
    try:
        c4d = get_cinema4d_connection()
        result = c4d.send_command("create_object", {
            "object_type": object_type,
            "name": name,
            "position": position,
            "rotation": rotation,
            "scale": scale
        })
        return f"Successfully created {object_type} named '{name}': {json.dumps(result, indent=2)}"
    except Exception as e:
        logger.error(f"Error creating object in Cinema 4D: {str(e)}")
        return f"Error creating object: {str(e)}"


@mcp.tool()
def modify_object(ctx: Context, object_name: str, position: List[float] = None,
                  rotation: List[float] = None, scale: List[float] = None,
                  properties: Dict[str, Any] = None) -> str:
    """
    Modify an existing object in Cinema 4D.

    Parameters:
    - object_name: Name of the object to modify
    - position: New position [x, y, z] (optional)
    - rotation: New rotation [h, p, b] in degrees (optional)
    - scale: New scale [x, y, z] (optional)
    - properties: Dictionary of additional properties to set (optional)

    Returns confirmation of modifications.
    """
    try:
        c4d = get_cinema4d_connection()
        result = c4d.send_command("modify_object", {
            "name": object_name,
            "position": position,
            "rotation": rotation,
            "scale": scale,
            "properties": properties
        })
        return f"Successfully modified '{object_name}': {json.dumps(result, indent=2)}"
    except Exception as e:
        logger.error(f"Error modifying object in Cinema 4D: {str(e)}")
        return f"Error modifying object: {str(e)}"


@mcp.tool()
def delete_object(ctx: Context, object_name: str) -> str:
    """
    Delete an object from the Cinema 4D scene.

    Parameters:
    - object_name: Name of the object to delete

    Returns confirmation of deletion.
    """
    try:
        c4d = get_cinema4d_connection()
        result = c4d.send_command("delete_object", {"name": object_name})
        return f"Successfully deleted '{object_name}'"
    except Exception as e:
        logger.error(f"Error deleting object from Cinema 4D: {str(e)}")
        return f"Error deleting object: {str(e)}"


# ========== Material Tools ==========

@mcp.tool()
def create_material(ctx: Context, name: str, color: List[float] = None,
                    reflectance: float = 0.0, roughness: float = 0.5,
                    metallic: float = 0.0, opacity: float = 1.0) -> str:
    """
    Create a new material in Cinema 4D with PBR properties.

    Parameters:
    - name: Name for the material
    - color: RGB color [r, g, b] values 0-1 (optional, default: white)
    - reflectance: Reflectance value 0-1 (default: 0.0)
    - roughness: Roughness value 0-1 (default: 0.5)
    - metallic: Metallic value 0-1 (default: 0.0)
    - opacity: Opacity value 0-1 (default: 1.0)

    Returns material details.
    """
    try:
        c4d = get_cinema4d_connection()
        result = c4d.send_command("create_material", {
            "name": name,
            "color": color or [1.0, 1.0, 1.0],
            "reflectance": reflectance,
            "roughness": roughness,
            "metallic": metallic,
            "opacity": opacity
        })
        return f"Successfully created material '{name}': {json.dumps(result, indent=2)}"
    except Exception as e:
        logger.error(f"Error creating material in Cinema 4D: {str(e)}")
        return f"Error creating material: {str(e)}"


@mcp.tool()
def apply_material(ctx: Context, object_name: str, material_name: str) -> str:
    """
    Apply a material to an object.

    Parameters:
    - object_name: Name of the object
    - material_name: Name of the material to apply

    Returns confirmation.
    """
    try:
        c4d = get_cinema4d_connection()
        result = c4d.send_command("apply_material", {
            "object_name": object_name,
            "material_name": material_name
        })
        return f"Successfully applied material '{material_name}' to '{object_name}'"
    except Exception as e:
        logger.error(f"Error applying material in Cinema 4D: {str(e)}")
        return f"Error applying material: {str(e)}"


# ========== Viewport and Rendering Tools ==========

@mcp.tool()
def get_viewport_screenshot(ctx: Context, width: int = 1920, height: int = 1080) -> Image:
    """
    Capture a screenshot of the current Cinema 4D viewport.

    Parameters:
    - width: Image width in pixels (default: 1920)
    - height: Image height in pixels (default: 1080)

    Returns the screenshot as an Image.
    """
    try:
        c4d = get_cinema4d_connection()

        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"c4d_screenshot_{os.getpid()}.png")

        result = c4d.send_command("get_viewport_screenshot", {
            "width": width,
            "height": height,
            "filepath": temp_path
        })

        if "error" in result:
            raise Exception(result["error"])

        if not os.path.exists(temp_path):
            raise Exception("Screenshot file was not created")

        with open(temp_path, 'rb') as f:
            image_bytes = f.read()

        os.remove(temp_path)

        return Image(data=image_bytes, format="png")

    except Exception as e:
        logger.error(f"Error capturing screenshot: {str(e)}")
        raise Exception(f"Screenshot failed: {str(e)}")


@mcp.tool()
def render_frame(ctx: Context, width: int = 1920, height: int = 1080,
                 renderer: str = "standard", samples: int = 100) -> Image:
    """
    Render the current frame from the active camera.

    Parameters:
    - width: Render width in pixels (default: 1920)
    - height: Render height in pixels (default: 1080)
    - renderer: Renderer to use (standard, physical, or redshift) (default: standard)
    - samples: Render samples/quality (default: 100)

    Returns the rendered image.
    """
    try:
        c4d = get_cinema4d_connection()

        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"c4d_render_{os.getpid()}.png")

        result = c4d.send_command("render_frame", {
            "width": width,
            "height": height,
            "renderer": renderer,
            "samples": samples,
            "filepath": temp_path
        })

        if "error" in result:
            raise Exception(result["error"])

        if not os.path.exists(temp_path):
            raise Exception("Render file was not created")

        with open(temp_path, 'rb') as f:
            image_bytes = f.read()

        os.remove(temp_path)

        return Image(data=image_bytes, format="png")

    except Exception as e:
        logger.error(f"Error rendering frame: {str(e)}")
        raise Exception(f"Render failed: {str(e)}")


# ========== Animation Tools ==========

@mcp.tool()
def set_animation_frame(ctx: Context, frame: int) -> str:
    """
    Set the current animation frame/time.

    Parameters:
    - frame: Frame number to set

    Returns confirmation.
    """
    try:
        c4d = get_cinema4d_connection()
        result = c4d.send_command("set_animation_frame", {"frame": frame})
        return f"Set animation frame to {frame}"
    except Exception as e:
        logger.error(f"Error setting animation frame: {str(e)}")
        return f"Error setting animation frame: {str(e)}"


@mcp.tool()
def create_keyframe(ctx: Context, object_name: str, parameter: str, value: Any, frame: int) -> str:
    """
    Create a keyframe for an object parameter.

    Parameters:
    - object_name: Name of the object
    - parameter: Parameter to keyframe (position.x, rotation.y, scale.z, etc.)
    - value: Value to set at this keyframe
    - frame: Frame number for the keyframe

    Returns confirmation.
    """
    try:
        c4d = get_cinema4d_connection()
        result = c4d.send_command("create_keyframe", {
            "object_name": object_name,
            "parameter": parameter,
            "value": value,
            "frame": frame
        })
        return f"Created keyframe for '{object_name}.{parameter}' at frame {frame}"
    except Exception as e:
        logger.error(f"Error creating keyframe: {str(e)}")
        return f"Error creating keyframe: {str(e)}"


# ========== Code Execution ==========

@mcp.tool()
def execute_python(ctx: Context, code: str) -> str:
    """
    Execute arbitrary Python code in Cinema 4D.

    Parameters:
    - code: The Python code to execute

    Use with caution. The code will run in Cinema 4D's Python environment.
    """
    try:
        c4d = get_cinema4d_connection()
        result = c4d.send_command("execute_code", {"code": code})
        return f"Code executed successfully: {result.get('result', '')}"
    except Exception as e:
        logger.error(f"Error executing code: {str(e)}")
        return f"Error executing code: {str(e)}"


# ========== Chat Tools ==========

@mcp.tool()
def send_chat_message(ctx: Context, message: str, include_scene_context: bool = True) -> str:
    """
    Send a chat message to Cinema 4D and receive a response.
    This allows for conversational interaction with Cinema 4D, maintaining chat history.

    Parameters:
    - message: The chat message to send
    - include_scene_context: Whether to include current scene information in the context (default: True)

    Returns the chat response with optional scene context.
    """
    try:
        c4d = get_cinema4d_connection()
        chat_manager = get_chat_manager()

        # Add user message to history
        chat_manager.add_message("user", message)

        # Get recent conversation history for context
        history = chat_manager.get_conversation_history(limit=10)

        # Send to Cinema 4D
        result = c4d.send_command("process_chat", {
            "message": message,
            "include_scene_context": include_scene_context,
            "history": history
        })

        if "error" in result:
            return f"Error: {result['error']}"

        response = result.get("response", "")
        context_info = result.get("context_info", {})

        # Add assistant response to history
        chat_manager.add_message("assistant", response, metadata=context_info)

        # Format output
        output = response

        if include_scene_context and context_info:
            output += "\n\n[Scene Context]\n"
            if "object_count" in context_info:
                output += f"Objects in scene: {context_info['object_count']}\n"
            if "selected_objects" in context_info:
                selected = ", ".join(context_info["selected_objects"])
                output += f"Selected: {selected}\n"

        return output
    except Exception as e:
        logger.error(f"Error sending chat message: {str(e)}")
        return f"Error sending chat message: {str(e)}"


@mcp.tool()
def get_chat_history(ctx: Context, limit: int = 20) -> str:
    """
    Get the chat conversation history.

    Parameters:
    - limit: Maximum number of recent messages to return (default: 20)

    Returns formatted chat history.
    """
    try:
        chat_manager = get_chat_manager()
        history = chat_manager.get_conversation_history(limit=limit)

        if not history:
            return "No chat history available."

        output = f"Chat History (showing {len(history)} messages):\n\n"
        for msg in history:
            role = msg["role"].capitalize()
            content = msg["content"]
            timestamp = msg.get("timestamp", "")
            output += f"[{timestamp}] {role}: {content}\n\n"

        return output
    except Exception as e:
        logger.error(f"Error getting chat history: {str(e)}")
        return f"Error getting chat history: {str(e)}"


@mcp.tool()
def clear_chat_history(ctx: Context) -> str:
    """
    Clear all chat history and start a new conversation session.

    Returns confirmation message.
    """
    try:
        chat_manager = get_chat_manager()
        chat_manager.reset()
        return "Chat history cleared. Starting new conversation session."
    except Exception as e:
        logger.error(f"Error clearing chat history: {str(e)}")
        return f"Error clearing chat history: {str(e)}"


@mcp.tool()
def get_chat_status(ctx: Context) -> str:
    """
    Check if chat functionality is enabled in Cinema 4D.
    Returns chat status and conversation summary.
    """
    try:
        c4d = get_cinema4d_connection()
        result = c4d.send_command("get_chat_status")

        enabled = result.get("enabled", False)
        message = result.get("message", "")

        if enabled:
            chat_manager = get_chat_manager()
            summary = chat_manager.get_summary()
            message += f"\n\nCurrent session: {summary['session_id']}"
            message += f"\nMessages: {summary['message_count']} "
            message += f"({summary['user_messages']} user, {summary['assistant_messages']} assistant)"

        return message
    except Exception as e:
        logger.error(f"Error checking chat status: {str(e)}")
        return f"Error checking chat status: {str(e)}"


# ========== Utility Tools ==========

@mcp.tool()
def export_scene(ctx: Context, filepath: str, format: str = "c4d") -> str:
    """
    Export the Cinema 4D scene to a file.

    Parameters:
    - filepath: Path where to save the file
    - format: Export format (c4d, fbx, obj, alembic, gltf, usd)

    Returns confirmation.
    """
    try:
        c4d = get_cinema4d_connection()
        result = c4d.send_command("export_scene", {
            "filepath": filepath,
            "format": format
        })
        return f"Successfully exported scene to {filepath}"
    except Exception as e:
        logger.error(f"Error exporting scene: {str(e)}")
        return f"Error exporting scene: {str(e)}"


@mcp.tool()
def import_file(ctx: Context, filepath: str, merge: bool = True) -> str:
    """
    Import a file into the Cinema 4D scene.

    Parameters:
    - filepath: Path to the file to import
    - merge: Whether to merge with current scene or replace (default: True)

    Returns confirmation with imported object info.
    """
    try:
        c4d = get_cinema4d_connection()
        result = c4d.send_command("import_file", {
            "filepath": filepath,
            "merge": merge
        })
        return f"Successfully imported {filepath}: {json.dumps(result, indent=2)}"
    except Exception as e:
        logger.error(f"Error importing file: {str(e)}")
        return f"Error importing file: {str(e)}"


@mcp.prompt()
def cinema4d_workflow() -> str:
    """Defines best practices for working with Cinema 4D"""
    return """When working with Cinema 4D through this MCP:

1. **Scene Management**:
   - Always check scene info first with get_scene_info()
   - Use create_object() to add primitives and null objects
   - modify_object() for transforming and adjusting properties
   - delete_object() to remove unwanted objects

2. **Material Workflow**:
   - Create materials with create_material() using PBR properties
   - Apply materials to objects with apply_material()
   - Cinema 4D supports full PBR workflow (color, roughness, metallic, reflectance)

3. **Visualization**:
   - get_viewport_screenshot() for quick previews
   - render_frame() for quality renders
   - Supports Standard, Physical, and Redshift renderers

4. **Animation**:
   - Use set_animation_frame() to navigate timeline
   - create_keyframe() to animate any parameter
   - Supports full keyframe animation workflow

5. **Chat Feature**:
   - Use send_chat_message() for conversational interactions
   - Chat maintains context about your scene
   - Ask questions about objects, materials, and scene state

6. **Import/Export**:
   - export_scene() supports multiple formats (FBX, OBJ, Alembic, glTF, USD)
   - import_file() to bring in external assets

7. **Code Execution**:
   - execute_python() for complex operations
   - Has access to full Cinema 4D Python API
   - Use for custom tools and advanced workflows

Best Practices:
- Start with scene queries to understand current state
- Build scenes incrementally with primitives
- Apply materials after creating geometry
- Test viewport screenshots before final renders
- Use chat for guidance and scene analysis
"""


# Main execution
def main():
    """Run the MCP server"""
    mcp.run()


if __name__ == "__main__":
    main()
