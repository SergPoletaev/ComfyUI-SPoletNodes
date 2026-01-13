import os
import json
import folder_paths
from PIL import Image, PngImagePlugin
import numpy as np
from pathlib import Path
import datetime
import re

class SaveImagesPreviewPassthrough:
    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"
        self.compress_level = 4

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "Image"}),
                "output_path": ("STRING", {"default": ""}), 
                "create_date_folder": ("BOOLEAN", {"default": True}),
                "file_format": (["png", "jpg", "jpeg", "bmp", "tiff"],),
                "filename_separator": ("STRING", {"default": "_"}), 
                "hide_preview": ("BOOLEAN", {"default": False}),
                "delimiter": (["comma", "dot", "hyphen", "underline", "newline"], {"default": "comma"}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("images", "file_path", "folder_path", "all_paths", "frames_count")
    
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    CATEGORY = "image"

    def sanitize_output_path(self, user_path: str) -> str:
        root_output = Path(self.output_dir).resolve()
        
        if not user_path or user_path.strip() == "":
            return str(root_output)
        
        try:
            path = Path(user_path.strip())
            if path.is_absolute():
                resolved = path.resolve()
                if hasattr(resolved, "is_relative_to"):
                    if resolved.is_relative_to(root_output): return str(resolved)
                else:
                    if str(resolved).startswith(str(root_output)): return str(resolved)
                
                # Unsafe absolute -> clean name
                safe_name = re.sub(r'[^\w\-\.]', '_', path.name)
                return str(root_output / safe_name)
            
            # Relative -> limit depth
            parts = [p for p in path.parts if p != '..' and p != '.' and p != '']
            if len(parts) > 20: parts = parts[:20]
            
            safe_path = root_output.joinpath(*parts)
            return str(safe_path)
        except:
            return str(root_output)

    def save_images(self, images, filename_prefix, output_path, create_date_folder, file_format, 
                   filename_separator, hide_preview, delimiter, prompt=None, extra_pnginfo=None):
        
        batch_count = len(images)

        # 1. Path Sanitization
        base_output_dir = self.sanitize_output_path(output_path)

        # 2. Date Folder
        if create_date_folder:
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            final_output_dir = os.path.join(base_output_dir, date_str)
        else:
            final_output_dir = base_output_dir

        try:
            os.makedirs(final_output_dir, exist_ok=True)
        except:
            final_output_dir = self.output_dir
            os.makedirs(final_output_dir, exist_ok=True)

        # 3. Format & Filename
        ext = file_format.lower()
        if ext == "jpeg": ext = "jpg"
        
        clean_prefix = re.sub(r'[^\w\-\.]', '_', filename_prefix)
        delimiter_map = {"comma": ",", "dot": ".", "hyphen": "-", "underline": "_", "newline": "\n"}
        actual_delimiter = delimiter_map.get(delimiter, ",")

        counter = 1
        if os.path.exists(final_output_dir):
            try:
                existing = [f for f in os.listdir(final_output_dir) if f.startswith(clean_prefix) and f.lower().endswith(f".{ext}")]
                if existing:
                    prefix_len = len(clean_prefix) + len(filename_separator)
                    max_num = 0
                    for f in existing:
                        try:
                            num_part = f[prefix_len : -(len(ext)+1)]
                            if num_part.isdigit():
                                max_num = max(max_num, int(num_part))
                        except: continue
                    counter = max_num + 1
            except: pass

        # 5. Saving
        results = []
        all_saved_paths = []
        images_np = (images.cpu().numpy() * 255).clip(0, 255).astype(np.uint8)

        for img_array in images_np:
            img = Image.fromarray(img_array)
            metadata = None
            if ext == "png":
                metadata = PngImagePlugin.PngInfo()
                if prompt: metadata.add_text("prompt", json.dumps(prompt))
                if extra_pnginfo:
                    for x in extra_pnginfo: metadata.add_text(x, json.dumps(extra_pnginfo[x]))

            filename = f"{clean_prefix}{filename_separator}{counter:05d}.{ext}"
            full_path = os.path.join(final_output_dir, filename)
            
            if ext == "png":
                img.save(full_path, pnginfo=metadata, compress_level=self.compress_level)
            else:
                if img.mode == 'RGBA': img = img.convert('RGB')
                img.save(full_path, quality=100)

            all_saved_paths.append(full_path)
            
            subfolder = ""
            try:
                p_root = Path(self.output_dir).resolve()
                p_final = Path(final_output_dir).resolve()
                
                try:
                    if hasattr(p_final, 'is_relative_to') and p_final.is_relative_to(p_root):
                        subfolder = str(p_final.relative_to(p_root))
                    elif str(p_final).startswith(str(p_root)):
                        subfolder = os.path.relpath(final_output_dir, self.output_dir)
                except: pass
                
                if subfolder == ".": subfolder = ""
            except: pass

            results.append({"filename": filename, "subfolder": subfolder, "type": self.type})
            counter += 1

        # 6. Return
        single_path_str = all_saved_paths[-1] if all_saved_paths else ""
        folder_path_str = final_output_dir
        all_paths_str = actual_delimiter.join(all_saved_paths)

        if hide_preview:
            return {"result": (images, single_path_str, folder_path_str, all_paths_str, batch_count)}
        
        return {"ui": { "images": results }, "result": (images, single_path_str, folder_path_str, all_paths_str, batch_count)}
