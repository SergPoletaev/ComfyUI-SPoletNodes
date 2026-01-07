import os
import torch
import numpy as np
import folder_paths
from pathlib import Path
import subprocess
import json
import time
import shutil
from PIL import Image as PILImage
from comfy.utils import ProgressBar

try:
    from videohelpersuite.nodes import VHS_FILENAMES
    VHS_AVAILABLE = True
except Exception:
    VHS_AVAILABLE = False


def _get_output_path(filename_prefix, extension, save_to_temp=False, custom_path=None):
    if custom_path and custom_path.strip():
        full_output_dir = custom_path.strip()
        subfolder = "" 
        file_type = "output"
    elif save_to_temp:
        output_dir = folder_paths.get_temp_directory()
        subfolder = "ComfyUI_Temp"
        full_output_dir = os.path.join(output_dir, subfolder)
        file_type = "temp"
    else:
        output_dir = folder_paths.get_output_directory()
        subfolder = "ComfyUI"
        full_output_dir = os.path.join(output_dir, subfolder)
        file_type = "output"

    try:
        Path(full_output_dir).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[EnhancedVideoSave] Error creating directory {full_output_dir}: {e}")
        return _get_output_path(filename_prefix, extension, save_to_temp=True)
    
    counter = len([f for f in os.listdir(full_output_dir) if f.startswith(filename_prefix)]) + 1
    filename = f"{filename_prefix}_{counter:05d}.{extension}"
    full_path = os.path.join(full_output_dir, filename)
    
    return full_path, subfolder, filename, file_type, full_output_dir


def _tensor_to_numpy(image_batch):
    if isinstance(image_batch, torch.Tensor):
        image_batch = image_batch.cpu().numpy()
    if image_batch.dtype != np.uint8:
        image_batch = (image_batch * 255).clip(0, 255).astype(np.uint8)
    return image_batch


def _generate_brightness_histogram(images_np):
    if images_np is None or images_np.size == 0:
        return torch.zeros((1, 100, 256, 3), dtype=torch.float32)

    if images_np.shape[0] > 1:
        img_for_hist = images_np[0:1]
    else:
        img_for_hist = images_np

    B, H, W, C = img_for_hist.shape
    if C == 4:
        gray = 0.299 * img_for_hist[..., 0] + 0.587 * img_for_hist[..., 1] + 0.114 * img_for_hist[..., 2]
    elif C == 3:
        gray = 0.299 * img_for_hist[..., 0] + 0.587 * img_for_hist[..., 1] + 0.114 * img_for_hist[..., 2]
    else:
        gray = img_for_hist[..., 0]

    hist, _ = np.histogram(gray.ravel(), bins=256, range=(0, 255), density=False)
    hist = hist.astype(np.float32)
    if hist.max() > 0:
        hist = hist / hist.max()

    hist_img = np.zeros((100, 256, 3), dtype=np.uint8)
    for i in range(256):
        height = int(hist[i] * 95)
        hist_img[95 - height:95, i] = [255, 165, 0]
    
    out_tensor = hist_img.astype(np.float32) / 255.0
    return torch.from_numpy(out_tensor[None, ...])


def _extract_video_info(video_path):
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return {}

        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])

        file_size_bytes = int(fmt.get("size", 0))
        duration_sec = float(fmt.get("duration", 0))
        duration_ms = int(duration_sec * 1000)
        
        hours = duration_ms // 3600000
        minutes = (duration_ms % 3600000) // 60000
        seconds = (duration_ms % 60000) // 1000
        millis = duration_ms % 1000
        duration_formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"

        info = {
            "filepath": video_path,
            "format": os.path.splitext(video_path)[1][1:].lower(),
            "file_size_bytes": file_size_bytes,
            "file_size_mb": round(file_size_bytes / (1024 * 1024), 2),
            "duration_sec": duration_sec,
            "duration_ms": duration_ms,
            "duration_formatted": duration_formatted,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "gps": None
        }

        video_stream = next((s for s in streams if s["codec_type"] == "video"), None)
        audio_stream = next((s for s in streams if s["codec_type"] == "audio"), None)

        if video_stream:
            w = int(video_stream.get("width", 0))
            h = int(video_stream.get("height", 0))
            info["width"] = w
            info["height"] = h
            info["frame_aspect_ratio"] = f"{w}:{h}"
            info["video_codec"] = video_stream.get("codec_name", "unknown")
            
            fps_val = 0.0
            r_frame_rate = video_stream.get("r_frame_rate", "0/1")
            try:
                num, den = map(float, r_frame_rate.split("/"))
                fps_val = num / den if den != 0 else 0.0
            except:
                pass
            info["fps"] = fps_val

            nb_frames = video_stream.get("nb_frames")
            if nb_frames and str(nb_frames).isdigit():
                info["total_frames"] = int(nb_frames)
            else:
                info["total_frames"] = int(duration_sec * fps_val) if fps_val > 0 else 0
        
        info["has_audio"] = bool(audio_stream)
        if audio_stream:
            info["audio_codec"] = audio_stream.get("codec_name", "unknown")

        return info
    except Exception as e:
        print(f"[EnhancedVideoSave] ffprobe error: {e}")
        return {}


def _stream_video_to_ffmpeg(images, output_path, fps, format, codec, preset, crf, pix_fmt, loop_vid):
    images = _tensor_to_numpy(images)
    B, H, W, C = images.shape

    if C == 4 and format == "mp4":
        images = np.ascontiguousarray(images[..., :3])
        C = 3
    
    input_args = [
        '-y',
        '-loglevel', 'error', 
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-s', f'{W}x{H}',
        '-pix_fmt', 'rgb24' if C == 3 else 'rgba',
        '-r', str(fps),
        '-i', '-' 
    ]

    output_args = []
    
    if format == "gif":
        output_args = [
            '-vf', f'split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse',
            output_path
        ]
    elif format == "webp":
        # WebP (Animated)
        # libwebp не поддерживает стандартные пресеты x264, поэтому убираем -preset
        # loop: 0 = infinite, 1 = once
        loop_count = 0 if loop_vid else 1
        output_args = [
            '-c:v', 'libwebp',
            '-pix_fmt', 'yuv420p', # Обычно для webp
            '-loop', str(loop_count),
            '-lossless', '0',
            '-q:v', str(100 - crf), # Примерное маппирование качества
            output_path
        ]
    elif format == "webm":
        vcodec = "libvpx-vp9"
        output_args = [
            '-c:v', vcodec, 
            '-pix_fmt', pix_fmt if pix_fmt != "auto" else "yuv420p", 
            '-b:v', '0', 
            '-crf', str(crf),
            output_path
        ]
    else: # mp4
        vcodec = "libx264" if codec in ("auto", "h264") else ("libx265" if codec == "h265" else codec)
        selected_pix_fmt = pix_fmt if pix_fmt != "auto" else "yuv420p"
        output_args = [
            '-c:v', vcodec, 
            '-pix_fmt', selected_pix_fmt, 
            '-preset', preset, 
            '-crf', str(crf), 
            output_path
        ]

    cmd = ['ffmpeg'] + input_args + output_args

    try:
        process = subprocess.Popen(
            cmd, 
            stdin=subprocess.PIPE, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL 
        )
    except FileNotFoundError:
        print("[EnhancedVideoSave] FFmpeg not found!")
        return False

    pbar = ProgressBar(B)

    for i in range(B):
        frame_bytes = images[i].tobytes()
        try:
            process.stdin.write(frame_bytes)
            pbar.update(1)
        except BrokenPipeError:
            print(f"[EnhancedVideoSave] ❌ FFmpeg pipe broken at frame {i}")
            break
        except Exception as e:
            print(f"[EnhancedVideoSave] Error sending frame: {e}")
            break

    if process.stdin:
        process.stdin.close()
    
    process.wait()

    if process.returncode != 0:
        return False
    
    return True


def _concat_videos_ffmpeg(video_paths_list, output_path, preset, crf, pix_fmt):
    list_path = output_path + ".txt"
    try:
        valid_paths = []
        for p in video_paths_list:
            if os.path.exists(p):
                valid_paths.append(p)
            else:
                print(f"[EnhancedVideoSave] ⚠️ Warning: File not found during concat: {p}")
        
        if not valid_paths:
            print("[EnhancedVideoSave] ❌ No valid files to concatenate")
            return False

        with open(list_path, "w", encoding="utf-8") as f:
            for path in valid_paths:
                safe_path = path.replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")
        
        selected_pix_fmt = pix_fmt if pix_fmt != "auto" else "yuv420p"
        
        cmd = [
            'ffmpeg', '-y',
            '-loglevel', 'error',
            '-f', 'concat',
            '-safe', '0',
            '-i', list_path,
            '-c:v', 'libx264',
            '-pix_fmt', selected_pix_fmt,
            '-preset', preset,
            '-crf', str(crf),
            '-c:a', 'aac',
            output_path
        ]
        
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[EnhancedVideoSave] Concat error: {e}")
        return False
    finally:
        if os.path.exists(list_path):
            os.remove(list_path)

def _merge_audio(video_path, audio_path, output_path):
    cmd = [
        'ffmpeg', '-y', '-loglevel', 'error',
        '-i', video_path,
        '-i', audio_path,
        '-c:v', 'copy',
        '-c:a', 'aac', '-b:a', '192k',
        '-shortest',
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _extract_last_n_frames(video_path, n, fps):
    if n <= 0:
        return torch.zeros((1, 512, 512, 3), dtype=torch.float32)
        
    try:
        if fps <= 0: fps = 1
        duration_needed = (n / fps) * 1.5 
        if duration_needed < 1.0: duration_needed = 1.0

        cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            '-sseof', f'-{duration_needed:.3f}',
            '-i', video_path,
            '-f', 'image2pipe',
            '-vcodec', 'png',
            '-'
        ]
        
        result = subprocess.run(cmd, capture_output=True, check=True)
        
        from io import BytesIO
        data = result.stdout
        frames = []
        png_signature = b'\x89PNG\r\n\x1a\n'
        parts = data.split(png_signature)
        
        for part in parts:
            if not part: continue
            img_data = png_signature + part
            try:
                img = PILImage.open(BytesIO(img_data)).convert("RGB")
                img_np = np.array(img).astype(np.float32) / 255.0
                frames.append(torch.from_numpy(img_np))
            except Exception:
                pass

        if not frames:
             return torch.zeros((1, 512, 512, 3), dtype=torch.float32)

        frames_tensor = torch.stack(frames)
        if frames_tensor.shape[0] > n:
            frames_tensor = frames_tensor[-n:]
            
        return frames_tensor

    except Exception as e:
        print(f"[EnhancedVideoSave] Error extracting last frames: {e}")
        return torch.zeros((1, 512, 512, 3), dtype=torch.float32)


class EnhancedVideoPreview:
    @classmethod
    def INPUT_TYPES(s):
        formats = ["mp4", "gif", "webm", "webp"]
        codecs = ["h264", "h265", "vp8", "vp9", "av1", "auto"]
        presets = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
        pix_fmts = ["yuv420p", "yuv422p", "yuv444p", "rgb24", "rgba", "auto"]
        
        return {
            "required": {
                # --- Сохранение ---
                "save_video_on_disk": ("BOOLEAN", {"default": False}), # Default OFF
                # Кнопка BROWSE будет добавлена через JS
                "save_path": ("STRING", {"default": "", "multiline": False}),
                "filename_prefix": ("STRING", {"default": "enhanced_video"}), # Default name
                
                # --- Кодирование ---
                "fps": ("FLOAT", {"default": 16.0, "min": 1.0, "max": 120.0, "step": 1.0}), # Default 16
                "format": (formats,), # Added webp
                "codec": (codecs, {"default": "h264"}), 
                "pix_fmt": (pix_fmts, {"default": "yuv420p"}),
                "preset": (presets, {"default": "ultrafast"}),
                "crf": ("INT", {"default": 20, "min": 0, "max": 51, "step": 1}),
                
                # --- Плеер ---
                "last_frames_count": ("INT", {"default": 0, "min": 0, "max": 200, "step": 1}), # Default 0
                "autoplay": ("BOOLEAN", {"default": True}),
                "mute": ("BOOLEAN", {"default": False}),
                "loop": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "images": ("IMAGE",),
                "audio": ("VHS_AUDIO",),
                "video_paths": ("STRING", {"forceInput": True, "multiline": True}),
            }
        }

    RETURN_TYPES = (
        "STRING",        # video_path
        "STRING",        # video_dir_path
        "IMAGE",         # Last_Frames
        "IMAGE",         # brightness_histogram
        "VHS_VIDEOINFO", # video_info
        "STRING",        # frame_aspect_ratio
        "STRING",        # duration_formatted
        "STRING"         # gps_json
    )
    
    RETURN_NAMES = (
        "video_path", 
        "video_dir_path", 
        "Last_Frames", 
        "brightness_histogram", 
        "video_info", 
        "frame_aspect_ratio", 
        "duration_formatted", 
        "gps_json"
    )
    OUTPUT_NODE = True
    FUNCTION = "preview"
    CATEGORY = "video/preview"

    def preview(self, save_video_on_disk, save_path, filename_prefix,
                fps, format, codec, pix_fmt, preset, crf, 
                last_frames_count, autoplay, mute, loop, images=None, audio=None, video_paths=None):
        
        ext_map = {"mp4": "mp4", "gif": "gif", "webm": "webm", "webp": "webp"}
        ext = ext_map.get(format, "mp4")

        # 1. ОПРЕДЕЛЕНИЕ ПУТИ
        save_to_temp = not save_video_on_disk
        
        final_output_path, subfolder, filename, file_type, internal_dir_path = \
            _get_output_path(filename_prefix, ext, 
                             save_to_temp=save_to_temp, 
                             custom_path=save_path)

        # 2. ГЕНЕРАЦИЯ
        output_frames = None 

        if images is not None:
            print(f"[EnhancedVideoSave] Mode: Images -> Video (Disk: {save_video_on_disk})")
            
            temp_video_path = final_output_path
            
            audio_path = None
            if audio is not None:
                try:
                    fname = audio.get("filename")
                    sdir = audio.get("subfolder", "")
                    atype = audio.get("type", "input")
                    base = folder_paths.get_input_directory() if atype == "input" else folder_paths.get_output_directory()
                    audio_path = os.path.join(base, sdir, fname)
                    if not os.path.exists(audio_path): audio_path = None
                except: audio_path = None

            if audio_path:
                temp_video_path = final_output_path.replace(f".{ext}", f"_temp.{ext}")

            success = _stream_video_to_ffmpeg(images, temp_video_path, fps, format, codec, preset, crf, pix_fmt, loop)
            if not success: raise RuntimeError("Encoding failed")

            if audio_path:
                _merge_audio(temp_video_path, audio_path, final_output_path)
                if os.path.exists(temp_video_path) and temp_video_path != final_output_path:
                    os.remove(temp_video_path)
            
            if last_frames_count > 0:
                if images.shape[0] > last_frames_count:
                    output_frames = images[-last_frames_count:]
                else:
                    output_frames = images

        elif video_paths is not None and len(video_paths.strip()) > 0:
            print(f"[EnhancedVideoSave] Mode: Concatenation (Disk: {save_video_on_disk})")
            
            raw_text = video_paths.strip()
            normalized_text = raw_text.replace(',', '\n').replace(';', '\n').replace('\r', '\n')
            path_list = []
            for line in normalized_text.split('\n'):
                clean_line = line.strip()
                clean_line = clean_line.strip('"').strip("'")
                if clean_line:
                    path_list.append(clean_line)
            
            if not path_list:
                raise ValueError("No valid video paths found in input string")

            success = _concat_videos_ffmpeg(path_list, final_output_path, preset, crf, pix_fmt)
            if not success: raise RuntimeError("Concatenation failed")
            
            info_temp = _extract_video_info(final_output_path)
            real_fps = info_temp.get("fps", fps)
            if real_fps == 0: real_fps = fps
            
            if last_frames_count > 0:
                output_frames = _extract_last_n_frames(final_output_path, last_frames_count, real_fps)
            
        else:
            raise ValueError("Input Error: Either 'images' or 'video_paths' must be provided.")

        # Сбор информации
        info = _extract_video_info(final_output_path)
        if not info:
            info = {
                "duration_sec": 0, "total_frames": 0,
                "width": 0, "height": 0, "gps": None, "fps": 0
            }
        
        hist_image = _generate_brightness_histogram(_tensor_to_numpy(output_frames) if output_frames is not None else None)

        # UI Payload
        ui_payload = {
            "filename": filename,
            "subfolder": subfolder,
            "type": file_type, 
            "format": "video/" + format if format != "gif" else "image/gif",
            "options": {
                "autoplay": autoplay,
                "mute": mute,
                "loop": loop
            }
        }

        if format in ["mp4", "webm"]:
            ui_data = {"videos": [ui_payload]}
        elif format == "gif":
            ui_data = {"gifs": [ui_payload]}
        else:
            ui_data = {}

        gps_json = json.dumps(info.get("gps"), indent=2, ensure_ascii=False) if info.get("gps") else "{}"
        
        vhs_video_info = {
            "source_fps": info.get("fps", 0.0),
            "source_frame_count": int(info.get("total_frames", 0)),
            "source_duration": float(info.get("duration_sec", 0.0)),
            "source_width": int(info.get("width", 0)),
            "source_height": int(info.get("height", 0)),
            "loaded_fps": info.get("fps", 0.0),
            "loaded_frame_count": int(info.get("total_frames", 0)),
            "loaded_duration": float(info.get("duration_sec", 0.0)),
            "loaded_width": int(info.get("width", 0)),
            "loaded_height": int(info.get("height", 0)),
        }

        print(f"[EnhancedVideoSave] ✅ Result saved to: {internal_dir_path}")
        
        if output_frames is None:
             output_frames = torch.zeros((1, 512, 512, 3), dtype=torch.float32)

        return {
            "ui": ui_data,
            "result": (
                final_output_path,      
                internal_dir_path,      
                output_frames,          
                hist_image,             
                vhs_video_info,         
                info.get("frame_aspect_ratio", ""), 
                info.get("duration_formatted", ""), 
                gps_json                
            )
        }

NODE_CLASS_MAPPINGS = {"EnhancedVideoPreview": EnhancedVideoPreview}
NODE_DISPLAY_NAME_MAPPINGS = {"EnhancedVideoPreview": "🎬 Enhanced Video Save'n'Preview"}