import os
import subprocess
import folder_paths
import random
import datetime
import math
import numpy as np
from PIL import Image
import comfy.utils

class VideoConcatFFmpeg:
    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "num_VideoFile_paths": ("INT", {"default": 0, "min": 0, "max": 50, "step": 1}),
                "num_VideoDir_paths": ("INT", {"default": 0, "min": 0, "max": 50, "step": 1}),
                "output_name": ("STRING", {"default": ""}), 
                "output_path": ("STRING", {"default": ""}), 
                
                "ffmpeg_mode": (
                    [
                        "Auto (Re-encode H.264)", 
                        "Copy (Fastest, No Effects)", 
                    ], 
                    {"default": "Auto (Re-encode H.264)"}
                ),
                
                "concat_mode": (
                    [
                        "Simple (Hard Cut)", 
                        "Crossfade (Smooth Transition)", 
                    ], 
                    {"default": "Simple (Hard Cut)"}
                ),
                "transition_delay": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 5.0, "step": 0.1}),
                
                # --- ГРУППА ЦВЕТОКОРРЕКЦИИ ---
                "force_match_everything": ("BOOLEAN", {"default": False, "label_on": "Active (Override Below)", "label_off": "Disabled"}),
                
                "color_match_mode": (
                    [
                        "None", 
                        "Match Brightness", 
                        "Match Contrast",
                        "Match Saturation",
                        "Match Brightness + Contrast",
                        "Match Brightness + Saturation",
                        "Match Contrast + Saturation",
                        "Match All (Br. + Contr. + Sat.)"
                    ], 
                    {"default": "None"}
                ),
                
                "wb_gamma_mode": (
                    [
                        "None", 
                        "Match White Balance (Soft)",
                        "Match WB + Gamma (Experimental)"
                    ], 
                    {"default": "None"}
                ),
                
                "match_strength": ("FLOAT", {"default": 0.5, "min": 0.1, "max": 1.0, "step": 0.1}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("output_file_path",)
    FUNCTION = "concatenate_videos"
    OUTPUT_NODE = True
    CATEGORY = "video"

    def analyze_frame_stats(self, path):
        """
        Умный анализ с использованием 90-го перцентиля для насыщенности.
        """
        stats = {
            "duration": 0.0, "has_audio": False,
            "r_avg": 0.0, "g_avg": 0.0, "b_avg": 0.0,
            "luma_avg": 0.0, "luma_std": 0.0, "sat_avg": 0.0,
            "valid": False
        }
        try:
            cmd_probe = ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", path]
            res = subprocess.run(cmd_probe, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                import json
                data = json.loads(res.stdout)
                try: stats["duration"] = float(data["format"]["duration"])
                except: pass
                for s in data.get("streams", []):
                    if s.get("codec_type") == "audio":
                        stats["has_audio"] = True
                        break

            seek_time = max(0.5, stats["duration"] * 0.2)
            if seek_time > stats["duration"]: seek_time = 0.0
            cmd_extract = ["ffmpeg", "-ss", str(seek_time), "-i", path, "-vframes", "1", "-f", "image2pipe", "-vcodec", "png", "-"]
            process = subprocess.Popen(cmd_extract, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout_data, _ = process.communicate()
            if stdout_data:
                import io
                image = Image.open(io.BytesIO(stdout_data)).convert("RGB")
                np_img = np.array(image)
                
                means = np_img.mean(axis=(0,1)) 
                stats["r_avg"] = means[0]; stats["g_avg"] = means[1]; stats["b_avg"] = means[2]
                luma = 0.299 * np_img[:,:,0] + 0.587 * np_img[:,:,1] + 0.114 * np_img[:,:,2]
                stats["luma_avg"] = luma.mean(); stats["luma_std"] = luma.std()
                
                hsv_img = np.array(image.convert('HSV'))
                v_chan = hsv_img[:,:,2]
                s_chan = hsv_img[:,:,1]
                
                valid_mask = v_chan > 25
                if np.any(valid_mask):
                    valid_sats = s_chan[valid_mask]
                    stats["sat_avg"] = np.percentile(valid_sats, 90)
                else:
                    stats["sat_avg"] = 0.0
                stats["valid"] = True
        except Exception as e:
            print(f"[VideoConcat] Analysis Error {path}: {e}")
        return stats

    def concatenate_videos(self, num_VideoFile_paths, num_VideoDir_paths, output_name, output_path, 
                          ffmpeg_mode, concat_mode, transition_delay, 
                          force_match_everything, color_match_mode, wb_gamma_mode, match_strength, **kwargs):
        
        # --- SANITIZED PATH LOGIC ---
        root_output = os.path.abspath(self.output_dir)
        
        if not output_path or output_path.strip() == "":
            target_dir = root_output
        else:
            path_candidate = output_path.strip()
            
            # Проверяем абсолютный путь (может прийти от виджета)
            if os.path.isabs(path_candidate):
                try:
                    # Если путь лежит ВНУТРИ output_dir - всё ок
                    if os.path.commonpath([root_output, os.path.abspath(path_candidate)]) == root_output:
                        target_dir = os.path.abspath(path_candidate)
                    else:
                        # Если снаружи - отрезаем путь и кладем в output
                        safe_name = os.path.basename(os.path.normpath(path_candidate))
                        target_dir = os.path.join(root_output, safe_name)
                except Exception:
                    # Если разные диски - fallback
                    safe_name = os.path.basename(os.path.normpath(path_candidate))
                    target_dir = os.path.join(root_output, safe_name)
            else:
                # Относительный путь
                full_candidate = os.path.abspath(os.path.join(root_output, path_candidate))
                if full_candidate.startswith(root_output):
                    target_dir = full_candidate
                else:
                    print(f"[VideoConcat] Security violation: Path escape attempt. Using root.")
                    target_dir = root_output
            
        os.makedirs(target_dir, exist_ok=True)

        if not output_name or not output_name.strip():
            filename = f"merged-{datetime.datetime.now().strftime('%Y-%m-%d')}"
        else:
            filename = output_name.strip()
        
        counter = 1
        final_output_path = os.path.join(target_dir, f"{filename}_{counter:04d}.mp4")
        while os.path.exists(final_output_path):
            counter += 1
            final_output_path = os.path.join(target_dir, f"{filename}_{counter:04d}.mp4")
        
        try:
            # 1. Collect
            video_files = []
            for i in range(1, num_VideoFile_paths + 1):
                key = f"VideoFile_path_{i}"
                path = kwargs.get(key, "")
                if path and isinstance(path, str) and path.strip():
                    clean = path.strip().strip('"').strip("'")
                    if os.path.exists(clean): video_files.append(os.path.abspath(clean))
            
            valid_ext = {".mp4", ".mkv", ".mov", ".avi", ".webm"}
            for i in range(1, num_VideoDir_paths + 1):
                key = f"VideoDir_path_{i}"
                dpath = kwargs.get(key, "")
                if dpath and isinstance(dpath, str) and dpath.strip():
                    clean = dpath.strip().strip('"').strip("'")
                    if os.path.isdir(clean):
                        dfs = []
                        try:
                            for f in os.listdir(clean):
                                if os.path.splitext(f)[1].lower() in valid_ext:
                                    dfs.append(os.path.join(clean, f))
                            dfs.sort()
                            video_files.extend(dfs)
                        except: pass

            if not video_files:
                return {"result": ("",)}

            # 2. Logic
            pbar = comfy.utils.ProgressBar(100)
            pbar.update(5)

            if "Copy" in ffmpeg_mode:
                print(f"[VideoConcat] Mode: Direct Copy")
                list_path = os.path.join(target_dir, f"list_{random.randint(0,999)}.txt")
                with open(list_path, 'w', encoding='utf-8') as f:
                    for p in video_files: f.write(f"file '{p.replace('\\','/')}'\n")
                
                cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", final_output_path]
                subprocess.run(cmd, check=True)
                if os.path.exists(list_path): os.remove(list_path)
                
            else:
                do_crossfade = "Crossfade" in concat_mode and transition_delay > 0
                
                apply_bright = False; apply_contr = False; apply_sat = False
                apply_wb = False; apply_gamma = False
                
                if force_match_everything:
                    apply_bright = True; apply_contr = True; apply_sat = True
                    apply_wb = True; apply_gamma = True
                else:
                    cm = color_match_mode
                    if "Brightness" in cm or "Br." in cm: apply_bright = True
                    if "Contrast" in cm or "Contr." in cm: apply_contr = True
                    if "Saturation" in cm or "Sat." in cm: apply_sat = True
                    wg = wb_gamma_mode
                    if "White Balance" in wg or "WB" in wg: apply_wb = True
                    if "Gamma" in wg: apply_gamma = True
                
                any_effect = (apply_bright or apply_contr or apply_sat or apply_wb or apply_gamma)
                
                if not do_crossfade and not any_effect:
                    print(f"[VideoConcat] Mode: Simple Re-encode")
                    list_path = os.path.join(target_dir, f"list_{random.randint(0,999)}.txt")
                    with open(list_path, 'w', encoding='utf-8') as f:
                        for p in video_files: f.write(f"file '{p.replace('\\','/')}'\n")
                    
                    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                           "-c:v", "libx264", "-pix_fmt", "yuv420p", final_output_path]
                    subprocess.run(cmd, check=True)
                    if os.path.exists(list_path): os.remove(list_path)
                
                else:
                    print(f"[VideoConcat] Mode: Deep Processing. Strength: {match_strength}")
                    pbar.update(10)
                    files_data = []
                    ref = {}
                    has_audio_global = True 
                    
                    for idx, v in enumerate(video_files):
                        info = self.analyze_frame_stats(v)
                        info["path"] = v
                        files_data.append(info)
                        if idx == 0:
                            ref = info.copy()
                            if ref["sat_avg"] < 10:
                                print("[VideoConcat] Reference is almost B&W. Disabling saturation match.")
                                apply_sat = False
                            if ref["luma_avg"] < 15 or not ref["valid"]:
                                print("[VideoConcat] Reference dark/invalid. Safe mode.")
                                apply_contr = False; apply_gamma = False
                        
                        if not info["has_audio"]: has_audio_global = False

                    inputs = []
                    for v in video_files: inputs.extend(["-i", v])
                    
                    filter_str = ""
                    prepared_streams = []
                    
                    for i in range(len(files_data)):
                        stream_name = f"v{i}_prep"
                        cur = files_data[i]
                        filters = []
                        
                        if any_effect and i > 0 and cur["valid"]:
                            eq_params = []
                            cb_params = [] 
                            
                            # A. Brightness
                            if apply_bright:
                                diff = (ref["luma_avg"] - cur["luma_avg"]) / 255.0 * match_strength
                                diff = max(-0.3, min(0.3, diff))
                                if abs(diff) > 0.005: eq_params.append(f"brightness={diff:.3f}")
                            
                            # B. Contrast
                            if apply_contr:
                                c_std = max(5.0, cur["luma_std"])
                                r_std = max(5.0, ref["luma_std"])
                                contrast = 1.0 + (r_std / c_std - 1.0) * match_strength
                                contrast = max(0.85, min(1.4, contrast))
                                if abs(contrast - 1.0) > 0.02: eq_params.append(f"contrast={contrast:.3f}")
                                
                            # C. Saturation
                            if apply_sat:
                                c_sat = max(5.0, cur["sat_avg"])
                                r_sat = max(5.0, ref["sat_avg"])
                                sat = 1.0 + (r_sat / c_sat - 1.0) * match_strength
                                
                                if sat < 1.0:
                                    sat = max(0.9, sat) 
                                else:
                                    sat = min(1.6, sat)
                                    
                                if abs(sat - 1.0) > 0.02: eq_params.append(f"saturation={sat:.3f}")

                            # D. Gamma
                            if apply_gamma:
                                target_gamma = ref["luma_avg"] / max(5.0, cur["luma_avg"])
                                gamma = 1.0 + (target_gamma - 1.0) * (match_strength * 0.5)
                                gamma = max(0.85, min(1.25, gamma))
                                if abs(gamma - 1.0) > 0.05: eq_params.append(f"gamma={gamma:.3f}")

                            # E. White Balance
                            if apply_wb:
                                def get_bal(ref_c, cur_c):
                                    diff = (ref_c - cur_c) / 255.0 * match_strength
                                    return max(-0.3, min(0.3, diff))
                                r_bal = get_bal(ref["r_avg"], cur["r_avg"])
                                g_bal = get_bal(ref["g_avg"], cur["g_avg"])
                                b_bal = get_bal(ref["b_avg"], cur["b_avg"])
                                if abs(r_bal)>0.01 or abs(g_bal)>0.01 or abs(b_bal)>0.01:
                                    cb_params.extend([f"rm={r_bal:.3f}", f"gm={g_bal:.3f}", f"bm={b_bal:.3f}"])

                            if eq_params: filters.append(f"eq={':'.join(eq_params)}")
                            if cb_params: filters.append(f"colorbalance={':'.join(cb_params)}")

                        filters.append("format=yuv420p,setsar=1") 
                        filter_chain = ",".join(filters)
                        filter_str += f"[{i}:v]{filter_chain}[{stream_name}];"
                        prepared_streams.append(stream_name)

                    last_v = prepared_streams[0]
                    last_a = "0:a" if has_audio_global else None
                    current_offset = 0.0
                    
                    if do_crossfade:
                        for i in range(1, len(files_data)):
                            prev_dur = files_data[i-1]["duration"]
                            current_offset += prev_dur - transition_delay
                            next_v = prepared_streams[i]
                            target_v = f"v_out_{i}"
                            filter_str += f"[{last_v}][{next_v}]xfade=transition=fade:duration={transition_delay}:offset={current_offset:.3f}[{target_v}];"
                            last_v = target_v
                            if has_audio_global:
                                next_a = f"{i}:a"
                                target_a = f"a_out_{i}"
                                filter_str += f"[{last_a}][{next_a}]acrossfade=d={transition_delay}:c1=tri:c2=tri[{target_a}];"
                                last_a = target_a
                    else:
                        concat_ins = ""
                        for i in range(len(prepared_streams)):
                            concat_ins += f"[{prepared_streams[i]}]"
                            if has_audio_global: concat_ins += f"[{i}:a]"
                        a_val = 1 if has_audio_global else 0
                        filter_str += f"{concat_ins}concat=n={len(prepared_streams)}:v=1:a={a_val}[v_out_final]"
                        if has_audio_global: filter_str += "[a_out_final]"
                        last_v = "v_out_final"
                        last_a = "a_out_final" if has_audio_global else None

                    filter_str = filter_str.rstrip(";")
                    
                    cmd = ["ffmpeg", "-y"]
                    cmd.extend(inputs)
                    cmd.extend(["-filter_complex", filter_str, "-map", f"[{last_v}]"])
                    if has_audio_global and last_a: cmd.extend(["-map", f"[{last_a}]", "-c:a", "aac"])
                    cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", "-fps_mode", "cfr", final_output_path])
                    
                    print(f"[VideoConcat] Rendering Complex...")
                    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            pbar.update(100)

        except Exception as e:
            print(f"[VideoConcat] CRITICAL ERROR: {e}")
            if not os.path.exists(final_output_path):
                return {"result": ("",)}

        # 4. Result
        preview_results = []
        if os.path.exists(final_output_path):
            try:
                rel = os.path.relpath(final_output_path, self.output_dir)
                if not rel.startswith(".."):
                    f, n = os.path.split(rel)
                    preview_results.append({"filename": n, "subfolder": f, "type": "output", "format": "video/mp4"})
            except: pass

        if preview_results: return {"ui": {"images": preview_results}, "result": (final_output_path,)}
        return {"result": (final_output_path,)}
