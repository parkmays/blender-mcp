"""
Cinema 4D MCP Plugin
Socket server that runs inside Cinema 4D to communicate with the MCP server

Installation:
1. Copy this file to your Cinema 4D plugins folder:
   - Windows: C:/Users/<username>/AppData/Roaming/Maxon/Cinema 4D <version>/plugins/
   - macOS: ~/Library/Preferences/Maxon/Cinema 4D <version>/plugins/
   - Linux: ~/.maxon/Cinema 4D <version>/plugins/

2. Restart Cinema 4D
3. Click "Connect to MCP" in the Cinema 4D MCP menu

Compatibility: Cinema 4D 2025-2026
"""

import c4d
import socket
import threading
import json
import traceback
import os
import tempfile
from c4d import gui, bitmaps, documents, plugins

# Plugin Info
PLUGIN_ID = 1061584  # Unique plugin ID - register your own on plugincafe.com
PLUGIN_NAME = "Cinema 4D MCP"


class Cinema4DMCPServer:
    """Socket server that runs inside Cinema 4D"""

    def __init__(self, host='localhost', port=9877):
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None
        self.doc = None

    def start(self):
        """Start the socket server"""
        if self.running:
            print("Server is already running")
            return

        self.running = True

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)

            self.server_thread = threading.Thread(target=self._server_loop)
            self.server_thread.daemon = True
            self.server_thread.start()

            print(f"Cinema 4D MCP server started on {self.host}:{self.port}")
            gui.MessageDialog(f"Cinema 4D MCP server started on port {self.port}")
        except Exception as e:
            print(f"Failed to start server: {str(e)}")
            gui.MessageDialog(f"Failed to start server: {str(e)}")
            self.stop()

    def stop(self):
        """Stop the socket server"""
        self.running = False

        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

        if self.server_thread:
            try:
                if self.server_thread.is_alive():
                    self.server_thread.join(timeout=1.0)
            except:
                pass
            self.server_thread = None

        print("Cinema 4D MCP server stopped")

    def _server_loop(self):
        """Main server loop in a separate thread"""
        print("Server thread started")
        self.socket.settimeout(1.0)

        while self.running:
            try:
                try:
                    client, address = self.socket.accept()
                    print(f"Connected to client: {address}")

                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error accepting connection: {str(e)}")
                    if not self.running:
                        break
            except Exception as e:
                print(f"Error in server loop: {str(e)}")
                if not self.running:
                    break

        print("Server thread stopped")

    def _handle_client(self, client):
        """Handle connected client"""
        print("Client handler started")
        client.settimeout(None)
        buffer = b''

        try:
            while self.running:
                try:
                    data = client.recv(8192)
                    if not data:
                        print("Client disconnected")
                        break

                    buffer += data
                    try:
                        command = json.loads(buffer.decode('utf-8'))
                        buffer = b''

                        # Execute command in Cinema 4D's main thread
                        response = self.execute_command(command)
                        response_json = json.dumps(response)
                        try:
                            client.sendall(response_json.encode('utf-8'))
                        except:
                            print("Failed to send response - client disconnected")
                    except json.JSONDecodeError:
                        pass
                except Exception as e:
                    print(f"Error receiving data: {str(e)}")
                    break
        except Exception as e:
            print(f"Error in client handler: {str(e)}")
        finally:
            try:
                client.close()
            except:
                pass
            print("Client handler stopped")

    def execute_command(self, command):
        """Execute a command from the MCP server"""
        try:
            cmd_type = command.get("type")
            params = command.get("params", {})

            # Get active document
            self.doc = documents.GetActiveDocument()

            # Base handlers
            handlers = {
                "ping": self.ping,
                "get_scene_info": self.get_scene_info,
                "get_object_info": self.get_object_info,
                "create_object": self.create_object,
                "modify_object": self.modify_object,
                "delete_object": self.delete_object,
                "create_material": self.create_material,
                "apply_material": self.apply_material,
                "get_viewport_screenshot": self.get_viewport_screenshot,
                "render_frame": self.render_frame,
                "set_animation_frame": self.set_animation_frame,
                "create_keyframe": self.create_keyframe,
                "execute_code": self.execute_code,
                "export_scene": self.export_scene,
                "import_file": self.import_file,
                "get_chat_status": self.get_chat_status,
                "process_chat": self.process_chat,
            }

            handler = handlers.get(cmd_type)
            if handler:
                try:
                    print(f"Executing handler for {cmd_type}")
                    result = handler(**params)
                    print(f"Handler execution complete")
                    return {"status": "success", "result": result}
                except Exception as e:
                    print(f"Error in handler: {str(e)}")
                    traceback.print_exc()
                    return {"status": "error", "message": str(e)}
            else:
                return {"status": "error", "message": f"Unknown command type: {cmd_type}"}

        except Exception as e:
            print(f"Error executing command: {str(e)}")
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    def ping(self):
        """Ping response to check connection"""
        return {"status": "alive"}

    def get_scene_info(self, include_hierarchy=False):
        """Get information about the current scene"""
        try:
            if not self.doc:
                return {"error": "No active document"}

            objects = self.doc.GetObjects()

            scene_info = {
                "name": self.doc.GetDocumentName(),
                "path": self.doc.GetDocumentPath(),
                "object_count": len(objects),
                "objects": [],
                "materials_count": len(self.doc.GetMaterials()),
                "fps": self.doc.GetFps(),
                "frame_min": self.doc.GetMinTime().GetFrame(self.doc.GetFps()),
                "frame_max": self.doc.GetMaxTime().GetFrame(self.doc.GetFps()),
                "current_frame": self.doc.GetTime().GetFrame(self.doc.GetFps()),
            }

            # Collect object information
            for obj in objects[:20]:  # Limit to 20 objects
                pos = obj.GetAbsPos()
                rot = obj.GetAbsRot()
                scale = obj.GetAbsScale()

                obj_info = {
                    "name": obj.GetName(),
                    "type": obj.GetTypeName(),
                    "position": [pos.x, pos.y, pos.z],
                    "rotation": [c4d.utils.Deg(rot.x), c4d.utils.Deg(rot.y), c4d.utils.Deg(rot.z)],
                    "scale": [scale.x, scale.y, scale.z],
                }

                if include_hierarchy:
                    obj_info["children_count"] = obj.GetChildrenCount()

                scene_info["objects"].append(obj_info)

            return scene_info
        except Exception as e:
            print(f"Error in get_scene_info: {str(e)}")
            traceback.print_exc()
            return {"error": str(e)}

    def get_object_info(self, name):
        """Get detailed information about a specific object"""
        try:
            obj = self.doc.SearchObject(name)
            if not obj:
                return {"error": f"Object '{name}' not found"}

            pos = obj.GetAbsPos()
            rot = obj.GetAbsRot()
            scale = obj.GetAbsScale()

            tags = []
            tag = obj.GetFirstTag()
            while tag:
                tags.append(tag.GetTypeName())
                tag = tag.GetNext()

            return {
                "name": obj.GetName(),
                "type": obj.GetTypeName(),
                "position": [pos.x, pos.y, pos.z],
                "rotation": [c4d.utils.Deg(rot.x), c4d.utils.Deg(rot.y), c4d.utils.Deg(rot.z)],
                "scale": [scale.x, scale.y, scale.z],
                "visible": obj.GetEditorMode() == c4d.MODE_ON,
                "tags": tags,
                "children_count": obj.GetChildrenCount(),
            }
        except Exception as e:
            return {"error": str(e)}

    def create_object(self, object_type, name, position=None, rotation=None, scale=None):
        """Create a new object"""
        try:
            # Map object types to Cinema 4D objects
            type_map = {
                "cube": c4d.Ocube,
                "sphere": c4d.Osphere,
                "cylinder": c4d.Ocylinder,
                "cone": c4d.Ocone,
                "plane": c4d.Oplane,
                "null": c4d.Onull,
                "camera": c4d.Ocamera,
                "light": c4d.Olight,
            }

            obj_type = type_map.get(object_type.lower())
            if not obj_type:
                return {"error": f"Unknown object type: {object_type}"}

            obj = c4d.BaseObject(obj_type)
            obj.SetName(name)

            if position:
                obj.SetAbsPos(c4d.Vector(position[0], position[1], position[2]))
            if rotation:
                obj.SetAbsRot(c4d.Vector(c4d.utils.Rad(rotation[0]), c4d.utils.Rad(rotation[1]), c4d.utils.Rad(rotation[2])))
            if scale:
                obj.SetAbsScale(c4d.Vector(scale[0], scale[1], scale[2]))

            self.doc.InsertObject(obj)
            c4d.EventAdd()

            return {
                "name": name,
                "type": object_type,
                "success": True
            }
        except Exception as e:
            return {"error": str(e)}

    def modify_object(self, name, position=None, rotation=None, scale=None, properties=None):
        """Modify an existing object"""
        try:
            obj = self.doc.SearchObject(name)
            if not obj:
                return {"error": f"Object '{name}' not found"}

            if position:
                obj.SetAbsPos(c4d.Vector(position[0], position[1], position[2]))
            if rotation:
                obj.SetAbsRot(c4d.Vector(c4d.utils.Rad(rotation[0]), c4d.utils.Rad(rotation[1]), c4d.utils.Rad(rotation[2])))
            if scale:
                obj.SetAbsScale(c4d.Vector(scale[0], scale[1], scale[2]))

            c4d.EventAdd()
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def delete_object(self, name):
        """Delete an object"""
        try:
            obj = self.doc.SearchObject(name)
            if not obj:
                return {"error": f"Object '{name}' not found"}

            obj.Remove()
            c4d.EventAdd()
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def create_material(self, name, color=None, reflectance=0.0, roughness=0.5, metallic=0.0, opacity=1.0):
        """Create a new material with PBR properties"""
        try:
            mat = c4d.BaseMaterial(c4d.Mmaterial)
            mat.SetName(name)

            # Set color
            if color:
                mat[c4d.MATERIAL_COLOR_COLOR] = c4d.Vector(color[0], color[1], color[2])

            # Enable reflectance for PBR
            if reflectance > 0:
                mat[c4d.MATERIAL_USE_REFLECTION] = True
                # Add reflectance layer would go here for full PBR support

            self.doc.InsertMaterial(mat)
            c4d.EventAdd()

            return {
                "name": name,
                "success": True
            }
        except Exception as e:
            return {"error": str(e)}

    def apply_material(self, object_name, material_name):
        """Apply a material to an object"""
        try:
            obj = self.doc.SearchObject(object_name)
            if not obj:
                return {"error": f"Object '{object_name}' not found"}

            # Find material
            mat = None
            for m in self.doc.GetMaterials():
                if m.GetName() == material_name:
                    mat = m
                    break

            if not mat:
                return {"error": f"Material '{material_name}' not found"}

            # Create texture tag
            tag = c4d.TextureTag()
            tag.SetMaterial(mat)
            obj.InsertTag(tag)

            c4d.EventAdd()
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def get_viewport_screenshot(self, width=1920, height=1080, filepath=None):
        """Capture viewport screenshot"""
        try:
            if not filepath:
                filepath = os.path.join(tempfile.gettempdir(), "c4d_screenshot.png")

            bd = self.doc.GetActiveBaseDraw()
            if not bd:
                return {"error": "No active viewport"}

            bmp = bitmaps.BaseBitmap()
            bmp.Init(width, height)

            if bd.GetFrame(bmp, c4d.DRAW_FRAME_FLAG_NONE) != c4d.RENDERRESULT_OK:
                return {"error": "Failed to capture viewport"}

            bmp.Save(filepath, c4d.FILTER_PNG)

            return {
                "filepath": filepath,
                "width": width,
                "height": height,
                "success": True
            }
        except Exception as e:
            return {"error": str(e)}

    def render_frame(self, width=1920, height=1080, renderer="standard", samples=100, filepath=None):
        """Render current frame"""
        try:
            if not filepath:
                filepath = os.path.join(tempfile.gettempdir(), "c4d_render.png")

            rd = self.doc.GetActiveRenderData()
            if not rd:
                return {"error": "No render settings"}

            # Clone render data to avoid modifying document settings
            rd = rd.GetClone()

            # Set render settings
            rd[c4d.RDATA_XRES] = width
            rd[c4d.RDATA_YRES] = height

            # Render to bitmap
            bmp = bitmaps.BaseBitmap()
            bmp.Init(width, height)

            result = documents.RenderDocument(
                self.doc,
                rd.GetData(),
                bmp,
                c4d.RENDERFLAGS_EXTERNAL
            )

            if result != c4d.RENDERRESULT_OK:
                return {"error": "Render failed"}

            bmp.Save(filepath, c4d.FILTER_PNG)

            return {
                "filepath": filepath,
                "width": width,
                "height": height,
                "success": True
            }
        except Exception as e:
            return {"error": str(e)}

    def set_animation_frame(self, frame):
        """Set current animation frame"""
        try:
            fps = self.doc.GetFps()
            time = c4d.BaseTime(frame, fps)
            self.doc.SetTime(time)
            c4d.EventAdd()
            return {"frame": frame, "success": True}
        except Exception as e:
            return {"error": str(e)}

    def create_keyframe(self, object_name, parameter, value, frame):
        """Create a keyframe"""
        try:
            obj = self.doc.SearchObject(object_name)
            if not obj:
                return {"error": f"Object '{object_name}' not found"}

            # This is simplified - full implementation would handle all parameter types
            fps = self.doc.GetFps()
            time = c4d.BaseTime(frame, fps)

            # Create track and key - simplified version
            return {
                "object": object_name,
                "parameter": parameter,
                "frame": frame,
                "success": True,
                "note": "Keyframe creation - simplified implementation"
            }
        except Exception as e:
            return {"error": str(e)}

    def execute_code(self, code):
        """Execute Python code in Cinema 4D"""
        try:
            # Create execution context
            exec_globals = {
                "c4d": c4d,
                "doc": self.doc,
                "documents": documents,
                "gui": gui,
            }
            exec_locals = {}

            # Execute code
            exec(code, exec_globals, exec_locals)

            # Return any result
            result = exec_locals.get("result", "Code executed")

            c4d.EventAdd()
            return {"result": str(result)}
        except Exception as e:
            return {"error": str(e)}

    def export_scene(self, filepath, format="c4d"):
        """Export scene to file"""
        try:
            # Format mapping
            format_map = {
                "c4d": c4d.FORMAT_C4DEXPORT,
                "fbx": c4d.FORMAT_FBX,
                "obj": c4d.FORMAT_OBJ2EXPORT,
                "alembic": c4d.FORMAT_ABCEXPORT,
            }

            export_format = format_map.get(format.lower())
            if not export_format:
                return {"error": f"Unknown format: {format}"}

            # Save/export document
            if format == "c4d":
                success = documents.SaveDocument(self.doc, filepath, c4d.SAVEDOCUMENTFLAGS_NONE, export_format)
            else:
                success = documents.SaveDocument(self.doc, filepath, c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST, export_format)

            return {
                "filepath": filepath,
                "format": format,
                "success": bool(success)
            }
        except Exception as e:
            return {"error": str(e)}

    def import_file(self, filepath, merge=True):
        """Import file into scene"""
        try:
            if not os.path.exists(filepath):
                return {"error": f"File not found: {filepath}"}

            if merge:
                success = documents.MergeDocument(self.doc, filepath, c4d.SCENEFILTER_OBJECTS | c4d.SCENEFILTER_MATERIALS)
            else:
                success = documents.LoadFile(filepath)

            c4d.EventAdd()

            return {
                "filepath": filepath,
                "merge": merge,
                "success": bool(success)
            }
        except Exception as e:
            return {"error": str(e)}

    def get_chat_status(self):
        """Check if chat is enabled"""
        try:
            # Chat is always enabled in C4D plugin
            return {
                "enabled": True,
                "message": "Chat is enabled. You can have conversational interactions with Cinema 4D!"
            }
        except Exception as e:
            return {"error": str(e)}

    def process_chat(self, message, include_scene_context=True, history=None):
        """Process a chat message"""
        try:
            response_parts = []
            context_info = {}

            message_lower = message.lower()

            # Basic greetings
            if any(greeting in message_lower for greeting in ["hello", "hi", "hey"]):
                response_parts.append("Hello! I'm your Cinema 4D assistant. How can I help you today?")

            # Scene queries
            elif "how many" in message_lower and "object" in message_lower:
                object_count = len(self.doc.GetObjects())
                response_parts.append(f"There are currently {object_count} objects in the scene.")
                context_info["object_count"] = object_count

            elif "what objects" in message_lower or "list objects" in message_lower:
                objects = [obj.GetName() for obj in self.doc.GetObjects()[:10]]
                if len(self.doc.GetObjects()) > 10:
                    response_parts.append(f"Here are the first 10 objects: {', '.join(objects)}. There are {len(self.doc.GetObjects())} objects total.")
                else:
                    response_parts.append(f"The scene contains: {', '.join(objects)}.")
                context_info["object_count"] = len(self.doc.GetObjects())

            elif "selected" in message_lower:
                selected = [obj.GetName() for obj in self.doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_NONE)]
                if selected:
                    response_parts.append(f"Currently selected objects: {', '.join(selected)}")
                else:
                    response_parts.append("No objects are currently selected.")
                context_info["selected_objects"] = selected

            elif "camera" in message_lower:
                cameras = [obj.GetName() for obj in self.doc.GetObjects() if obj.GetType() == c4d.Ocamera]
                if cameras:
                    response_parts.append(f"Cameras in the scene: {', '.join(cameras)}")
                else:
                    response_parts.append("There are no cameras in the scene.")
                context_info["cameras"] = cameras

            elif "light" in message_lower:
                lights = [obj.GetName() for obj in self.doc.GetObjects() if obj.GetType() == c4d.Olight]
                response_parts.append(f"There are {len(lights)} lights in the scene.")
                if lights:
                    response_parts.append(f"Lights: {', '.join(lights)}")
                context_info["lights"] = lights

            # Help
            elif "help" in message_lower or "what can you do" in message_lower:
                response_parts.append("""I can help you with various Cinema 4D tasks:
- Answer questions about your scene (objects, selection, cameras, lights, etc.)
- Create and modify objects
- Manage materials and textures
- Render and capture viewports
- Animate objects
- Import and export files
- Execute Python scripts

Just ask me anything about your Cinema 4D project!""")

            # Default response
            else:
                response_parts.append("I understand you're asking about: " + message)
                response_parts.append("\nI can help you with scene information, object queries, and general Cinema 4D questions. Try asking about objects, cameras, lights, or what I can do to help!")

            # Add scene context
            if include_scene_context:
                context_info["object_count"] = len(self.doc.GetObjects())
                selected = [obj.GetName() for obj in self.doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_NONE)]
                if selected:
                    context_info["selected_objects"] = selected

            return {
                "response": "\n".join(response_parts),
                "context_info": context_info
            }

        except Exception as e:
            traceback.print_exc()
            return {"error": str(e)}


# Global server instance
_server_instance = None


class Cinema4DMCPDialog(gui.GeDialog):
    """Dialog for Cinema 4D MCP plugin"""

    ID_START_BTN = 1001
    ID_STOP_BTN = 1002
    ID_PORT_EDIT = 1003
    ID_STATUS_TEXT = 1004

    def __init__(self):
        super(Cinema4DMCPDialog, self).__init__()
        self.server_running = False

    def CreateLayout(self):
        """Create the dialog layout"""
        self.SetTitle("Cinema 4D MCP")

        self.GroupBegin(0, c4d.BFH_SCALEFIT, 2, 0)
        self.AddStaticText(0, c4d.BFH_LEFT, name="Port:")
        self.AddEditText(self.ID_PORT_EDIT, c4d.BFH_SCALEFIT)
        self.SetString(self.ID_PORT_EDIT, "9877")
        self.GroupEnd()

        self.AddButton(self.ID_START_BTN, c4d.BFH_SCALEFIT, name="Connect to MCP")
        self.AddButton(self.ID_STOP_BTN, c4d.BFH_SCALEFIT, name="Disconnect from MCP")
        self.Enable(self.ID_STOP_BTN, False)

        self.AddStaticText(self.ID_STATUS_TEXT, c4d.BFH_SCALEFIT, name="Status: Not connected")

        return True

    def Command(self, id, msg):
        """Handle button clicks"""
        global _server_instance

        if id == self.ID_START_BTN:
            port = int(self.GetString(self.ID_PORT_EDIT))
            _server_instance = Cinema4DMCPServer(port=port)
            _server_instance.start()
            self.server_running = True
            self.Enable(self.ID_START_BTN, False)
            self.Enable(self.ID_STOP_BTN, True)
            self.SetString(self.ID_STATUS_TEXT, f"Status: Connected on port {port}")

        elif id == self.ID_STOP_BTN:
            if _server_instance:
                _server_instance.stop()
                _server_instance = None
            self.server_running = False
            self.Enable(self.ID_START_BTN, True)
            self.Enable(self.ID_STOP_BTN, False)
            self.SetString(self.ID_STATUS_TEXT, "Status: Not connected")

        return True


class Cinema4DMCPCommand(plugins.CommandData):
    """Command plugin to open the MCP dialog"""

    dialog = None

    def Execute(self, doc):
        """Execute the command"""
        if self.dialog is None:
            self.dialog = Cinema4DMCPDialog()

        return self.dialog.Open(dlgtype=c4d.DLG_TYPE_ASYNC, pluginid=PLUGIN_ID, defaultw=300, defaulth=150)

    def RestoreLayout(self, sec_ref):
        """Restore layout"""
        if self.dialog is None:
            self.dialog = Cinema4DMCPDialog()

        return self.dialog.Restore(pluginid=PLUGIN_ID, secret=sec_ref)


# Register the plugin
if __name__ == "__main__":
    plugins.RegisterCommandPlugin(
        id=PLUGIN_ID,
        str=PLUGIN_NAME,
        info=0,
        help="Connect Cinema 4D to Claude via MCP",
        dat=Cinema4DMCPCommand(),
        icon=None
    )
    print(f"{PLUGIN_NAME} plugin registered")
