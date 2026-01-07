import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

app.registerExtension({
    name: "Comfyui.VideoConcat",
    
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "Video Concat (FFmpeg)") {
            
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function() {
                if(onNodeCreated) onNodeCreated.apply(this, arguments);
                
                initDynamicInputs(this);
                initPathBrowser(this, app);
                
                // --- ЛОГИКА ИНТЕРФЕЙСА ---
                const w_mode = this.widgets.find(w => w.name === "ffmpeg_mode");
                const w_force = this.widgets.find(w => w.name === "force_match_everything");
                
                const updateVisibility = () => {
                    const isCopy = w_mode.value.includes("Copy");
                    const isForce = w_force.value; // Boolean
                    
                    // 1. Глобальное скрытие при COPY
                    // Скрываем все настройки эффектов
                    const complexWidgets = ["concat_mode", "transition_delay", "force_match_everything", "color_match_mode", "wb_gamma_mode"];
                    
                    complexWidgets.forEach(name => {
                        const w = this.widgets.find(x => x.name === name);
                        if (!w) return;
                        if (!w.origType) w.origType = w.type;
                        
                        if (isCopy) {
                            w.type = "HIDDEN";
                            w.computeSize = () => [0, -4];
                        } else {
                            // Если не копи, восстанавливаем, НО...
                            // Проверяем логику Force Everything
                            if (isForce && (name === "color_match_mode" || name === "wb_gamma_mode")) {
                                w.type = "HIDDEN"; // Скрываем детальные настройки если включен Force
                                w.computeSize = () => [0, -4];
                            } else {
                                w.type = w.origType; // Показываем
                                delete w.computeSize;
                            }
                        }
                    });

                    // Ресайз ноды
                    this.setSize([this.size[0], this.computeSize()[1]]);
                    // Если есть превью, оно должно пересчитаться
                    if (this.videoWidget && this.lastVideoSize) {
                         // Простая перерисовка не изменит размер превью контейнера, 
                         // поэтому вызываем onExecuted логику или просто dirty
                    }
                    this.setDirtyCanvas(true, true);
                };

                if (w_mode) w_mode.callback = updateVisibility;
                if (w_force) w_force.callback = updateVisibility;
                
                setTimeout(updateVisibility, 100);
            };

            // ... (Далее стандартный код контекстного меню и плеера, без изменений) ...
            const getExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
            nodeType.prototype.getExtraMenuOptions = function(_, options) {
                if (getExtraMenuOptions) getExtraMenuOptions.apply(this, arguments);
                const widget = this.widgets?.find((w) => w.name === "video_preview");
                if (!widget) return;
                const isHidden = widget.element.style.display === "none";
                const url = widget.videoElement?.src;
                const myMenuOptions = [];
                myMenuOptions.push({
                    content: isHidden ? "👁️ Show Preview" : "🙈 Hide Preview",
                    callback: () => {
                        if (isHidden) {
                            widget.element.style.display = "flex";
                        } else {
                            this.lastVideoSize = [...this.size];
                            widget.element.style.display = "none";
                            // Пересчитываем высоту
                            const h = calculateInputsHeight(this);
                            this.setSize([this.size[0], h + 50]);
                        }
                        this.setDirtyCanvas(true, true);
                    }
                });
                if (url && !isHidden) {
                    myMenuOptions.push(
                        { content: "🎬 Open Video in New Tab", callback: () => window.open(url, "_blank") },
                        { content: "💾 Save Video As...", callback: () => {
                            const a = document.createElement("a");
                            a.href = url;
                            a.download = url.split('/').pop().split('?')[0];
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                        }}
                    );
                }
                if (myMenuOptions.length > 0) options.splice(0, 0, ...myMenuOptions);
            };

            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function(message) {
                if (onExecuted) onExecuted.apply(this, arguments);
                if (!message || !message.images || message.images.length === 0) return;
                const file = message.images[0];
                const params = new URLSearchParams({ filename: file.filename, subfolder: file.subfolder, type: file.type || "output" });
                const url = api.apiURL("/view?" + params.toString());
                let widget = this.widgets?.find((w) => w.name === "video_preview");
                if (!widget) {
                    const div = document.createElement("div");
                    Object.assign(div.style, { width: "100%", height: "100%", display: "flex", justifyContent: "center", alignItems: "center" });
                    const video = document.createElement("video");
                    Object.assign(video.style, { width: "100%", height: "100%", objectFit: "contain" });
                    video.controls = true; video.loop = true; video.autoplay = true;
                    video.addEventListener("contextmenu", (e) => { e.preventDefault(); e.stopPropagation(); app.canvas.selectNode(this); app.canvas.processContextMenu(this, e); });
                    div.appendChild(video);
                    widget = this.addDOMWidget("video_preview", "video", div, { serialize: false, hideOnZoom: false });
                    widget.videoElement = video;
                    video.onloadedmetadata = () => {
                       if (widget.element.style.display === "none") return;
                       const targetWidth = Math.max(this.size[0], Math.min(600, video.videoWidth));
                       const ratio = video.videoHeight / video.videoWidth;
                       const videoH = targetWidth * ratio;
                       const inputsH = calculateInputsHeight(this);
                       this.setSize([targetWidth, inputsH + videoH + 20]);
                       app.graph.setDirtyCanvas(true, true);
                    };
                }
                const vEl = widget.videoElement;
                const tsUrl = url + "&t=" + Date.now();
                if (!vEl.src.includes(url)) { vEl.src = tsUrl; if (widget.element.style.display !== "none") vEl.play().catch(()=>{}); }
            };
        }
    }
});

function calculateInputsHeight(node) {
    let height = 40; 
    if (node.inputs) height += node.inputs.length * 20;
    if (node.widgets) {
        node.widgets.forEach(w => {
            if (w.name !== "video_preview" && w.type !== "HIDDEN") height += 24; 
        });
    }
    return height;
}

function initDynamicInputs(node) {
    const updateInputs = (count, prefix, type) => {
        const currentInputs = node.inputs ? node.inputs.filter(i => i.name.startsWith(prefix)) : [];
        const currentCount = currentInputs.length;
        if (count > currentCount) { for (let i = currentCount + 1; i <= count; i++) node.addInput(`${prefix}${i}`, type); } 
        else if (count < currentCount) { for (let i = currentCount; i > count; i--) { const idx = node.findInputSlot(`${prefix}${i}`); if (idx !== -1) node.removeInput(idx); } }
        node.setDirtyCanvas(true);
    };
    const numFiles = node.widgets.find(w => w.name === "num_VideoFile_paths");
    const numDirs = node.widgets.find(w => w.name === "num_VideoDir_paths");
    if (numFiles) { numFiles.callback = (v) => updateInputs(v, "VideoFile_path_", "STRING"); setTimeout(() => updateInputs(numFiles.value, "VideoFile_path_", "STRING"), 100); }
    if (numDirs) { numDirs.callback = (v) => updateInputs(v, "VideoDir_path_", "STRING"); setTimeout(() => updateInputs(numDirs.value, "VideoDir_path_", "STRING"), 100); }
}

function initPathBrowser(node, app) {
    const pathWidget = node.widgets.find(w => w.name === "output_path");
    if (pathWidget) { node.addWidget("button", "📂 Browse Output", null, (w, c, n, p, e) => { showFolderContextMenu(pathWidget.value, e, pathWidget, app); }); }
}

async function showFolderContextMenu(path, event, targetWidget, app) {
    let data;
    try {
        const response = await api.fetchApi("/save_preview/list_dirs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: path }) });
        if (!response.ok) throw new Error("Network");
        data = await response.json();
    } catch (e) { alert("Error: " + e); return; }
    const vals = []; const opts = [];
    if (data.parent_path && data.parent_path !== data.current_path) { vals.push("⬅️ UP"); opts.push({ content: "⬅️ UP", callback: () => showFolderContextMenu(data.parent_path, event, targetWidget, app) }); }
    vals.push(`✅ SELECT: ${data.current_path}`); opts.push({ content: `✅ SELECT THIS`, callback: () => { targetWidget.value = data.current_path; if(targetWidget.callback)targetWidget.callback(targetWidget.value); app.graph.setDirtyCanvas(true,true); }});
    vals.push(null); opts.push(null);
    if (data.dirs) data.dirs.forEach(d => { vals.push("📁 "+d); opts.push({ content: "📁 "+d, callback: () => { const sep = data.current_path.includes("/")?"/":"\\"; const np = data.current_path.endsWith(sep) ? data.current_path+d : data.current_path+sep+d; showFolderContextMenu(np, event, targetWidget, app); }}); });
    new LiteGraph.ContextMenu(vals, { event: event, callback: (v) => { const idx=vals.indexOf(v); if(opts[idx]&&opts[idx].callback) opts[idx].callback(); }});
}