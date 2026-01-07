import os
import server
from aiohttp import web
import folder_paths

# --- ИМПОРТ КЛАССОВ НОД ---
from .video_crossfade import VideoBatchCrossfade
from .ultimate_memory_cleaner import _UltimateMemoryCleaner
from .enhanced_video_preview import EnhancedVideoPreview
from .save_images_preview import SaveImagesPreviewPassthrough
from .video_concat import VideoConcatFFmpeg
from .image_size_control import GetImageSizeWithPreview  # <-- Новая нода

# --- ОБЩАЯ ЛОГИКА API ДЛЯ БРАУЗЕРА ПАПОК ---
# (Используется в EnhancedVideoPreview, SaveImagesPreview и VideoConcat)

async def handle_list_dirs(request):
    try:
        data = await request.json()
        current_path = data.get("path", "")
        
        # Если путь не задан, используем output directory
        if not current_path or current_path.strip() == "":
            current_path = folder_paths.get_output_directory()
        
        # Нормализация
        current_path = os.path.abspath(os.path.normpath(current_path))
        
        if not os.path.exists(current_path) or not os.path.isdir(current_path):
            return web.json_response(
                {"error": "Path not found or invalid", "path": current_path}, 
                status=404
            )

        parent_path = os.path.dirname(current_path)
        dirs = []

        try:
            with os.scandir(current_path) as it:
                for entry in it:
                    if entry.is_dir() and not entry.name.startswith('.'):
                        dirs.append(entry.name)
        except PermissionError:
            return web.json_response({"error": "Permission denied"}, status=403)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

        dirs.sort()

        return web.json_response({
            "current_path": current_path,
            "parent_path": parent_path,
            "dirs": dirs
        })
    except Exception as e:
        return web.json_response({"error": f"Unexpected error: {str(e)}"}, status=500)


# --- РЕГИСТРАЦИЯ МАРШРУТОВ API ---
# Регистрируем один обработчик на разные пути, чтобы поддержать все JS скрипты

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