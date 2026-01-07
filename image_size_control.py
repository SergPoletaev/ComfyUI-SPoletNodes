import torch
import comfy.utils

class GetImageSizeWithPreview:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                
                "custom_resolution": ("BOOLEAN", {"default": False}),
                
                # Настройка интерполяции
                "interpolation": (["nearest-exact", "bilinear", "area", "bicubic", "lanczos", "bislerp"], {"default": "bicubic"}),
                
                "width_step": ("INT", {"default": 1, "min": 1, "max": 128, "step": 1}),
                "custom_width": ("INT", {"default": 0, "min": 0, "max": 16384, "step": 1}),
                
                "height_step": ("INT", {"default": 1, "min": 1, "max": 128, "step": 1}),
                "custom_height": ("INT", {"default": 0, "min": 0, "max": 16384, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "INT", "INT")
    RETURN_NAMES = ("image", "width", "height")
    FUNCTION = "get_size"
    CATEGORY = "ImageSizeInfo"

    def get_size(self, image, custom_resolution, interpolation, width_step, custom_width, height_step, custom_height):
        _, current_h, current_w, _ = image.shape
        
        final_w = current_w
        final_h = current_h

        if custom_resolution:
            if custom_width > 0:
                s_w = width_step if width_step > 0 else 1
                final_w = round(custom_width / s_w) * s_w
            if custom_height > 0:
                s_h = height_step if height_step > 0 else 1
                final_h = round(custom_height / s_h) * s_h

        if final_w != current_w or final_h != current_h:
            samples = image.movedim(-1, 1)
            # Используем выбранную интерполяцию вместо хардкода "bicubic"
            s = comfy.utils.common_upscale(samples, final_w, final_h, interpolation, "disabled")
            s = s.movedim(1, -1)
            result_image = s
        else:
            result_image = image

        info_text = f"Input:  {current_w} x {current_h}\nOutput: {final_w} x {final_h}"
        
        return {
            "ui": {"text": [info_text]}, 
            "result": (result_image, final_w, final_h)
        }