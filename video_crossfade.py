import torch
import numpy as np

class VideoBatchCrossfade:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "Batches_count": ("INT", {"default": 2, "min": 2, "max": 1000, "step": 1}),
                "overlap_frames": ("INT", {"default": 8, "min": 0, "max": 256, "step": 1}),
                # Добавляем выпадающий список методов
                "fade_method": (
                    ["linear", "ease_in_out", "ease_in", "ease_out", "hard_cut"], 
                    {"default": "linear"}
                ),
            },
            "optional": {}
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "process_batches"
    CATEGORY = "video/postprocessing"

    def get_alpha_curve(self, steps, method, device):
        """Генерация кривой прозрачности (alpha)"""
        # Линейное время от 0 до 1
        t = torch.linspace(0.0, 1.0, steps=steps, dtype=torch.float32, device=device)
        
        if method == "linear":
            return t
        
        elif method == "ease_in_out":
            # Формула (1 - cos(t * pi)) / 2 — классическая S-образная кривая
            return 0.5 * (1.0 - torch.cos(t * torch.pi))
            
        elif method == "ease_in":
            # Квадратичное ускорение (t^2)
            return t * t
            
        elif method == "ease_out":
            # Квадратичное замедление (1 - (1-t)^2)
            return 1.0 - (1.0 - t) * (1.0 - t)
            
        else:
            # Fallback на линейный
            return t

    def crossfade_two_batches(self, batch_a, batch_b, overlap_frames, method):
        batch_a = batch_a.to(torch.float32)
        batch_b = batch_b.to(torch.float32)

        B1, H, W, C = batch_a.shape
        B2, H2, W2, C2 = batch_b.shape

        if (H, W, C) != (H2, W2, C2):
            raise ValueError(f"Batch shapes must match. Got {batch_a.shape} vs {batch_b.shape}")

        # Если выбран hard_cut, нахлест принудительно 0
        if method == "hard_cut":
            return torch.cat([batch_a, batch_b], dim=0)

        real_overlap = min(overlap_frames, B1, B2)

        if real_overlap == 0:
            return torch.cat([batch_a, batch_b], dim=0)

        # 1. Разделение
        prefix_a = batch_a[:-real_overlap] if real_overlap < B1 else torch.empty(0, H, W, C, device=batch_a.device)
        overlap_a = batch_a[-real_overlap:]

        overlap_b = batch_b[:real_overlap]
        suffix_b = batch_b[real_overlap:] if real_overlap < B2 else torch.empty(0, H, W, C, device=batch_b.device)

        # 2. Генерация Alpha по выбранному методу
        alpha = self.get_alpha_curve(real_overlap, method, batch_a.device)
        alpha = alpha.view(-1, 1, 1, 1) # reshape для бродкастинга [frames, 1, 1, 1]

        # 3. Смешивание
        blended = (1.0 - alpha) * overlap_a + alpha * overlap_b

        # 4. Сборка
        parts = []
        if prefix_a.shape[0] > 0: parts.append(prefix_a)
        parts.append(blended)
        if suffix_b.shape[0] > 0: parts.append(suffix_b)

        return torch.cat(parts, dim=0)

    def process_batches(self, Batches_count, overlap_frames, fade_method, **kwargs):
        batches_to_process = []
        
        # Сборка батчей
        for i in range(1, Batches_count + 1):
            key = f"Batch_{i:04d}" 
            image_batch = kwargs.get(key)
            if image_batch is not None:
                batches_to_process.append(image_batch)

        if not batches_to_process:
            return (torch.zeros((1, 512, 512, 3)),)

        result = batches_to_process[0]

        # Последовательная склейка
        for next_batch in batches_to_process[1:]:
            result = self.crossfade_two_batches(result, next_batch, overlap_frames, fade_method)

        return (result,)