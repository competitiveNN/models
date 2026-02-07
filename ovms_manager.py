#!/usr/bin/env python3
"""
OpenVINO Model Server Configuration Manager

This script manages the ovms_config.json file and reloads the configuration
via the OpenVINO Model Server API.

Usage:
    python ovms_manager.py add <model_path> [--name <model_name>]
    python ovms_manager.py remove <model_name>
    python ovms_manager.py list
    python ovms_manager.py reload

Examples:
    python ovms_manager.py add /models/ov/mistral/llama-2-7b-chat
    python ovms_manager.py add /models/ov/mistral/phi-3-mini --name phi3-mini
    python ovms_manager.py add /models/ov/mistral/ministral --name ministral --llm
    python ovms_manager.py remove llama-2-7b-chat
    python ovms_manager.py list
    python ovms_manager.py reload
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
import requests
from typing import Dict, List, Optional


class OVMSConfigManager:
    def __init__(self, config_path: str = "ovms_config.json", server_url: str = "http://localhost:8000", 
                 interactive: bool = True, host_models_path: Optional[str] = None):
        self.config_path = Path(config_path)
        self.server_url = server_url
        self.interactive = interactive
        self.host_models_path = host_models_path or os.environ.get("MODELS_PATH", str(Path.home() / "data" / "models"))
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """Load the OVMS configuration file."""
        if not self.config_path.exists():
            # Create default config if it doesn't exist
            default_config = {
                "model_config_list": []
            }
            self._save_config(default_config)
            return default_config
        
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in {self.config_path}: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Error reading {self.config_path}: {e}")
            sys.exit(1)
    
    def _save_config(self, config: Dict) -> None:
        """Save the configuration to file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"✓ Configuration saved to {self.config_path}")
        except Exception as e:
            print(f"Error saving configuration: {e}")
            sys.exit(1)
    
    def _extract_model_name_from_path(self, model_path: str) -> str:
        """Extract model name from path."""
        return Path(model_path).name
    
    def _graph_exists(self, graph_name: str) -> bool:
        """Check if a graph with the given name already exists."""
        for graph in self.config.get("mediapipe_config_list", []):
            if graph.get("name") == graph_name:
                return True
        return False
    
    def _model_exists(self, model_name: str) -> bool:
        """Check if a model with the given name already exists."""
        for model in self.config.get("model_config_list", []):
            if model.get("config", {}).get("name") == model_name:
                return True
        return False
    
    def _map_path(self, path: str) -> Path:
        """Map a /models/... path to local filesystem path if running on host."""
        if str(path).startswith("/models/") and not Path("/models").exists():
            host_root = Path(self.host_models_path)
            if host_root.exists():
                return host_root / str(path)[len("/models/"):]
        return Path(path)

    def _parse_model_name(self, basename: str) -> str:
        """
        Extract model family, billion parameters, and quant flags from basename.
        Example: gemma3-4b-cw -> gemma3-4b-cw
        """
        # Try to find the size part (e.g. 4b, 7B, 1.1b)
        size_match = re.search(r'(\d+(?:\.\d+)?[bB])', basename)
        if not size_match:
            # Fallback to simple slugification if no size part found
            return re.sub(r'[^a-zA-Z0-9.-]', '-', basename).lower().strip('-')
            
        size_part = size_match.group(1).lower()
        start, end = size_match.span()
        
        # Family is everything before the size
        family_part = basename[:start].strip('-._')
        # Flags are everything after the size
        flags_part = basename[end:].strip('-._')
        
        # Normalize parts
        family = re.sub(r'[^a-zA-Z0-9-]', '-', family_part).strip('-').lower()
        flags = re.sub(r'[^a-zA-Z0-9-]', '-', flags_part).strip('-').lower()
        
        parts = []
        if family:
            parts.append(family)
        parts.append(size_part)
        if flags:
            parts.append(flags)
            
        name = "-".join(parts)
        # Ensure it doesn't have multiple dashes
        name = re.sub(r'-+', '-', name)
        return name

    def _create_unique_graph(self, template_path: str, target_path: str, model_path: str) -> bool:
        """Create a unique graph.pbtxt by copying a template and updating models_path."""
        # Try to find the template, handling host path mapping if needed
        p_template = self._map_path(template_path)
        
        if not p_template.exists():
            print(f"Error: Template graph file '{template_path}' not found.")
            return False
            
        try:
            with open(p_template, 'r') as f:
                content = f.read()
            
            # Update models_path - the model files are in the /1 subdirectory
            new_models_path = os.path.join(model_path, "1")
            pattern = r'(models_path:\s*["\'])([^"\']*)(["\'])'
            new_content = re.sub(pattern, lambda m: f"{m.group(1)}{new_models_path}{m.group(3)}", content)
            
            # Determine target write path (handling host mapping if needed)
            p_target = self._map_path(target_path)
            
            # Ensure parent exists
            p_target.parent.mkdir(parents=True, exist_ok=True)
            
            with open(p_target, 'w') as f:
                f.write(new_content)
                
            print(f"✓ Created unique graph at {target_path} (models_path: {new_models_path})")
            return True
        except Exception as e:
            print(f"Error creating unique graph: {e}")
            return False

    def add_model(self, model_path: str, model_name: Optional[str] = None, 
                  is_llm: bool = False, device: Optional[str] = None) -> None:
        """Add a model to the configuration."""
        # Resolve real path and determine symlink target
        symlink_target = model_path
        exists = os.path.exists(model_path)
        
        if not exists and model_path.startswith("/models/"):
            host_path = self._map_path(model_path)
            if host_path.exists():
                exists = True
        
        if not exists:
            print(f"Warning: Model path {model_path} does not exist")
            if self.interactive:
                response = input("Continue anyway? [y/N]: ")
                if response.lower() not in ['y', 'yes']:
                    print("Aborted.")
                    return
            else:
                print("Non-interactive mode: continuing anyway...")
        
        # Generate model name if not provided
        basename = os.path.basename(symlink_target.rstrip('/'))
        if not model_name:
            model_name = self._parse_model_name(basename)
            print(f"Generated model name: {model_name}")

        # Setup server directory structure
        server_root = "/models/ov/server"
        target_model_dir = os.path.join(server_root, model_name)
        version_dir = os.path.join(target_model_dir, "1")
        
        host_model_dir = self._map_path(target_model_dir)
        host_version_dir = self._map_path(version_dir)
        
        # Create directory and symlink
        host_model_dir.mkdir(parents=True, exist_ok=True)
        if host_version_dir.exists() or host_version_dir.is_symlink():
            if host_version_dir.is_symlink():
                host_version_dir.unlink()
            else:
                shutil.rmtree(host_version_dir)
        
        # Calculate relative symlink target mimicking 'ln -sr'
        # We need to calculate the relative path from target_model_dir to symlink_target
        # using their absolute representation in the container's view.
        
        # 1. Get container-absolute source path
        if symlink_target.startswith("/models/"):
            container_abs_src = os.path.normpath(symlink_target)
        else:
            host_abs_src = os.path.abspath(symlink_target)
            host_models_root = str(os.path.abspath(self.host_models_path))
            if host_abs_src.startswith(host_models_root):
                container_abs_src = "/models" + host_abs_src[len(host_models_root):]
            else:
                container_abs_src = host_abs_src
        
        # 2. Get container-absolute link parent path
        container_abs_parent = os.path.normpath(target_model_dir)
        
        # 3. Calculate relative path
        rel_symlink_target = os.path.relpath(container_abs_src, container_abs_parent)

        try:
            os.symlink(rel_symlink_target, host_version_dir)
            print(f"✓ Created relative symlink {version_dir} -> {rel_symlink_target}")
        except Exception as e:
            print(f"Error creating symlink: {e}")
            return
        
        # Ensure list keys exist
        if "model_config_list" not in self.config:
            self.config["model_config_list"] = []
        if "mediapipe_config_list" not in self.config:
            self.config["mediapipe_config_list"] = []

        if is_llm:
            graph_name = model_name
            backend_model_name = f"{model_name}_model"
            unique_graph_path = os.path.join(target_model_dir, "graph.pbtxt")
            
            # 1. Create unique graph
            template_graph_path = "/models/ov/server/graph.pbtxt"
            print(f"Creating unique graph from template: {template_graph_path}")
            if not self._create_unique_graph(template_graph_path, unique_graph_path, target_model_dir):
                print("Failed to create unique graph. Aborting configuration update.")
                return

            # 2. Update/Add backend model configuration
            model_config = {
                "config": {
                    "name": backend_model_name,
                    "base_path": target_model_dir
                }
            }
            if device:
                model_config["config"]["target_device"] = device

            # Clean up existing conflicting names
            self.config["model_config_list"] = [
                m for m in self.config["model_config_list"] 
                if m.get("config", {}).get("name") not in [backend_model_name, graph_name]
            ]
            self.config["model_config_list"].append(model_config)
            print(f"✓ Added model config entry: {backend_model_name}")

            # 3. Update/Add graph configuration
            graph_config = {
                "name": graph_name,
                "graph_path": unique_graph_path
            }
            self.config["mediapipe_config_list"] = [
                g for g in self.config["mediapipe_config_list"] 
                if g.get("name") != graph_name
            ]
            self.config["mediapipe_config_list"].append(graph_config)
            print(f"✓ Added mediapipe config entry: {graph_name}")
            
        else:
            # Regular model
            model_config = {
                "config": {
                    "name": model_name,
                    "base_path": target_model_dir
                }
            }
            if device:
                model_config["config"]["target_device"] = device
            
            # Clean up existing conflicting names
            self.config["model_config_list"] = [
                m for m in self.config["model_config_list"] 
                if m.get("config", {}).get("name") not in [model_name, f"{model_name}_model"]
            ]
            self.config["model_config_list"].append(model_config)
            
            # Remove from mediapipe_config_list if it was previously an LLM
            self.config["mediapipe_config_list"] = [
                g for g in self.config["mediapipe_config_list"] 
                if g.get("name") != model_name
            ]
            print(f"✓ Added regular model config entry: {model_name}")
        
        self._save_config(self.config)
    
    def remove_model(self, model_name: str) -> None:
        """Remove a model or graph from the configuration by name."""
        removed_items = []
        
        if "mediapipe_config_list" in self.config:
            original_count = len(self.config["mediapipe_config_list"])
            self.config["mediapipe_config_list"] = [
                graph for graph in self.config["mediapipe_config_list"]
                if graph.get("name") != model_name
            ]
            new_count = len(self.config["mediapipe_config_list"])
            if original_count > new_count:
                removed_items.append("graph")
        
        # Remove from model_config_list
        if "model_config_list" in self.config:
            original_count = len(self.config["model_config_list"])
            self.config["model_config_list"] = [
                model for model in self.config["model_config_list"]
                if model.get("config", {}).get("name") != model_name and 
                   model.get("config", {}).get("name") != f"{model_name}_model"
            ]
            new_count = len(self.config["model_config_list"])
            if original_count > new_count:
                removed_items.append("model")
        
        # Also remove the managed directory in /models/ov/server
        target_model_dir = os.path.join("/models/ov/server", model_name)
        host_model_dir = self._map_path(target_model_dir)
        if host_model_dir.exists():
            try:
                shutil.rmtree(host_model_dir)
                print(f"✓ Removed managed directory {target_model_dir}")
                if "directory" not in removed_items:
                    removed_items.append("directory")
            except Exception as e:
                print(f"Error removing directory {target_model_dir}: {e}")
        
        if not removed_items:
            print(f"Error: Model/Graph '{model_name}' not found in configuration and no managed directory exists")
            self.list_models()
            return
        
        self._save_config(self.config)
        print(f"✓ Removed {'/'.join(removed_items)} '{model_name}' from configuration")
    
    def list_models(self) -> None:
        """List all models and graphs in the configuration."""
        models = self.config.get("model_config_list", [])
        graphs = self.config.get("mediapipe_config_list", [])
        
        if not models and not graphs:
            print("No models or graphs configured")
            return
        
        total_items = len(models) + len(graphs)
        print(f"Configured items ({total_items}):")
        print("-" * 80)
        
        item_num = 1
        
        # List graphs (LLMs)
        for graph in graphs:
            graph_name = graph.get("name", "Unknown")
            model_name = f"{graph_name}_model"
            
            # Find the corresponding model
            model_path = "Unknown"
            device = None
            for model in models:
                if model.get("config", {}).get("name") == model_name:
                    model_path = model.get("config", {}).get("base_path", "Unknown")
                    device = model.get("config", {}).get("target_device")
                    break
            
            print(f"{item_num:2d}. {graph_name} (LLM Graph)")
            print(f"    Path: {model_path}")
            print(f"    Model: {model_name}")
            if device:
                print(f"    Device: {device}")
            print()
            item_num += 1
        
        # List regular models (that are not graphs)
        graph_names = [g.get("name") for g in graphs]
        for model in models:
            config = model.get("config", {})
            name = config.get("name", "Unknown")
            path = config.get("base_path", "Unknown")
            device = config.get("target_device")
            
            if name not in graph_names and not name.endswith("_model"):
                print(f"{item_num:2d}. {name} (Model)")
                print(f"    Path: {path}")
                if device:
                    print(f"    Device: {device}")
                print()
                item_num += 1
    
    def reload_config(self) -> None:
        """Reload the configuration via OVMS API."""
        try:
            url = f"{self.server_url}/v1/config/reload"
            print(f"Reloading configuration via {url}...")
            
            response = requests.post(url, timeout=30)
            
            if response.status_code == 200:
                print("✓ Configuration reloaded successfully")
                try:
                    result = response.json()
                    if result:
                        print(f"Server response: {result}")
                except:
                    pass
            else:
                print(f"✗ Failed to reload configuration")
                print(f"Status code: {response.status_code}")
                print(f"Response: {response.text}")
                
        except requests.exceptions.ConnectionError:
            print(f"✗ Could not connect to OVMS server at {self.server_url}")
            print("Make sure the OpenVINO Model Server is running")
        except requests.exceptions.Timeout:
            print("✗ Request timed out")
        except Exception as e:
            print(f"✗ Error reloading configuration: {e}")
    
    def status(self) -> None:
        """Check server status and list loaded models."""
        try:
            # Check server status
            url = f"{self.server_url}/v1/config"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                print("✓ OVMS server is running")
                try:
                    config = response.json()
                    models = config.get("model_config_list", [])
                    print(f"Loaded models: {len(models)}")
                    for model in models:
                        name = model.get("config", {}).get("name", "Unknown")
                        print(f"  - {name}")
                except:
                    print("Could not parse server response")
            else:
                print(f"✗ Server returned status code: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            print(f"✗ OVMS server not reachable at {self.server_url}")
        except Exception as e:
            print(f"✗ Error checking server status: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="OpenVINO Model Server Configuration Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s add /models/ov/mistral/llama-2-7b-chat
  %(prog)s add /models/ov/mistral/phi-3-mini --name phi3-mini
  %(prog)s add /models/ov/mistral/ministral --name ministral --llm
  %(prog)s remove llama-2-7b-chat
  %(prog)s list
  %(prog)s reload
  %(prog)s status"""
    )
    
    parser.add_argument(
        "--config", "-c",
        default="ovms_config.json",
        help="Path to OVMS configuration file (default: ovms_config.json)"
    )
    
    parser.add_argument(
        "--server", "-s",
        default="http://localhost:8000",
        help="OVMS server URL (default: http://localhost:8000)"
    )
    
    parser.add_argument(
        "--models-path", "-m",
        help="Host path where /models is mounted (default: $MODELS_PATH or ~/data/models)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Add command
    add_parser = subparsers.add_parser("add", help="Add a model or LLM graph to the configuration")
    add_parser.add_argument("path", help="Path to the model directory")
    add_parser.add_argument("--name", "-n", help="Model name (default: extracted from path)")
    add_parser.add_argument("--device", "-d", help="Target device (e.g. CPU, GPU, MULTI:GPU.1,GPU.0)")
    add_parser.add_argument("--llm", action="store_true",
                           help="Add as LLM graph (MediaPipe pipeline)")
    
    # Remove command
    remove_parser = subparsers.add_parser("remove", help="Remove a model or graph from the configuration")
    remove_parser.add_argument("name", help="Name of the model/graph to remove")
    
    # List command
    subparsers.add_parser("list", help="List all configured models and graphs")
    
    # Reload command
    subparsers.add_parser("reload", help="Reload the configuration on the server")
    
    # Status command
    subparsers.add_parser("status", help="Check server status and loaded models")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Create manager instance
    manager = OVMSConfigManager(args.config, args.server, host_models_path=args.models_path)
    
    # Execute command
    if args.command == "add":
        manager.add_model(args.path, args.name, args.llm, args.device)
    elif args.command == "remove":
        manager.remove_model(args.name)
    elif args.command == "list":
        manager.list_models()
    elif args.command == "reload":
        manager.reload_config()
    elif args.command == "status":
        manager.status()


if __name__ == "__main__":
    main()