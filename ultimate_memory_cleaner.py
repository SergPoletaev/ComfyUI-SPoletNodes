import torch
import gc
import time
import comfy.model_management as model_management
from server import PromptServer

class _UltimateMemoryCleaner:
    DESCRIPTION = """
Ultimate Memory Cleaner

Полный аналог кнопок "Unload Models" и "Free model and node cache".
Принудительно очищает VRAM, RAM и внутренний кэш ComfyUI.

Опции:
- unload_models: Полная выгрузка загруженных моделей из VRAM/RAM.
- free_cache: Очистка "soft cache" (остатки весов моделей в памяти).
- aggressive_gc: Принудительный сборщик мусора Python (чистит RAM).
- delay: Пауза (сек) с визуальным таймером (шаг 1 сек).
Рекомендуется 2-3 сек. для картинок и 3-5 более сек. для видео.
    """

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {}, 
            "optional": {
                "unload_models": ("BOOLEAN", {"default": True}),
                "free_cache": ("BOOLEAN", {"default": True}),
                "aggressive_gc": ("BOOLEAN", {"default": True}),
                # Дефолт 1.0, шаг 1.0 (для удобства ввода целых чисел)
                "delay": ("FLOAT", {"default": 3.0, "min": 0.0, "max": 60.0, "step": 1.0}),
                "latent": ("LATENT",),
                "image": ("IMAGE",),
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "vae": ("VAE",),
            },
            "hidden": {"unique_id": "UNIQUE_ID"}
        }

    RETURN_TYPES = ("LATENT", "IMAGE", "MODEL", "CLIP", "VAE")
    FUNCTION = "clean_memory"
    CATEGORY = "utils/system"
    OUTPUT_NODE = True 

    def clean_memory(self, unload_models=True, free_cache=True, aggressive_gc=True, delay=1.0, 
                     latent=None, image=None, model=None, clip=None, vae=None, unique_id=None):
        
        # --- ОЧИСТКА ---
        if unload_models:
            model_management.unload_all_models()
            model_management.soft_empty_cache()

        if aggressive_gc:
            gc.collect()

        if free_cache:
            model_management.soft_empty_cache()
            if torch.cuda.is_available():
                torch.cuda.synchronize() 
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()

        # --- ЗАДЕРЖКА (ТАЙМЕР) ---
        if delay > 0:
            # Выделяем целое количество секунд и остаток
            steps = int(delay)
            remainder = delay - steps
            
            print(f"[UltimateMemoryCleaner]: Waiting {delay}s...")

            # Цикл по целым секундам
            for i in range(steps):
                time.sleep(1.0)
                # Обновляем прогресс (i+1 из steps)
                if unique_id is not None:
                    PromptServer.instance.send_sync("progress", 
                        {"value": i + 1, "max": steps, "node": unique_id})
            
            # Дожидаемся дробного остатка (если был, например 0.5 сек)
            if remainder > 0:
                time.sleep(remainder)

        return (latent, image, model, clip, vae)