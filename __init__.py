import os
import server
from aiohttp import web
import folder_paths
from pathlib import Path

# --- ИМПОРТ КЛАССОВ НОД ---
from .video_crossfade import VideoBatchCrossfade
from .ultimate_memory_cleaner import _UltimateMemoryCleaner
from .enhanced_video_preview import EnhancedVideoPreview
from .save_images_preview import SaveImagesPreviewPassthrough
from .video_concat import VideoConcatFFmpeg
from .image_size_control import GetImageSizeWithPreview

# Константы безопасности
MAX_PATH_LENGTH = 1024  # Разумное ограничение

# --- БЕЗОПАСНАЯ ПРОВЕРКА ПУТЕЙ ---
def is_path_allowed(path_str: str) -> bool:
    """Проверяет, что путь находится внутри разрешенных директорий ComfyUI"""
    try:
        if not path_str: return False
        if len(path_str) > MAX_PATH_LENGTH: return False
        
        path = Path(path_str)
        resolved = path.resolve()
        
        # Разрешенные корневые директории
        allowed_roots = [
            Path(folder_paths.get_output_directory()).resolve(),
            Path(folder_paths.get_temp_directory()).resolve()
        ]
        
        for allowed in allowed_roots:
            try:
                # Для Python 3.9+
                if hasattr(resolved, "is_relative_to"):
                    if resolved.is_relative_to(allowed):
                        return True
                else:
                    # Для Python 3.8
                    if str(resolved).startswith(str(allowed)):
                        return True
            except: continue
        
        return False
    except Exception:
        return False

# --- ОБЩАЯ ЛОГИКА API ДЛЯ БРАУЗЕРА ПАПОК ---
async def handle_list_dirs(request):
    try:
        data = await request.json()
        current_path = data.get("path", "")
        
        # Проверка длины пути
        if len(current_path) > MAX_PATH_LENGTH:
             return web.json_response({"error": "Path too long"}, status=400)

        # Если путь не задан, используем output directory
        if not current_path or current_path.strip() == "":
            current_path = folder_paths.get_output_directory()
        
        # Нормализация
        try:
            abs_current_path = str(Path(current_path).resolve())
        except:
            return web.json_response({"error": "Invalid path syntax"}, status=400)

        # КРИТИЧЕСКАЯ ПРОВЕРКА БЕЗОПАСНОСТИ
        if not is_path_allowed(abs_current_path):
            return web.json_response(
                {"error": "Access denied: Path is outside allowed directories", "path": current_path}, 
                status=403
            )

        if not os.path.exists(abs_current_path) or not os.path.isdir(abs_current_path):
            return web.json_response(
                {"error": "Path not found", "path": current_path}, 
                status=404
            )

        # Проверяем родителя
        parent_path = os.path.dirname(abs_current_path)
        if not is_path_allowed(parent_path):
            parent_path = None

        dirs = []
        try:
            with os.scandir(abs_current_path) as it:
                for entry in it:
                    if entry.is_dir() and not entry.name.startswith('.'):
                        dirs.append(entry.name)
        except PermissionError:
            return web.json_response({"error": "Permission denied"}, status=403)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

        dirs.sort()

        return web.json_response({
            "current_path": abs_current_path,
            "parent_path": parent_path,
            "dirs": dirs
        })
    except Exception as e:
        return web.json_response({"error": f"Unexpected error: {str(e)}"}, status=500)


# --- РЕГИСТРАЦИЯ МАРШРУТОВ API ---
@server.PromptServer.instance.routes.post("/enhanced_preview/list_dirs")
async def route_enhanced_list_dirs(request):
    return await handle_list_dirs(request)

@server.PromptServer.instance.routes.post("/save_preview/list_dirs")
async def route_save_list_dirs(request):
    return await handle_list_dirs(request)

@server.PromptServer.instance.routes.post("/api/save_preview/list_dirs")
async def route_api_save_list_dirs(request):
    return await handle_list_dirs(request)


# --- MAPPINGS ---
NODE_CLASS_MAPPINGS = {
    "VideoBatchCrossfade": VideoBatchCrossfade,
    "UltimateMemoryCleaner": _UltimateMemoryCleaner,
    "EnhancedVideoPreview": EnhancedVideoPreview,
    "Save Images & Preview": SaveImagesPreviewPassthrough,
    "Video Concat (FFmpeg)": VideoConcatFFmpeg,
    "GetImageSizeWithPreview": GetImageSizeWithPreview
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "VideoBatchCrossfade": "📹 Video Batch Crossfade",
    "UltimateMemoryCleaner": "🧹 Ultimate Memory Cleaner",
    "EnhancedVideoPreview": "🎬 Enhanced Video Save'n'Preview",
    "Save Images & Preview": "💾 Save Images & Preview (Passthrough)",
    "Video Concat (FFmpeg)": "🎥 Video Concat (FFmpeg)",
    "GetImageSizeWithPreview": "📏 Image Size Info & Edit"
}

WEB_DIRECTORY = "./web/js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
